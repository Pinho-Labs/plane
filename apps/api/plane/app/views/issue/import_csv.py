# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.http import HttpResponse

# Third Party imports
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueImportSerializer
from plane.bgtasks.issue_import_task import issue_import_task
from plane.db.models import IssueImport, Project
from plane.utils.host import base_host
from plane.utils.importers.context import build_resolution_context
from plane.utils.importers.csv_issue_importer import FILE_LEVEL_ROW, build_preview
from plane.utils.importers.preview import (
    build_display_maps,
    serialize_invalid_rows,
    serialize_valid_row,
)
from plane.utils.importers.rules import build_import_rules_markdown
from plane.utils.importers.runner import MAX_STORED_ERRORS, create_rows, serialize_errors
from plane.utils.importers.template import build_template_csv
from ..base import BaseAPIView

# Uploads larger than this are rejected outright (must stay under the proxy's
# FILE_SIZE_LIMIT). Kept in sync with the frontend's client-side guard.
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Row count above which the import runs as a background Celery task instead of
# synchronously in-request. Grounded in the ~30s gunicorn worker timeout.
SYNC_ROW_THRESHOLD = 200

# Cap on how many resolved rows the validate dry-run returns for the preview
# table. All valid rows are still imported on commit — this only bounds the
# preview payload; the response flags when it was truncated.
PREVIEW_LIMIT = 200


def _read_csv_file(request):
    """Return (text, error_response). Exactly one is non-None."""
    upload = request.FILES.get("file")
    if upload is None:
        return None, Response(
            {"error": "No CSV file was provided under the 'file' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if upload.size > MAX_FILE_SIZE:
        return None, Response(
            {"error": f"CSV exceeds the maximum size of {MAX_FILE_SIZE // (1024 * 1024)}MB."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        # utf-8-sig transparently strips a BOM written by spreadsheet apps.
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, Response(
            {"error": "The CSV file must be UTF-8 encoded."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return text, None


class IssueCSVTemplateEndpoint(BaseAPIView):
    """Download the canonical CSV template (headers + one example row)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        response = HttpResponse(build_template_csv(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="work-items-import-template.csv"'
        return response


class IssueCSVRulesEndpoint(BaseAPIView):
    """Return a Markdown rules document with this project's live allowed values.

    Meant to be handed to an LLM so it generates a CSV that imports cleanly.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id)
        markdown = build_import_rules_markdown(project, request.user.id)
        return Response({"markdown": markdown}, status=status.HTTP_200_OK)


class IssueCSVImportValidateEndpoint(BaseAPIView):
    """Dry-run: parse + resolve + validate the CSV, writing nothing."""

    parser_classes = (MultiPartParser, FormParser)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        text, error = _read_csv_file(request)
        if error is not None:
            return error

        project = Project.objects.get(pk=project_id)
        ctx = build_resolution_context(project, request.user.id)
        preview = build_preview(text, ctx)

        # Resolve ids back to display values so the preview table renders each
        # row like a real work item (state pill, avatars, coloured labels, …).
        maps = build_display_maps(project)
        sample = [serialize_valid_row(row, maps) for row in preview.valid_rows[:PREVIEW_LIMIT]]
        invalid_sample = serialize_invalid_rows(preview.invalid_rows[:PREVIEW_LIMIT], preview.errors)

        return Response(
            {
                "total": preview.total,
                "valid": preview.valid_count,
                "invalid": preview.invalid_count,
                "errors": serialize_errors(preview.errors)[:MAX_STORED_ERRORS],
                "sample": sample,
                "invalid_sample": invalid_sample,
                "preview_limit": PREVIEW_LIMIT,
                "sample_truncated": preview.valid_count > PREVIEW_LIMIT,
            },
            status=status.HTTP_200_OK,
        )


class IssueCSVImportEndpoint(BaseAPIView):
    """Commit an import (POST) and list import history (GET).

    Small files import synchronously; files above SYNC_ROW_THRESHOLD are handed
    to a Celery task and the client polls the history endpoint for status.
    """

    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        imports = IssueImport.objects.filter(workspace__slug=slug, project_id=project_id)
        return Response(IssueImportSerializer(imports, many=True).data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        text, error = _read_csv_file(request)
        if error is not None:
            return error

        skip_invalid = str(request.data.get("skip_invalid", "false")).lower() in ("true", "1", "yes")
        upload = request.FILES.get("file")
        file_name = (getattr(upload, "name", None) or "import.csv")[:255]

        project = Project.objects.get(pk=project_id)
        ctx = build_resolution_context(project, request.user.id)
        preview = build_preview(text, ctx)

        # File-level problems (missing Name column, empty file, row cap) always block.
        file_errors = [e for e in preview.errors if e.row == FILE_LEVEL_ROW]
        if file_errors:
            return Response(
                {"error": file_errors[0].message, "errors": serialize_errors(file_errors)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Invalid rows block the whole import unless the caller opts into partial import.
        if preview.invalid_count and not skip_invalid:
            return Response(
                {
                    "error": "Some rows are invalid. Fix them, or retry with skip_invalid=true to import the rest.",
                    "total": preview.total,
                    "valid": preview.valid_count,
                    "invalid": preview.invalid_count,
                    "errors": serialize_errors(preview.errors)[:MAX_STORED_ERRORS],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = IssueImport.objects.create(
            project_id=project_id,
            workspace_id=project.workspace_id,
            file_name=file_name,
            initiated_by=request.user,
            status="queued",
            total_rows=preview.total,
        )

        origin = base_host(request=request, is_app=True)

        # Above the threshold the client only gets a queued record and polls the history endpoint.
        if preview.total > SYNC_ROW_THRESHOLD:
            issue_import_task.delay(
                importer_id=str(record.id),
                csv_text=text,
                user_id=str(request.user.id),
                slug=slug,
                origin=origin,
            )
            return Response(
                {"id": str(record.id), "status": "queued", "total": preview.total, "async": True},
                status=status.HTTP_202_ACCEPTED,
            )

        record.status = "processing"
        record.save(update_fields=["status", "updated_at"])

        created, skipped, failed, row_errors = create_rows(
            request.user, slug, origin, project, preview.valid_rows
        )

        all_errors = serialize_errors(preview.errors) + row_errors
        record.created_rows = created
        record.skipped_rows = skipped
        record.failed_rows = failed + preview.invalid_count
        record.error_report = all_errors[:MAX_STORED_ERRORS]
        record.status = "completed"
        record.save(
            update_fields=["created_rows", "skipped_rows", "failed_rows", "error_report", "status", "updated_at"]
        )

        return Response(
            {
                "id": str(record.id),
                "status": "completed",
                "async": False,
                "created": created,
                "skipped": skipped,
                "failed": failed + preview.invalid_count,
                "total": preview.total,
                "errors": all_errors[:MAX_STORED_ERRORS],
            },
            status=status.HTTP_201_CREATED,
        )
