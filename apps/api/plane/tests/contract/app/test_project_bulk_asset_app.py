# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for ``ProjectBulkAssetEndpoint``.

A project cover is uploaded from the create-project modal *before* the project
exists, so it is stored with ``project_id`` NULL and only gets claimed here.

Scoping the lookup to ``project_id=project_id`` (the GHSA-qw87 IDOR fix) made
that claim impossible: the cover never matched, so creating a project answered
404 and left ``cover_image_asset`` NULL. These tests pin both halves — the claim
has to work, and assets owned by another project have to stay unreachable.
"""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    FileAsset,
    Project,
    ProjectMember,
    User,
    WorkspaceMember,
)


def make_project(workspace, user, name, identifier):
    project = Project.objects.create(
        name=name,
        identifier=identifier,
        workspace=workspace,
        created_by=user,
    )
    ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=20)
    return project


def make_cover_asset(workspace, user, project=None):
    return FileAsset.objects.create(
        attributes={"name": "cover.jpg", "type": "image/jpeg", "size": 2048},
        asset=f"{workspace.id}/{uuid4().hex}-cover.jpg",
        size=2048,
        workspace=workspace,
        project=project,
        created_by=user,
        entity_type=FileAsset.EntityTypeContext.PROJECT_COVER,
        is_uploaded=True,
        storage_metadata={"size": 2048},
    )


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Test Project", "TP")


@pytest.fixture
def other_project(db, workspace, create_user):
    """A second project in the same workspace, to prove cross-project reach is denied."""
    return make_project(workspace, create_user, "Other Project", "OP")


@pytest.fixture
def outsider_client(db, workspace):
    """Session client for a workspace member who belongs to no project."""
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"outsider-{unique_id}@plane.so",
        username=f"outsider_{unique_id}",
        first_name="Outsider",
        last_name="User",
    )
    user.set_password("test-password")
    user.save()
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def bulk_url(slug, project_id, entity_id):
    return f"/api/assets/v2/workspaces/{slug}/projects/{project_id}/{entity_id}/bulk/"


@pytest.mark.contract
class TestProjectBulkAssetCover:
    @pytest.mark.django_db
    def test_unassigned_cover_is_claimed_by_the_project(
        self, session_client, workspace, project, create_user
    ):
        """Regression: this 404 surfaced in the UI as a failed project creation."""
        asset = make_cover_asset(workspace, create_user)
        assert asset.project_id is None

        response = session_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": [str(asset.id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        asset.refresh_from_db()
        project.refresh_from_db()
        assert asset.project_id == project.id
        assert project.cover_image_asset_id == asset.id

    @pytest.mark.django_db
    def test_cover_already_owned_by_the_project_still_binds(
        self, session_client, workspace, project, create_user
    ):
        """The settings flow uploads with the project id already set; it must keep working."""
        asset = make_cover_asset(workspace, create_user, project=project)

        response = session_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": [str(asset.id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        project.refresh_from_db()
        assert project.cover_image_asset_id == asset.id

    @pytest.mark.django_db
    def test_cover_owned_by_another_project_cannot_be_stolen(
        self, session_client, workspace, project, other_project, create_user
    ):
        """IDOR guard: accepting unassigned assets must not reach assets owned elsewhere."""
        asset = make_cover_asset(workspace, create_user, project=other_project)

        response = session_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": [str(asset.id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        asset.refresh_from_db()
        project.refresh_from_db()
        assert asset.project_id == other_project.id
        assert project.cover_image_asset_id is None

    @pytest.mark.django_db
    def test_claiming_denied_for_non_project_member(
        self, outsider_client, workspace, project, create_user
    ):
        asset = make_cover_asset(workspace, create_user)

        response = outsider_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": [str(asset.id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        asset.refresh_from_db()
        assert asset.project_id is None

    @pytest.mark.django_db
    def test_missing_asset_ids_is_rejected(self, session_client, workspace, project):
        response = session_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": []},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_unknown_asset_id_is_not_found(self, session_client, workspace, project):
        response = session_client.post(
            bulk_url(workspace.slug, project.id, project.id),
            {"asset_ids": [str(uuid4())]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
