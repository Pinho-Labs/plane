# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for identifier bookkeeping on the token API.

This path had its own divergent copy of the rule: creation checked ProjectIdentifier but
never wrote a row, so projects created here left the identifier unregistered and the
check blind; renaming validated nothing at all and left the old claim behind. Both now
go through ProjectIdentifier.is_taken / .claim, the same helpers the app API uses.
"""

from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import Project, ProjectIdentifier


def projects_url(slug, pk=None):
    base = f"/api/v1/workspaces/{slug}/projects/"
    return f"{base}{pk}/" if pk else base


def create_project(client, slug, name, identifier):
    return client.post(projects_url(slug), {"name": name, "identifier": identifier}, format="json")


@pytest.mark.contract
class TestTokenApiProjectIdentifier:
    @pytest.mark.django_db
    def test_creation_registers_the_identifier(self, api_key_client, workspace):
        response = create_project(api_key_client, workspace.slug, "Site", "SIPL")

        assert response.status_code == status.HTTP_201_CREATED, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        rows = ProjectIdentifier.objects.filter(workspace=workspace, project_id=response.data["id"])
        assert [row.name for row in rows] == ["SIPL"]

    @pytest.mark.django_db
    def test_rename_moves_the_identifier_row(self, api_key_client, workspace):
        created = create_project(api_key_client, workspace.slug, "Site", "PINHOLABS")
        assert created.status_code == status.HTTP_201_CREATED

        renamed = api_key_client.patch(
            projects_url(workspace.slug, created.data["id"]), {"identifier": "SIPL"}, format="json"
        )

        assert renamed.status_code == status.HTTP_200_OK, (
            f"Got {renamed.status_code}: {getattr(renamed, 'data', None)!r}"
        )
        rows = ProjectIdentifier.objects.filter(workspace=workspace, project_id=created.data["id"])
        assert [row.name for row in rows] == ["SIPL"]

    @pytest.mark.django_db
    def test_identifier_freed_by_a_rename_can_be_reused(self, api_key_client, workspace):
        created = create_project(api_key_client, workspace.slug, "Site", "PINHOLABS")
        assert created.status_code == status.HTTP_201_CREATED

        renamed = api_key_client.patch(
            projects_url(workspace.slug, created.data["id"]), {"identifier": "SIPL"}, format="json"
        )
        assert renamed.status_code == status.HTTP_200_OK

        reused = create_project(api_key_client, workspace.slug, "Pinho Labs", "PINHOLABS")

        assert reused.status_code == status.HTTP_201_CREATED, (
            f"Got {reused.status_code}: {getattr(reused, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_rename_onto_a_taken_identifier_is_rejected(self, api_key_client, workspace):
        """Renaming was unchecked, so this used to reach the database constraint."""
        first = create_project(api_key_client, workspace.slug, "Site", "SIPL")
        second = create_project(api_key_client, workspace.slug, "Other", "OTHR")
        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED

        response = api_key_client.patch(
            projects_url(workspace.slug, second.data["id"]), {"identifier": "SIPL"}, format="json"
        )

        # 409 with an identifier-shaped body is this API's contract for the conflict; the
        # name-shaped 409 next to it is the IntegrityError path, i.e. the constraint catching
        # what validation should have
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "identifier" in response.data, f"reached via the database, not validation: {response.data!r}"
        assert Project.objects.get(id=second.data["id"]).identifier == "OTHR"

    @pytest.mark.django_db
    def test_resending_the_current_identifier_is_not_a_conflict(self, api_key_client, workspace):
        """Clients that PATCH the whole object resend the identifier unchanged.

        The new uniqueness check has to exclude the project being updated, or every such
        call starts answering 409.
        """
        created = create_project(api_key_client, workspace.slug, "Site", "SIPL")
        assert created.status_code == status.HTTP_201_CREATED

        response = api_key_client.patch(
            projects_url(workspace.slug, created.data["id"]),
            {"name": "Site Institucional", "identifier": "SIPL"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_failed_rename_leaves_neither_half_applied(self, api_key_client, workspace):
        """Adding the claim move to this path made an atomicity gap here too.

        Creation on this endpoint was already wrapped; the update was not, so a failure
        between renaming and moving the claim would leave the old identifier taken.
        """
        created = create_project(api_key_client, workspace.slug, "Site", "SIPL")
        assert created.status_code == status.HTTP_201_CREATED

        with mock.patch(
            "plane.api.serializers.project.ProjectIdentifier.claim",
            side_effect=RuntimeError("forced failure for rollback test"),
        ):
            response = api_key_client.patch(
                projects_url(workspace.slug, created.data["id"]), {"identifier": "PINHOLABS"}, format="json"
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert Project.objects.get(id=created.data["id"]).identifier == "SIPL"
        assert [row.name for row in ProjectIdentifier.objects.filter(project_id=created.data["id"])] == ["SIPL"]

    @pytest.mark.django_db
    def test_creation_sees_an_identifier_already_used_by_a_project(self, api_key_client, workspace):
        """Creation only consulted the claim table, which this path never populated."""
        assert create_project(api_key_client, workspace.slug, "Site", "SIPL").status_code == (
            status.HTTP_201_CREATED
        )
        ProjectIdentifier.objects.filter(workspace=workspace, name="SIPL").delete()

        response = create_project(api_key_client, workspace.slug, "Other", "SIPL")

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "identifier" in response.data, f"reached via the database, not validation: {response.data!r}"
