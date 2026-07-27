# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Unit coverage for the 0123 data migration that reconciles ProjectIdentifier rows.

The suite runs with --nomigrations, so the migration never executes on its own. The
reconciliation function is called directly against the real app registry instead.

Caveat: on the real models ``ProjectIdentifier.objects`` is the soft-delete manager,
whereas a migration gets a plain one. Rows already soft-deleted are therefore invisible
here, so the "resurrect a soft-deleted row for a live project" branch is not exercised.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps

from plane.db.models import Project, ProjectIdentifier, Workspace, WorkspaceMember

sync_project_identifiers = import_module(
    "plane.db.migrations.0123_sync_project_identifiers"
).sync_project_identifiers


@pytest.fixture
def project(db, workspace, create_user):
    return Project.objects.create(
        name="Site", identifier="SIPL", workspace=workspace, created_by=create_user
    )


@pytest.mark.unit
@pytest.mark.django_db
def test_stale_row_is_renamed_to_the_current_identifier(project, workspace, create_user):
    """The production state: the project moved to SIPL, the row still claims PINHOLABS."""
    ProjectIdentifier.objects.create(
        name="PINHOLABS", project=project, workspace=workspace, created_by=create_user
    )

    sync_project_identifiers(global_apps, None)

    rows = ProjectIdentifier.objects.filter(workspace=workspace)
    assert [(row.name, row.project_id) for row in rows] == [("SIPL", project.id)]


@pytest.mark.unit
@pytest.mark.django_db
def test_missing_row_is_created(project, workspace):
    assert not ProjectIdentifier.objects.filter(project=project).exists()

    sync_project_identifiers(global_apps, None)

    rows = ProjectIdentifier.objects.filter(project=project)
    assert [row.name for row in rows] == ["SIPL"]


@pytest.mark.unit
@pytest.mark.django_db
def test_row_of_a_deleted_project_stops_claiming_its_identifier(project, workspace, create_user):
    ProjectIdentifier.objects.create(
        name="SIPL", project=project, workspace=workspace, created_by=create_user
    )
    Project.objects.filter(id=project.id).update(deleted_at="2026-07-27T00:00:00Z")

    sync_project_identifiers(global_apps, None)

    assert not ProjectIdentifier.objects.filter(name="SIPL", workspace=workspace).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_running_twice_changes_nothing(project, workspace, create_user):
    ProjectIdentifier.objects.create(
        name="PINHOLABS", project=project, workspace=workspace, created_by=create_user
    )

    sync_project_identifiers(global_apps, None)
    first = list(ProjectIdentifier.objects.filter(workspace=workspace).values("name", "project_id"))
    sync_project_identifiers(global_apps, None)

    assert list(ProjectIdentifier.objects.filter(workspace=workspace).values("name", "project_id")) == first


@pytest.mark.unit
@pytest.mark.django_db
def test_stale_claim_colliding_with_a_live_project(workspace, create_user):
    """A leftover claim can hold the identifier a different live project already uses.

    Renaming the rows one project at a time hits the unique index whenever the colliding
    project is reached first, which would abort the migration mid-deploy.
    """
    renamed = Project.objects.create(
        name="Renamed", identifier="LATER", workspace=workspace, created_by=create_user
    )
    ProjectIdentifier.objects.create(
        name="TAKEN", project=renamed, workspace=workspace, created_by=create_user
    )
    holder = Project.objects.create(
        name="Holder", identifier="TAKEN", workspace=workspace, created_by=create_user
    )

    sync_project_identifiers(global_apps, None)

    rows = {row.project_id: row.name for row in ProjectIdentifier.objects.filter(workspace=workspace)}
    assert rows == {holder.id: "TAKEN", renamed.id: "LATER"}


@pytest.fixture
def other_workspace(db, create_user):
    workspace = Workspace.objects.create(name="Other", owner=create_user, slug="other-workspace")
    WorkspaceMember.objects.create(workspace=workspace, member=create_user, role=20)
    return workspace


@pytest.mark.unit
@pytest.mark.django_db
def test_two_projects_holding_each_others_identifier(workspace, create_user):
    """The hardest shape: the stale rows form a cycle.

    Neither project can take its identifier until the other lets go, so any approach that
    resolves one project at a time deadlocks on the unique index whichever way it starts.
    """
    first = Project.objects.create(
        name="First", identifier="AAA", workspace=workspace, created_by=create_user
    )
    second = Project.objects.create(
        name="Second", identifier="BBB", workspace=workspace, created_by=create_user
    )
    ProjectIdentifier.objects.create(
        name="BBB", project=first, workspace=workspace, created_by=create_user
    )
    ProjectIdentifier.objects.create(
        name="AAA", project=second, workspace=workspace, created_by=create_user
    )

    sync_project_identifiers(global_apps, None)

    rows = {row.project_id: row.name for row in ProjectIdentifier.objects.filter(workspace=workspace)}
    assert rows == {first.id: "AAA", second.id: "BBB"}


@pytest.mark.unit
@pytest.mark.django_db
def test_same_identifier_in_two_workspaces_is_left_alone(workspace, other_workspace, create_user):
    """Identifiers are scoped per workspace: reconciling one must not disturb the other."""
    here = Project.objects.create(
        name="Here", identifier="SIPL", workspace=workspace, created_by=create_user
    )
    there = Project.objects.create(
        name="There", identifier="SIPL", workspace=other_workspace, created_by=create_user
    )

    sync_project_identifiers(global_apps, None)

    assert [r.name for r in ProjectIdentifier.objects.filter(project=here)] == ["SIPL"]
    assert [r.name for r in ProjectIdentifier.objects.filter(project=there)] == ["SIPL"]
