# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Builds a human/AI-readable "import rules" document for a project.

Given a target project, this renders a Markdown document listing every CSV
column, whether it is required, its format, and — for the project-scoped fields
(state, assignees, labels, cycle, modules, estimate, work item type) — the exact
set of values that are valid *for this project right now*. The intent is to hand
it to an LLM so it produces a CSV that imports cleanly instead of guessing values.
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
from plane.utils.importers.csv_issue_importer import VALID_PRIORITIES
from plane.utils.importers.template import CANONICAL_HEADERS, EXAMPLE_ROW

# Guard against pathological payloads for very large projects; the note tells the
# reader (and the LLM) that the list was truncated.
MAX_VALUES = 500


def _values_line(values, sep=" | "):
    """Render a value list as inline code, capping absurdly long lists."""
    values = [str(v) for v in values if v]
    if not values:
        return None, 0
    truncated = len(values) > MAX_VALUES
    shown = values[:MAX_VALUES]
    line = sep.join(f"`{v}`" for v in shown)
    if truncated:
        line += f" … (+{len(values) - MAX_VALUES} more)"
    return line, len(values)


def build_import_rules_markdown(project, user_id):
    """Return a Markdown rules document for importing work items into `project`."""
    project_id = project.id

    states = list(State.objects.filter(project_id=project_id).values_list("name", flat=True))
    default_state = (
        State.objects.filter(project_id=project_id, default=True).values_list("name", flat=True).first()
    )
    emails = [
        e
        for e in ProjectMember.objects.filter(
            project_id=project_id, role__gte=15, is_active=True
        ).values_list("member__email", flat=True)
        if e
    ]
    labels = list(Label.objects.filter(project_id=project_id).values_list("name", flat=True))
    cycles = list(Cycle.objects.filter(project_id=project_id).values_list("name", flat=True))
    modules = list(Module.objects.filter(project_id=project_id).values_list("name", flat=True))
    estimates = (
        list(EstimatePoint.objects.filter(estimate_id=project.estimate_id).values_list("value", flat=True))
        if project.estimate_id
        else []
    )
    types = (
        list(
            IssueType.objects.filter(project_issue_types__project_id=project_id, is_active=True).values_list(
                "name", flat=True
            )
        )
        if project.is_issue_type_enabled
        else []
    )

    lines = []
    add = lines.append

    add(f"# CSV import rules — {project.name} ({project.identifier})")
    add("")
    add("Use these rules to build a CSV for bulk-importing work items into this project.")
    add("Only the values listed here are valid. Do NOT invent values for State, Assignees,")
    add("Labels, Cycle, Modules, Estimate, Parent, or Work Item Type.")
    add("")
    add("## File format")
    add("- UTF-8, comma-separated. The first row must be the exact header below.")
    add('- Multi-value cells are separated by ";" (semicolon).')
    add("- Dates use `YYYY-MM-DD`.")
    add("- Only the **Name** column is required. Every other column is optional and may be left blank or omitted.")
    add("")
    add("Header row (columns, in order):")
    add("")
    add("```")
    add(",".join(CANONICAL_HEADERS))
    add("```")
    add("")
    add("## Columns")

    add("")
    add("### Name — REQUIRED")
    add("Free text, up to 255 characters.")

    add("")
    add("### Description — optional")
    add("Plain text.")

    add("")
    add("### State — optional")
    state_line, _ = _values_line(states)
    if state_line:
        add(f"Allowed values (case-insensitive): {state_line}")
    else:
        add("No states found in this project.")
    if default_state:
        add(f"If left blank, defaults to `{default_state}`.")

    add("")
    add("### Priority — optional")
    # Display in severity order; VALID_PRIORITIES (the parser's source of truth) is the unordered set.
    priorities = [p for p in ("urgent", "high", "medium", "low", "none") if p in VALID_PRIORITIES]
    add(f"Exactly one of: {' | '.join(f'`{p}`' for p in priorities)}.")
    add("Blank defaults to `none`.")

    add("")
    add('### Assignees — optional, multiple allowed (separate with ";")')
    email_line, _ = _values_line(emails, sep="; ")
    add(f"Use these member emails only: {email_line}" if email_line else "No assignable members in this project.")

    add("")
    add("### Labels — optional, multiple allowed")
    label_line, _ = _values_line(labels, sep="; ")
    add(f"Existing labels: {label_line}" if label_line else "No labels exist yet in this project.")
    add("(New label names are created automatically only if the importer is a project admin.)")

    add("")
    add("### Start Date / Target Date — optional")
    add("Format `YYYY-MM-DD`. Start Date must be on or before Target Date.")

    add("")
    add("### Estimate — optional")
    if not project.estimate_id:
        add("**Not enabled for this project** — leave this column empty (any value will fail the row).")
    else:
        estimate_line, _ = _values_line(estimates)
        add(f"Allowed values: {estimate_line}" if estimate_line else "Estimates are enabled but no points are defined.")

    add("")
    add("### Parent — optional")
    add(f"An existing work item identifier in this project, e.g. `{project.identifier}-1`. Must already exist.")

    add("")
    add("### Cycle — optional")
    if not project.cycle_view:
        add("**Not enabled for this project** — leave this column empty.")
    else:
        cycle_line, _ = _values_line(cycles)
        add(f"Allowed cycles: {cycle_line}" if cycle_line else "Cycles are enabled but none exist yet.")

    add("")
    add("### Modules — optional, multiple allowed")
    if not project.module_view:
        add("**Not enabled for this project** — leave this column empty.")
    else:
        module_line, _ = _values_line(modules, sep="; ")
        add(f"Allowed modules: {module_line}" if module_line else "Modules are enabled but none exist yet.")

    add("")
    add("### Work Item Type — optional")
    if not project.is_issue_type_enabled:
        add("**Not enabled for this project** — leave this column empty.")
    else:
        type_line, _ = _values_line(types)
        add(f"Allowed types: {type_line}" if type_line else "Work item types are enabled but none are defined.")

    add("")
    add("### External ID — optional")
    add("Any unique string; used to skip duplicates when the same file is re-imported.")

    add("")
    add("## Example row")
    add("")
    add("```csv")
    add(",".join(CANONICAL_HEADERS))
    add(",".join(EXAMPLE_ROW.get(h, "") for h in CANONICAL_HEADERS))
    add("```")
    add("")

    return "\n".join(lines)
