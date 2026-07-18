# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging

# Third party imports
from celery import shared_task

# Module imports
from plane.db.models import IssueImport, Project, User
from plane.utils.importers.context import build_resolution_context
from plane.utils.importers.csv_issue_importer import build_preview
from plane.utils.importers.runner import MAX_STORED_ERRORS, create_rows, serialize_errors

logger = logging.getLogger("plane.worker")


@shared_task
def issue_import_task(importer_id, csv_text, user_id, slug, origin):
    """Run a large CSV work-item import in the background.

    The view has already validated the file (file-level + invalid-row checks)
    before enqueuing, so this task imports the valid rows and records any row
    that fails at creation time. Invalid rows are skipped, never fatal.
    """
    try:
        record = IssueImport.objects.get(id=importer_id)
    except IssueImport.DoesNotExist:
        logger.warning("issue_import_task: IssueImport %s not found", importer_id)
        return

    record.status = "processing"
    record.save(update_fields=["status", "updated_at"])

    try:
        project = Project.objects.get(id=record.project_id)
        user = User.objects.get(id=user_id)

        ctx = build_resolution_context(project, user_id)
        preview = build_preview(csv_text, ctx)

        created, skipped, failed, row_errors = create_rows(user, slug, origin, project, preview.valid_rows)

        all_errors = serialize_errors(preview.errors) + row_errors
        record.created_rows = created
        record.skipped_rows = skipped
        record.failed_rows = failed + preview.invalid_count
        record.error_report = all_errors[:MAX_STORED_ERRORS]
        record.status = "completed"
        record.save(
            update_fields=["created_rows", "skipped_rows", "failed_rows", "error_report", "status", "updated_at"]
        )
    except Exception as exc:  # noqa: BLE001 - record the failure instead of silently dying
        logger.exception("issue_import_task failed for importer %s", importer_id)
        record.status = "failed"
        record.error_report = [{"row": 0, "field": "task", "message": str(exc)}]
        record.save(update_fields=["status", "error_report", "updated_at"])
        raise
