# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import csv
from io import StringIO
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    CycleIssue,
    Issue,
    IssueImport,
    IssueLabel,
    Label,
    ModuleIssue,
    Project,
    ProjectMember,
    State,
    User,
)

# Activity/webhook side effects live in the shared runner (used by both the
# sync view and the async task), so they are patched there.
ACTIVITY_PATH = "plane.utils.importers.runner.issue_activity"
MODEL_ACTIVITY_PATH = "plane.utils.importers.runner.model_activity"
IMPORT_TASK_PATH = "plane.app.views.issue.import_csv.issue_import_task"
THRESHOLD_PATH = "plane.app.views.issue.import_csv.SYNC_ROW_THRESHOLD"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def project(db, workspace, create_user):
    """A project the test user administers, with two states and one label."""
    project = Project.objects.create(
        name="Import Project",
        identifier="PROJ",
        workspace=workspace,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(
        project=project, workspace=workspace, name="Todo", group="unstarted", default=True
    )
    State.objects.create(
        project=project, workspace=workspace, name="In Progress", group="started", default=False
    )
    Label.objects.create(project=project, workspace=workspace, name="bug")
    return project


@pytest.fixture
def outsider_client(db, workspace):
    """An authenticated client for a user who is NOT a member of `project`."""
    outsider = User.objects.create(
        email="outsider@plane.so", username="outsider", first_name="Out", last_name="Sider"
    )
    client = APIClient()
    client.force_authenticate(user=outsider)
    return client


@pytest.fixture
def member_client(db, workspace, project):
    """A client for a project MEMBER (role 15) — allowed to import but NOT to create labels."""
    member = User.objects.create(email="member@plane.so", username="member", first_name="Mem", last_name="Ber")
    ProjectMember.objects.create(project=project, member=member, role=15, is_active=True)
    client = APIClient()
    client.force_authenticate(user=member)
    return client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _csv_bytes(headers, *rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _upload(content, name="import.csv"):
    return SimpleUploadedFile(name, content, content_type="text/csv")


def _base_url(slug, project_id):
    return f"/api/workspaces/{slug}/projects/{project_id}/issues/import-csv/"


# --------------------------------------------------------------------------- #
# Template
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVTemplate:
    @pytest.mark.django_db
    def test_download_template(self, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id) + "template/"
        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/csv"
        header_line = response.content.decode("utf-8").splitlines()[0]
        assert "Name" in header_line and "State" in header_line


# --------------------------------------------------------------------------- #
# Rules document (for AI-assisted CSV generation)
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVRules:
    @pytest.mark.django_db
    def test_rules_list_live_project_values(self, session_client, workspace, project, create_user):
        url = _base_url(workspace.slug, project.id) + "rules/"
        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        md = response.data["markdown"]
        # Required column, fixed priority list, and this project's live values.
        assert "Name — REQUIRED" in md
        assert "`urgent`" in md and "`none`" in md
        assert "`Todo`" in md and "`In Progress`" in md  # the project's states
        assert "`bug`" in md  # the project's label
        assert create_user.email in md  # assignable member
        # Cycles/modules are disabled on the fixture project -> flagged, not enumerated.
        assert "Not enabled for this project" in md

    @pytest.mark.django_db
    def test_rules_document_description_html_support(self, session_client, workspace, project):
        # The Description section must tell the LLM that HTML is supported but
        # markdown is not, so it emits HTML tags rather than literal `**bold**`.
        url = _base_url(workspace.slug, project.id) + "rules/"
        md = session_client.get(url).data["markdown"]
        assert "### Description — optional" in md
        assert "HTML" in md
        assert "Markdown is NOT interpreted" in md

    @pytest.mark.django_db
    def test_rules_enumerate_enabled_features(self, session_client, workspace, project, create_user):
        # Enable every optional feature and add one value each -> the rules doc
        # enumerates them instead of showing the "not enabled" note.
        from plane.db.models import Cycle, Estimate, EstimatePoint, IssueType, Module
        from plane.db.models.issue_type import ProjectIssueType

        project.cycle_view = True
        project.module_view = True
        project.is_issue_type_enabled = True
        estimate = Estimate.objects.create(project=project, workspace=workspace, name="Story Points", type="points")
        EstimatePoint.objects.create(estimate=estimate, project=project, workspace=workspace, key=0, value="5")
        project.estimate = estimate
        project.save()
        Cycle.objects.create(project=project, workspace=workspace, name="Sprint 9", owned_by=create_user)
        Module.objects.create(project=project, workspace=workspace, name="Payments")
        issue_type = IssueType.objects.create(workspace=workspace, name="Defect")
        ProjectIssueType.objects.create(project=project, workspace=workspace, issue_type=issue_type)

        url = _base_url(workspace.slug, project.id) + "rules/"
        md = session_client.get(url).data["markdown"]
        assert "Allowed cycles: `Sprint 9`" in md
        assert "Allowed modules: `Payments`" in md
        assert "Allowed values: `5`" in md  # estimate points
        assert "Allowed types: `Defect`" in md
        assert "Not enabled for this project" not in md  # nothing should be flagged as disabled

    @pytest.mark.django_db
    def test_rules_forbidden_for_non_member(self, outsider_client, workspace, project):
        url = _base_url(workspace.slug, project.id) + "rules/"
        assert outsider_client.get(url).status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Validate (dry run)
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVValidate:
    @pytest.mark.django_db
    def test_validate_happy_writes_nothing(self, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id) + "validate/"
        content = _csv_bytes(
            ["Name", "State", "Priority"],
            ["Task A", "Todo", "high"],
            ["Task B", "In Progress", "low"],
        )
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["total"] == 2
        assert response.data["valid"] == 2
        assert response.data["invalid"] == 0
        assert Issue.objects.filter(project=project).count() == 0  # dry run wrote nothing
        # The preview sample resolves ids back to display values for the table.
        sample = response.data["sample"]
        assert len(sample) == 2
        assert sample[0]["name"] == "Task A"
        assert sample[0]["state"]["name"] == "Todo"
        assert "color" in sample[0]["state"]
        assert sample[0]["priority"] == "high"
        assert response.data["invalid_sample"] == []
        assert response.data["sample_truncated"] is False

    @pytest.mark.django_db
    def test_validate_reports_row_errors(self, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id) + "validate/"
        content = _csv_bytes(
            ["Name", "State", "Priority"],
            ["Task A", "Nirvana", "high"],  # bad state
            ["", "Todo", "low"],  # missing name
        )
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] == 0
        assert response.data["invalid"] == 2
        fields = {e["field"] for e in response.data["errors"]}
        assert "State" in fields and "Name" in fields
        # Invalid rows come back with their raw cells + per-row errors for the table.
        invalid_sample = response.data["invalid_sample"]
        assert len(invalid_sample) == 2
        by_row = {r["row"]: r for r in invalid_sample}
        bad_state_row = next(r for r in invalid_sample if r["values"].get("state") == "Nirvana")
        assert any(e["field"] == "State" for e in bad_state_row["errors"])
        unnamed_row = next(r for r in invalid_sample if not r["name"])
        assert any(e["field"] == "Name" for e in unnamed_row["errors"])
        assert set(by_row) == {1, 2}

    @pytest.mark.django_db
    def test_validate_requires_file(self, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id) + "validate/"
        response = session_client.post(url, {}, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------- #
# Commit
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVCommit:
    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_commit_creates_issues(self, m_activity, m_model_activity, session_client, workspace, project, create_user):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(
            ["Name", "State", "Priority", "Assignees", "Labels"],
            ["Fix login", "In Progress", "high", create_user.email, "bug"],
            ["Add tests", "Todo", "low", "", ""],
        )
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["created"] == 2
        issues = Issue.objects.filter(project=project).order_by("sequence_id")
        assert issues.count() == 2
        # sequence numbering is assigned per row
        assert list(issues.values_list("sequence_id", flat=True)) == [1, 2]
        first = issues.first()
        assert first.state.name == "In Progress"
        assert first.priority == "high"
        assert IssueLabel.objects.filter(issue=first).count() == 1
        # side effects fired
        assert m_activity.delay.call_count == 2
        assert m_model_activity.delay.call_count == 2

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_commit_blocks_on_invalid_without_skip(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State"], ["Good", "Todo"], ["Bad", "Nirvana"])
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Issue.objects.filter(project=project).count() == 0

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_commit_partial_with_skip_invalid(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State"], ["Good", "Todo"], ["Bad", "Nirvana"])
        response = session_client.post(url, {"file": _upload(content), "skip_invalid": "true"}, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] == 1
        assert response.data["failed"] == 1
        assert Issue.objects.filter(project=project).count() == 1

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_external_id_dedupe(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State", "External ID"], ["Task A", "Todo", "ext-1"])
        first = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert first.data["created"] == 1
        # Re-importing the same external id skips instead of duplicating.
        second = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert second.data["created"] == 0
        assert second.data["skipped"] == 1
        assert Issue.objects.filter(project=project).count() == 1

    @pytest.mark.django_db
    def test_missing_name_column_is_rejected(self, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["State", "Priority"], ["Todo", "high"])
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_admin_label_autocreate(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State", "Labels"], ["Task A", "Todo", "bug;backend"])
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] == 1
        assert Label.objects.filter(project=project, name="backend").exists()
        issue = Issue.objects.get(project=project)
        assert IssueLabel.objects.filter(issue=issue).count() == 2

    @pytest.mark.django_db
    def test_non_member_forbidden(self, outsider_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State"], ["Task A", "Todo"])
        response = outsider_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Module / cycle membership
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVMemberships:
    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_commit_creates_module_and_cycle_rows(self, _a, _m, session_client, workspace, project, create_user):
        from plane.db.models import Cycle, Module

        project.cycle_view = True
        project.module_view = True
        project.save()
        cycle = Cycle.objects.create(project=project, workspace=workspace, name="Sprint 5", owned_by=create_user)
        module = Module.objects.create(project=project, workspace=workspace, name="Auth")

        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State", "Cycle", "Modules"], ["Task A", "Todo", "Sprint 5", "Auth"])
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        issue = Issue.objects.get(project=project)
        assert CycleIssue.objects.filter(issue=issue, cycle=cycle).count() == 1
        assert ModuleIssue.objects.filter(issue=issue, module=module).count() == 1


# --------------------------------------------------------------------------- #
# Async path (large imports)
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVAsync:
    @pytest.mark.django_db
    @mock.patch(IMPORT_TASK_PATH)
    def test_large_import_dispatches_task(self, m_task, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State"], ["A", "Todo"], ["B", "Todo"])
        # Force the async branch with a threshold of 1 row.
        with mock.patch(THRESHOLD_PATH, 1):
            response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_202_ACCEPTED, response.data
        assert response.data["status"] == "queued"
        assert response.data["async"] is True
        m_task.delay.assert_called_once()
        # Nothing is created synchronously; the queued record awaits the worker.
        assert Issue.objects.filter(project=project).count() == 0
        record = IssueImport.objects.get(id=response.data["id"])
        assert record.status == "queued"

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_task_processes_import(self, _a, _m, workspace, project, create_user):
        from plane.bgtasks.issue_import_task import issue_import_task

        record = IssueImport.objects.create(
            project=project,
            workspace=workspace,
            file_name="big.csv",
            initiated_by=create_user,
            status="queued",
            total_rows=2,
        )
        csv_text = _csv_bytes(["Name", "State"], ["A", "Todo"], ["B", "In Progress"]).decode("utf-8")
        issue_import_task(
            importer_id=str(record.id),
            csv_text=csv_text,
            user_id=str(create_user.id),
            slug=workspace.slug,
            origin="http://localhost",
        )
        record.refresh_from_db()
        assert record.status == "completed"
        assert record.created_rows == 2
        assert Issue.objects.filter(project=project).count() == 2


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVHistory:
    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_history_lists_imports(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State"], ["Task A", "Todo"])
        session_client.post(url, {"file": _upload(content)}, format="multipart")

        response = session_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["created_rows"] == 1
        assert response.data[0]["status"] == "completed"
        assert IssueImport.objects.filter(project=project).count() == 1


# --------------------------------------------------------------------------- #
# Guards & field fidelity
# --------------------------------------------------------------------------- #
@pytest.mark.contract
class TestIssueCSVGuards:
    @pytest.mark.django_db
    def test_oversized_file_is_rejected(self, session_client, workspace, project):
        # An over-limit upload is rejected before any issue is created. Which layer
        # rejects it depends on config: Django's DATA_UPLOAD_MAX_MEMORY_SIZE
        # (= FILE_SIZE_LIMIT, 5MB default) returns 413 for bodies over the limit,
        # while the view's own MAX_FILE_SIZE guard returns 400. Either is correct.
        from plane.app.views.issue.import_csv import MAX_FILE_SIZE

        url = _base_url(workspace.slug, project.id)
        oversized = b"Name\n" + (b"a" * (MAX_FILE_SIZE + 10))
        response = session_client.post(url, {"file": _upload(oversized)}, format="multipart")
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        assert Issue.objects.filter(project=project).count() == 0

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_member_cannot_autocreate_labels(self, _a, _m, member_client, workspace, project):
        # A non-admin MEMBER may import, but an unknown label must fail the row
        # (not silently create the label), matching the admin-only label rule.
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(["Name", "State", "Labels"], ["Task A", "Todo", "brand-new-label"])
        response = member_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Label.objects.filter(project=project, name="brand-new-label").exists()
        assert Issue.objects.filter(project=project).count() == 0

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_parent_assignee_and_dates_are_persisted(self, _a, _m, session_client, workspace, project, create_user):
        from plane.db.models import IssueAssignee

        # First create a parent work item, then reference it as PROJ-1 with an
        # assignee (by email) and both dates in the same import.
        url = _base_url(workspace.slug, project.id)
        parent_csv = _csv_bytes(["Name", "State"], ["Parent item", "Todo"])
        session_client.post(url, {"file": _upload(parent_csv)}, format="multipart")
        parent = Issue.objects.get(project=project, name="Parent item")
        assert parent.sequence_id == 1

        child_csv = _csv_bytes(
            ["Name", "State", "Parent", "Assignees", "Start Date", "Target Date"],
            ["Child item", "In Progress", f"{project.identifier}-{parent.sequence_id}", create_user.email,
             "2026-07-20", "2026-07-25"],
        )
        response = session_client.post(url, {"file": _upload(child_csv)}, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        child = Issue.objects.get(project=project, name="Child item")
        assert child.parent_id == parent.id
        assert str(child.start_date) == "2026-07-20"
        assert str(child.target_date) == "2026-07-25"
        assert IssueAssignee.objects.filter(issue=child, assignee=create_user).count() == 1

    @pytest.mark.django_db
    @mock.patch(MODEL_ACTIVITY_PATH)
    @mock.patch(ACTIVITY_PATH)
    def test_start_after_target_fails_the_row(self, _a, _m, session_client, workspace, project):
        url = _base_url(workspace.slug, project.id)
        content = _csv_bytes(
            ["Name", "State", "Start Date", "Target Date"],
            ["Bad dates", "Todo", "2026-07-25", "2026-07-20"],
        )
        response = session_client.post(url, {"file": _upload(content)}, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Issue.objects.filter(project=project).count() == 0
