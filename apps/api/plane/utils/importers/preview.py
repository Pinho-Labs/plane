# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Serializes a dry-run `ImportPreview` into display-ready rows for the UI.

The parser resolves human-friendly CSV values to internal ids; this module does
the inverse for the preview table: it builds id -> display maps from the project
(state name+color, member name+avatar, label name+color, cycle/module names,
estimate value, work-item-type name) so the frontend renders each row exactly
like a real work item without having to load any of those stores itself.

Kept separate from the pure parser (`csv_issue_importer`) because it touches the
ORM, mirroring how `context.py` adapts the database to the pure resolver.
"""

from plane.db.models import (
    Cycle,
    EstimatePoint,
    IssueType,
    Label,
    Module,
    ProjectMember,
    State,
)
from plane.utils.importers.csv_issue_importer import FILE_LEVEL_ROW

# Empty rich-text the parser emits for a blank description; treated as "no body".
_EMPTY_DESCRIPTION = "<p></p>"


def build_display_maps(project):
    """Return id -> display dictionaries for every project-scoped reference."""
    project_id = project.id

    states = {
        str(s["id"]): {"name": s["name"], "color": s["color"]}
        for s in State.objects.filter(project_id=project_id).values("id", "name", "color")
    }
    members = {
        str(r["member_id"]): {
            "id": str(r["member_id"]),
            "display_name": r["member__display_name"],
            "avatar_url": r["member__avatar"] or None,
        }
        for r in ProjectMember.objects.filter(
            project_id=project_id, role__gte=15, is_active=True
        ).values("member_id", "member__display_name", "member__avatar")
    }
    labels = {
        str(label_row["id"]): {"name": label_row["name"], "color": label_row["color"] or None}
        for label_row in Label.objects.filter(project_id=project_id).values("id", "name", "color")
    }
    cycles = {str(c["id"]): c["name"] for c in Cycle.objects.filter(project_id=project_id).values("id", "name")}
    modules = {str(m["id"]): m["name"] for m in Module.objects.filter(project_id=project_id).values("id", "name")}

    estimates = {}
    if project.estimate_id:
        estimates = {
            str(e["id"]): e["value"]
            for e in EstimatePoint.objects.filter(estimate_id=project.estimate_id).values("id", "value")
        }

    types = {}
    if project.is_issue_type_enabled:
        types = {
            str(t["id"]): t["name"]
            for t in IssueType.objects.filter(
                project_issue_types__project_id=project_id, is_active=True
            ).values("id", "name")
        }

    return {
        "states": states,
        "members": members,
        "labels": labels,
        "cycles": cycles,
        "modules": modules,
        "estimates": estimates,
        "types": types,
    }


def serialize_valid_row(parsed, maps):
    """Turn a resolved `ParsedRow` into a display-ready dict for the preview table."""
    payload = parsed.payload

    labels = [maps["labels"][lid] for lid in payload.get("label_ids", []) if lid in maps["labels"]]
    # Labels an admin will auto-create don't exist yet, so they have no color.
    labels += [{"name": name, "color": None, "is_new": True} for name in parsed.new_label_names]

    description = payload.get("description_html") or ""

    return {
        "row": parsed.row_number,
        "name": payload.get("name", ""),
        "has_description": bool(description) and description != _EMPTY_DESCRIPTION,
        "priority": payload.get("priority", "none"),
        "state": maps["states"].get(payload.get("state_id")),
        "assignees": [maps["members"][a] for a in payload.get("assignee_ids", []) if a in maps["members"]],
        "labels": labels,
        "start_date": _iso(payload.get("start_date")),
        "target_date": _iso(payload.get("target_date")),
        "estimate": maps["estimates"].get(payload.get("estimate_point")),
        "cycle": maps["cycles"].get(parsed.cycle_id) if parsed.cycle_id else None,
        "modules": [maps["modules"][mid] for mid in parsed.module_ids if mid in maps["modules"]],
        "type": maps["types"].get(payload.get("type")),
    }


def serialize_invalid_rows(invalid_rows, errors):
    """Turn invalid rows + their errors into display dicts for the "with errors" view."""
    errors_by_row = {}
    for error in errors:
        if error.row == FILE_LEVEL_ROW:
            continue
        errors_by_row.setdefault(error.row, []).append(
            {"field": error.field, "message": error.message, "code": error.code, "params": error.params}
        )

    serialized = []
    for row_number, raw in invalid_rows:
        serialized.append(
            {
                "row": row_number,
                "name": (raw.get("name") or "").strip(),
                # Raw cells (only the non-empty ones) so the table can show what
                # the user actually typed next to the reason it failed.
                "values": {key: value for key, value in raw.items() if value},
                "errors": errors_by_row.get(row_number, []),
            }
        )
    return serialized


def _iso(value):
    return value.isoformat() if value else None
