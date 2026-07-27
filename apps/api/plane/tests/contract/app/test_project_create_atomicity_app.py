# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the atomicity of project creation and update on the app API.

Both paths write several rows in sequence. Without a transaction any failure past the
first write stayed committed while the response said the operation had failed — the
shape of the bug that started this: an opaque error over a project the user could
already see in the sidebar.

Update matters for the same reason creation does: saving also moves the identifier
claim, so a partial write leaves a project renamed with its old identifier still taken.
"""

from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import Project, ProjectIdentifier, ProjectMember, State


def projects_url(slug, pk=None):
    base = f"/api/workspaces/{slug}/projects/"
    return f"{base}{pk}/" if pk else base


@pytest.mark.contract
class TestProjectCreateAtomicity:
    @pytest.mark.django_db
    def test_failure_after_save_leaves_nothing_behind(self, session_client, workspace, create_user):
        """Force the failure past the point where a partial project used to survive."""
        with (
            mock.patch(
                "plane.app.views.project.base.State.objects.bulk_create",
                side_effect=RuntimeError("forced failure for rollback test"),
            ),
            mock.patch("plane.app.views.project.base.model_activity") as mocked_activity,
        ):
            response = session_client.post(
                projects_url(workspace.slug), {"name": "Rollback Probe", "identifier": "RB"}, format="json"
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert not Project.objects.filter(workspace=workspace).exists()
        assert not ProjectMember.objects.filter(workspace=workspace).exists()
        assert not State.objects.filter(workspace=workspace).exists()
        # registered with on_commit, so a rollback must leave it undispatched
        mocked_activity.delay.assert_not_called()

    @pytest.mark.django_db
    def test_rolled_back_identifier_stays_available(self, session_client, workspace):
        """A failed attempt must not burn the identifier for the retry."""
        with mock.patch(
            "plane.app.views.project.base.State.objects.bulk_create",
            side_effect=RuntimeError("forced failure for rollback test"),
        ):
            failed = session_client.post(
                projects_url(workspace.slug), {"name": "Rollback Probe", "identifier": "RB"}, format="json"
            )
        assert failed.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        retried = session_client.post(
            projects_url(workspace.slug), {"name": "Rollback Probe", "identifier": "RB"}, format="json"
        )

        assert retried.status_code == status.HTTP_201_CREATED, (
            f"Got {retried.status_code}: {getattr(retried, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_successful_creation_still_reports_the_activity(self, session_client, workspace, django_capture_on_commit_callbacks):
        """The deferred dispatch has to actually fire once the commit lands."""
        with (
            mock.patch("plane.app.views.project.base.model_activity") as mocked_activity,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = session_client.post(
                projects_url(workspace.slug), {"name": "Happy Path", "identifier": "HP"}, format="json"
            )

        assert response.status_code == status.HTTP_201_CREATED, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        mocked_activity.delay.assert_called_once()


@pytest.mark.contract
class TestProjectUpdateAtomicity:
    @pytest.fixture
    def project_id(self, session_client, workspace):
        created = session_client.post(
            projects_url(workspace.slug), {"name": "Site", "identifier": "SIPL"}, format="json"
        )
        assert created.status_code == status.HTTP_201_CREATED
        return created.data["id"]

    @pytest.mark.django_db
    def test_failed_rename_leaves_neither_half_applied(self, session_client, workspace, project_id):
        """A rename that fails must not land with the identifier claim out of step."""
        with (
            mock.patch(
                "plane.app.views.project.base.Intake.objects.filter",
                side_effect=RuntimeError("forced failure for rollback test"),
            ),
            mock.patch("plane.app.views.project.base.model_activity") as mocked_activity,
        ):
            response = session_client.patch(
                projects_url(workspace.slug, project_id),
                {"identifier": "PINHOLABS", "inbox_view": True},
                format="json",
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert Project.objects.get(id=project_id).identifier == "SIPL"
        assert [row.name for row in ProjectIdentifier.objects.filter(project_id=project_id)] == ["SIPL"]
        mocked_activity.delay.assert_not_called()

    @pytest.mark.django_db
    def test_failure_moving_the_claim_rolls_the_rename_back(self, session_client, workspace, project_id):
        """The precise scenario the transaction exists for.

        The rename and the claim move are two writes inside save(); the test above forces
        the failure after save() and so would still pass if only that outer step were
        protected.
        """
        with mock.patch(
            "plane.app.serializers.project.ProjectIdentifier.claim",
            side_effect=RuntimeError("forced failure for rollback test"),
        ):
            response = session_client.patch(
                projects_url(workspace.slug, project_id), {"identifier": "PINHOLABS"}, format="json"
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert Project.objects.get(id=project_id).identifier == "SIPL"

    @pytest.mark.django_db
    def test_successful_update_still_reports_the_activity(
        self, session_client, workspace, project_id, django_capture_on_commit_callbacks
    ):
        with (
            mock.patch("plane.app.views.project.base.model_activity") as mocked_activity,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = session_client.patch(
                projects_url(workspace.slug, project_id), {"name": "Site Institucional"}, format="json"
            )

        assert response.status_code == status.HTTP_200_OK, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        mocked_activity.delay.assert_called_once()
