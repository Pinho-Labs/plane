# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Unit coverage for ProjectIdentifier.is_taken / .claim.

Both APIs delegate their identifier rule to these two helpers, so a defect here reaches
every creation and rename path at once. The branches below are the ones the contract
tests cannot reach through HTTP.
"""

import pytest
from django.utils import timezone

from plane.db.models import Project, ProjectIdentifier, Workspace, WorkspaceMember


@pytest.fixture
def project(db, workspace, create_user):
    return Project.objects.create(
        name="Site", identifier="SIPL", workspace=workspace, created_by=create_user
    )


@pytest.fixture
def other_workspace(db, create_user):
    workspace = Workspace.objects.create(name="Other", owner=create_user, slug="other-workspace")
    WorkspaceMember.objects.create(workspace=workspace, member=create_user, role=20)
    return workspace


@pytest.mark.unit
@pytest.mark.django_db
class TestIsTaken:
    def test_identifier_of_an_existing_project_is_taken(self, project, workspace):
        assert ProjectIdentifier.is_taken("SIPL", workspace.id) is True

    def test_identifier_held_only_by_a_leftover_claim_is_taken(self, project, workspace, create_user):
        """The claim outliving its project is exactly what broke creation in production."""
        ProjectIdentifier.objects.create(
            name="PINHOLABS", project=project, workspace=workspace, created_by=create_user
        )
        Project.objects.filter(id=project.id).update(identifier="SIPL")

        assert ProjectIdentifier.is_taken("PINHOLABS", workspace.id) is True

    def test_excluded_project_does_not_conflict_with_itself(self, project, workspace, create_user):
        ProjectIdentifier.claim(project)

        assert ProjectIdentifier.is_taken("SIPL", workspace.id, exclude_project_id=project.id) is False

    def test_another_workspace_is_not_blocked(self, project, other_workspace):
        """Identifiers are scoped per workspace; a global check would block legitimate creates."""
        assert ProjectIdentifier.is_taken("SIPL", other_workspace.id) is False

    def test_case_and_padding_are_normalised(self, project, workspace):
        assert ProjectIdentifier.is_taken("  sipl  ", workspace.id) is True

    def test_empty_input_is_not_taken(self, workspace):
        assert ProjectIdentifier.is_taken("", workspace.id) is False
        assert ProjectIdentifier.is_taken(None, workspace.id) is False


@pytest.mark.unit
@pytest.mark.django_db
class TestClaim:
    def test_creates_the_row_when_missing(self, project, workspace):
        ProjectIdentifier.claim(project)

        assert [row.name for row in ProjectIdentifier.objects.filter(project=project)] == ["SIPL"]

    def test_moves_an_existing_row(self, project, workspace, create_user):
        ProjectIdentifier.objects.create(
            name="PINHOLABS", project=project, workspace=workspace, created_by=create_user
        )

        ProjectIdentifier.claim(project)

        assert [row.name for row in ProjectIdentifier.objects.filter(project=project)] == ["SIPL"]

    def test_revives_a_soft_deleted_row(self, project, workspace, create_user):
        """One-to-one means a soft-deleted row still holds the slot.

        Inserting a second one would violate the uniqueness of project_id, so the row has
        to be reused. Nothing reaches this branch over HTTP, which is why it is here.
        """
        row = ProjectIdentifier.objects.create(
            name="PINHOLABS", project=project, workspace=workspace, created_by=create_user
        )
        ProjectIdentifier.objects.filter(id=row.id).update(deleted_at=timezone.now())

        ProjectIdentifier.claim(project)

        assert ProjectIdentifier.all_objects.filter(project=project).count() == 1
        assert [row.name for row in ProjectIdentifier.objects.filter(project=project)] == ["SIPL"]

    def test_is_idempotent(self, project):
        ProjectIdentifier.claim(project)
        ProjectIdentifier.claim(project)

        assert ProjectIdentifier.all_objects.filter(project=project).count() == 1
