# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reconcile ProjectIdentifier rows with the identifier their project actually uses.

Until now the row was written once at creation and never touched again, so renaming a
project left the old identifier claimed by a row nobody could see. The next project to
pick that identifier passed validation and then died on the unique constraint, half
created. Rows are keyed one-to-one on project, so a rename moves the existing row rather
than creating a second one.
"""

from django.db import migrations
from django.utils import timezone


def sync_project_identifiers(apps, schema_editor):
    Project = apps.get_model("db", "Project")
    ProjectIdentifier = apps.get_model("db", "ProjectIdentifier")
    now = timezone.now()

    rows = {row.project_id: row for row in ProjectIdentifier.objects.all()}
    live = {
        project.id: project
        for project in Project.objects.filter(deleted_at__isnull=True).only(
            "id", "identifier", "workspace_id", "created_by_id"
        )
    }

    # First park every row that no longer matches its project. A stale row can be holding
    # the identifier some other live project already uses, and renaming one project at a
    # time would hit the unique index the moment that project came up — aborting the
    # migration mid-deploy, in an order that depends on how the rows happen to be read.
    for project_id, row in rows.items():
        project = live.get(project_id)
        if project is not None and row.name == project.identifier and row.deleted_at is None:
            continue
        if row.deleted_at is None:
            row.deleted_at = now
            row.save(update_fields=["deleted_at"])

    # With the stale names out of the partial index, every live project can take its own:
    # two live projects cannot share an identifier, so there is nothing left to collide.
    for project_id, project in live.items():
        row = rows.get(project_id)

        if row is None:
            ProjectIdentifier.objects.create(
                name=project.identifier,
                project_id=project.id,
                workspace_id=project.workspace_id,
                created_by_id=project.created_by_id,
            )
            continue

        if row.name != project.identifier or row.deleted_at is not None:
            row.name = project.identifier
            row.deleted_at = None
            row.save(update_fields=["name", "deleted_at"])


class Migration(migrations.Migration):
    dependencies = [("db", "0122_issueimport")]

    operations = [migrations.RunPython(sync_project_identifiers, migrations.RunPython.noop)]
