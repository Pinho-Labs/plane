# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared row-creation engine for the CSV importer.

Both the synchronous view path and the async Celery task call these functions,
so the logic is request-free: it takes a `user`, the workspace `slug`, and a
pre-computed `origin` string (from `base_host`) instead of a live request. This
keeps a single source of truth for how a work item is created from a parsed row.
"""

import json
import random

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from plane.app.serializers import IssueCreateSerializer
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import CycleIssue, Issue, Label, ModuleIssue

# Cap the number of error rows persisted on the IssueImport record.
MAX_STORED_ERRORS = 1000


def serialize_errors(errors):
    return [
        {"row": e.row, "field": e.field, "message": e.message, "code": e.code, "params": e.params} for e in errors
    ]


def create_rows(user, slug, origin, project, parsed_rows):
    """Create work items for every parsed row. Returns (created, skipped, failed, row_errors)."""
    created = skipped = failed = 0
    row_errors = []
    for parsed in parsed_rows:
        try:
            # Persist the row (and its memberships) atomically so a failure
            # rolls back cleanly without a half-created work item.
            with transaction.atomic():
                outcome, issue_id, safe_payload = _persist_row(user, project, parsed)
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
            failed += 1
            row_errors.append({"row": parsed.row_number, "field": "row", "message": str(exc)})
            continue

        if outcome == "skipped":
            skipped += 1
            continue

        created += 1
        # Fire side effects only after the row has committed.
        _fire_activity(user, slug, origin, project, issue_id, safe_payload)
    return created, skipped, failed, row_errors


def _persist_row(user, project, parsed):
    payload = dict(parsed.payload)

    # De-duplicate on external_id so re-importing the same file is safe.
    external_id = payload.get("external_id")
    if external_id and Issue.objects.filter(
        project_id=project.id, external_source="csv", external_id=external_id
    ).exists():
        return "skipped", None, None

    # Admin-only auto-create of labels that don't exist yet.
    if parsed.new_label_names:
        new_ids = _ensure_labels(user, project, parsed.new_label_names)
        payload["label_ids"] = list(payload.get("label_ids", [])) + new_ids

    serializer = IssueCreateSerializer(
        data=payload,
        context={
            "project_id": str(project.id),
            "workspace_id": str(project.workspace_id),
            "default_assignee_id": project.default_assignee_id,
        },
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    issue_id = serializer.data["id"]

    if parsed.module_ids:
        ModuleIssue.objects.bulk_create(
            [
                ModuleIssue(
                    issue_id=issue_id,
                    module_id=module_id,
                    project_id=project.id,
                    workspace_id=project.workspace_id,
                    created_by=user,
                    updated_by=user,
                )
                for module_id in parsed.module_ids
            ],
            batch_size=10,
            ignore_conflicts=True,
        )

    if parsed.cycle_id:
        CycleIssue.objects.create(
            issue_id=issue_id,
            cycle_id=parsed.cycle_id,
            project_id=project.id,
            workspace_id=project.workspace_id,
            created_by=user,
            updated_by=user,
        )

    safe_payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    return "created", issue_id, safe_payload


def _ensure_labels(user, project, names):
    ids = []
    for name in names:
        label, _ = Label.objects.get_or_create(
            project_id=project.id,
            name=name,
            defaults={
                "workspace_id": project.workspace_id,
                "color": f"#{random.randint(0, 0xFFFFFF + 1):06X}",
                "created_by": user,
                "updated_by": user,
            },
        )
        ids.append(str(label.id))
    return ids


def _fire_activity(user, slug, origin, project, issue_id, safe_payload):
    # Parity with IssueViewSet.create: activity log + notifications, and webhooks.
    issue_activity.delay(
        type="issue.activity.created",
        requested_data=json.dumps(safe_payload, cls=DjangoJSONEncoder),
        actor_id=str(user.id),
        issue_id=str(issue_id),
        project_id=str(project.id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
    )
    model_activity.delay(
        model_name="issue",
        model_id=str(issue_id),
        requested_data=safe_payload,
        current_instance=None,
        actor_id=user.id,
        slug=slug,
        origin=origin,
    )
