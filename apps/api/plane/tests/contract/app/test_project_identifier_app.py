# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for how project creation and renaming maintain ProjectIdentifier.

The row used to be written once at creation and never touched again, so renaming a
project left the old identifier claimed by a row nobody could see. Validation only
consulted Project.identifier, so the next project to pick that identifier passed, was
inserted, and then died on the unique constraint — surfacing as an opaque
"The payload is not valid" over a project that had already been created.
"""

import pytest
from rest_framework import status

from plane.db.models import Project, ProjectIdentifier


def projects_url(slug, pk=None):
    base = f"/api/workspaces/{slug}/projects/"
    return f"{base}{pk}/" if pk else base


def create_project(client, slug, name, identifier):
    return client.post(projects_url(slug), {"name": name, "identifier": identifier}, format="json")


@pytest.mark.contract
class TestProjectIdentifierLifecycle:
    @pytest.mark.django_db
    def test_rename_moves_the_identifier_row(self, session_client, workspace):
        created = create_project(session_client, workspace.slug, "Site", "PINHOLABS")
        assert created.status_code == status.HTTP_201_CREATED
        project_id = created.data["id"]

        renamed = session_client.patch(
            projects_url(workspace.slug, project_id), {"identifier": "SIPL"}, format="json"
        )

        assert renamed.status_code == status.HTTP_200_OK, (
            f"Got {renamed.status_code}: {getattr(renamed, 'data', None)!r}"
        )
        rows = ProjectIdentifier.objects.filter(workspace=workspace, project_id=project_id)
        assert [row.name for row in rows] == ["SIPL"]

    @pytest.mark.django_db
    def test_identifier_freed_by_a_rename_can_be_reused(self, session_client, workspace):
        """Regression: this is the production failure, end to end."""
        created = create_project(session_client, workspace.slug, "Site", "PINHOLABS")
        assert created.status_code == status.HTTP_201_CREATED

        renamed = session_client.patch(
            projects_url(workspace.slug, created.data["id"]), {"identifier": "SIPL"}, format="json"
        )
        assert renamed.status_code == status.HTTP_200_OK

        reused = create_project(session_client, workspace.slug, "Pinho Labs", "PINHOLABS")

        assert reused.status_code == status.HTTP_201_CREATED, (
            f"Got {reused.status_code}: {getattr(reused, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_identifier_claimed_by_a_stale_row_is_rejected_cleanly(self, session_client, workspace):
        """A leftover row must produce a field error, not a half-created project."""
        created = create_project(session_client, workspace.slug, "Site", "PINHOLABS")
        assert created.status_code == status.HTTP_201_CREATED

        # simulate the pre-fix state: the project moved on, the row stayed behind
        Project.objects.filter(id=created.data["id"]).update(identifier="SIPL")

        response = create_project(session_client, workspace.slug, "Pinho Labs", "PINHOLABS")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "PROJECT_IDENTIFIER_ALREADY_EXIST" in str(response.data)
        assert not Project.objects.filter(workspace=workspace, name="Pinho Labs").exists()

    @pytest.mark.django_db
    def test_updating_a_project_without_touching_its_identifier(self, session_client, workspace):
        """Its own row must not read as a conflict."""
        created = create_project(session_client, workspace.slug, "Site", "SIPL")
        assert created.status_code == status.HTTP_201_CREATED

        response = session_client.patch(
            projects_url(workspace.slug, created.data["id"]),
            {"name": "Site Institucional", "identifier": "SIPL"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        rows = ProjectIdentifier.objects.filter(workspace=workspace, project_id=created.data["id"])
        assert [row.name for row in rows] == ["SIPL"]

    @pytest.mark.django_db
    def test_differently_cased_duplicate_is_rejected(self, session_client, workspace):
        """Project.save() upper-cases, so a lower-case duplicate used to reach the constraint."""
        assert create_project(session_client, workspace.slug, "Site", "SIPL").status_code == (
            status.HTTP_201_CREATED
        )

        response = create_project(session_client, workspace.slug, "Other", "sipl")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "PROJECT_IDENTIFIER_ALREADY_EXIST" in str(response.data)
