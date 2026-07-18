# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Builds a `ResolutionContext` for the CSV importer from project-scoped queries.

This is the thin ORM adapter between the database and the pure parser in
`csv_issue_importer`: it pre-fetches every lookup the parser needs (states,
members, labels, cycles, modules, estimate points, parent identifiers, types)
so row resolution stays a set of in-memory dict lookups.
"""

from plane.db.models import (
    Cycle,
    EstimatePoint,
    Issue,
    IssueType,
    Label,
    Module,
    ProjectMember,
    State,
)
from plane.utils.importers.csv_issue_importer import ProjectFeatures, ResolutionContext


def user_can_create_labels(project_id, user_id):
    """Only project admins may create labels (mirrors LabelViewSet permission)."""
    return ProjectMember.objects.filter(
        project_id=project_id,
        member_id=user_id,
        role=20,  # ROLE.ADMIN
        is_active=True,
    ).exists()


def build_resolution_context(project, user_id):
    """Return a `ResolutionContext` populated from the given project.

    `project` is a fully-loaded Project instance (needs `identifier`, feature
    flags and `estimate_id`).
    """
    project_id = project.id

    state_by_name = {}
    default_state_id = None
    for state in State.objects.filter(project_id=project_id).values("id", "name", "default"):
        state_by_name[state["name"].strip().lower()] = str(state["id"])
        if state["default"]:
            default_state_id = str(state["id"])

    member_by_email = {
        row["member__email"].strip().lower(): str(row["member_id"])
        for row in ProjectMember.objects.filter(
            project_id=project_id, role__gte=15, is_active=True
        ).values("member_id", "member__email")
        if row["member__email"]
    }

    label_by_name = {
        row["name"].strip().lower(): str(row["id"])
        for row in Label.objects.filter(project_id=project_id).values("id", "name")
    }

    cycle_by_name = {
        row["name"].strip().lower(): str(row["id"])
        for row in Cycle.objects.filter(project_id=project_id).values("id", "name")
    }

    module_by_name = {
        row["name"].strip().lower(): str(row["id"])
        for row in Module.objects.filter(project_id=project_id).values("id", "name")
    }

    estimate_by_value = {}
    if project.estimate_id:
        estimate_by_value = {
            row["value"].strip().lower(): str(row["id"])
            for row in EstimatePoint.objects.filter(estimate_id=project.estimate_id).values("id", "value")
        }

    # Parent identifiers: PROJ-123 -> issue id. Built from all project issues so
    # a CSV can reference any existing work item as a parent.
    issue_by_identifier = {
        f"{project.identifier}-{row['sequence_id']}".upper(): str(row["id"])
        for row in Issue.objects.filter(project_id=project_id).values("id", "sequence_id")
    }

    type_by_name = {}
    if project.is_issue_type_enabled:
        type_by_name = {
            row["name"].strip().lower(): str(row["id"])
            for row in IssueType.objects.filter(
                project_issue_types__project_id=project_id, is_active=True
            ).values("id", "name")
        }

    return ResolutionContext(
        state_by_name=state_by_name,
        default_state_id=default_state_id,
        member_by_email=member_by_email,
        label_by_name=label_by_name,
        cycle_by_name=cycle_by_name,
        module_by_name=module_by_name,
        estimate_by_value=estimate_by_value,
        issue_by_identifier=issue_by_identifier,
        type_by_name=type_by_name,
        can_create_labels=user_can_create_labels(project_id, user_id),
        features=ProjectFeatures(
            cycle_view=project.cycle_view,
            module_view=project.module_view,
            estimates_enabled=project.estimate_id is not None,
            work_item_types_enabled=project.is_issue_type_enabled,
        ),
    )
