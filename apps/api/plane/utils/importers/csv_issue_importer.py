# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure parsing/validation/resolution for the work-item CSV bulk importer.

This module has NO Django/ORM dependency on purpose: it takes a CSV payload and
a `ResolutionContext` (lookup maps the caller pre-fetches from the database) and
returns resolved, serializer-shaped rows plus structured per-row errors. Keeping
it pure mirrors `plane.utils.porters.formatters` and makes it unit-testable with
no database, matching the existing CSV export sanitization tests.

The caller (endpoint / Celery task) is responsible for:
  * building the `ResolutionContext` from project-scoped queries,
  * creating any `new_label_names` (admins only) and merging their ids,
  * persisting issues via the create serializer and inserting the resolved
    `module_ids` / `cycle_id` membership rows.
"""

import csv
import html
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO

from plane.utils.importers.template import (
    MULTI_VALUE_SEPARATOR,
    SPEC_BY_KEY,
    normalize_header,
)

# Mirror of Issue.PRIORITY_CHOICES (kept local to keep this module Django-free).
VALID_PRIORITIES = frozenset(("urgent", "high", "medium", "low", "none"))
DEFAULT_PRIORITY = "none"

# Hard cap on data rows (excludes the header). Enforced here so the parser never
# materializes an unbounded file; the endpoint additionally caps the byte size.
MAX_ROWS = 5000

# Sentinel row number for file-level (non-row-specific) errors.
FILE_LEVEL_ROW = 0

_DATE_FORMAT = "%Y-%m-%d"


@dataclass(frozen=True)
class RowError:
    """A single validation problem, addressable by the user."""

    row: int  # 1-based data-row number (header excluded); 0 == file-level
    field: str
    message: str


@dataclass
class ProjectFeatures:
    """Which optional project features are enabled (gates cycle/module/etc.)."""

    cycle_view: bool = True
    module_view: bool = True
    estimates_enabled: bool = True
    work_item_types_enabled: bool = False


@dataclass
class ResolutionContext:
    """Pre-fetched, project-scoped lookup maps used to resolve human values.

    All name/email keys are expected lower-cased; identifier keys upper-cased.
    """

    state_by_name: dict = field(default_factory=dict)  # name -> state_id
    default_state_id: str | None = None
    member_by_email: dict = field(default_factory=dict)  # email -> user_id
    label_by_name: dict = field(default_factory=dict)  # name -> label_id
    cycle_by_name: dict = field(default_factory=dict)  # name -> cycle_id
    module_by_name: dict = field(default_factory=dict)  # name -> module_id
    estimate_by_value: dict = field(default_factory=dict)  # value -> estimate_point_id
    issue_by_identifier: dict = field(default_factory=dict)  # PROJ-123 -> issue_id
    type_by_name: dict = field(default_factory=dict)  # name -> issue_type_id
    can_create_labels: bool = False
    features: ProjectFeatures = field(default_factory=ProjectFeatures)


@dataclass
class ParsedRow:
    """A validated row resolved to internal ids, ready to persist."""

    row_number: int
    payload: dict  # fields for IssueCreateSerializer (name, state_id, ...)
    module_ids: list = field(default_factory=list)  # -> ModuleIssue rows
    cycle_id: str | None = None  # -> CycleIssue row
    new_label_names: list = field(default_factory=list)  # admin auto-create, then merge into label_ids


@dataclass
class ImportPreview:
    """Result of a dry run over the whole file."""

    total: int  # total data rows seen
    valid_rows: list = field(default_factory=list)  # list[ParsedRow]
    errors: list = field(default_factory=list)  # list[RowError]

    @property
    def valid_count(self):
        return len(self.valid_rows)

    @property
    def invalid_count(self):
        return len({e.row for e in self.errors if e.row != FILE_LEVEL_ROW})


def _split_multi(value):
    """Split a multi-value cell on the separator, trimming blanks."""
    if not value:
        return []
    return [part.strip() for part in value.split(MULTI_VALUE_SEPARATOR) if part.strip()]


def _to_description_html(value):
    """Wrap a plain-text description in a paragraph, escaping HTML.

    Values already looking like HTML (starting with '<') are passed through as-is
    and left for the server-side HTML sanitizer to clean.
    """
    if not value:
        return "<p></p>"
    stripped = value.strip()
    if stripped.startswith("<"):
        return stripped
    return f"<p>{html.escape(stripped)}</p>"


def parse_rows(csv_text):
    """Parse CSV text into (rows, errors).

    Each row is a dict keyed by internal field key (unknown columns ignored).
    Returns file-level errors for missing required columns or exceeding MAX_ROWS.
    """
    errors = []
    reader = csv.reader(StringIO(csv_text))
    try:
        raw_headers = next(reader)
    except StopIteration:
        return [], [RowError(FILE_LEVEL_ROW, "file", "The CSV file is empty.")]

    # Map each column index to an internal key (or None to ignore it).
    index_to_key = [normalize_header(h) for h in raw_headers]
    present_keys = {k for k in index_to_key if k}

    if "name" not in present_keys:
        # Without a Name column nothing is importable; skip per-row parsing so
        # the user gets one clear file-level error instead of noise on every row.
        return [], [RowError(FILE_LEVEL_ROW, "Name", "Required 'Name' column is missing.")]

    rows = []
    for line_number, values in enumerate(reader, start=1):
        if line_number > MAX_ROWS:
            errors.append(
                RowError(
                    FILE_LEVEL_ROW,
                    "file",
                    f"CSV exceeds the maximum of {MAX_ROWS} rows.",
                )
            )
            break
        if not any((v or "").strip() for v in values):
            continue
        row = {}
        for index, key in enumerate(index_to_key):
            if not key:
                continue
            row[key] = values[index].strip() if index < len(values) else ""
        rows.append((line_number, row))

    return rows, errors


def resolve_row(row_number, row, ctx):
    """Resolve one raw row to a (ParsedRow | None, list[RowError]).

    Accumulates ALL problems for the row so the user sees every issue at once.
    Returns (None, errors) when the row has any error.
    """
    errors = []
    payload = {}

    name = (row.get("name") or "").strip()
    if not name:
        errors.append(RowError(row_number, "Name", "Name is required."))
    elif len(name) > 255:
        errors.append(RowError(row_number, "Name", "Name exceeds 255 characters."))
    else:
        payload["name"] = name

    payload["description_html"] = _to_description_html(row.get("description"))

    raw_priority = (row.get("priority") or "").strip().lower()
    if not raw_priority:
        payload["priority"] = DEFAULT_PRIORITY
    elif raw_priority in VALID_PRIORITIES:
        payload["priority"] = raw_priority
    else:
        errors.append(
            RowError(
                row_number,
                "Priority",
                f"Invalid priority '{row.get('priority')}'. Use one of: {', '.join(sorted(VALID_PRIORITIES))}.",
            )
        )

    raw_state = (row.get("state") or "").strip()
    if raw_state:
        state_id = ctx.state_by_name.get(raw_state.lower())
        if state_id:
            payload["state_id"] = state_id
        else:
            errors.append(RowError(row_number, "State", f"State '{raw_state}' not found in this project."))
    elif ctx.default_state_id:
        payload["state_id"] = ctx.default_state_id
    # Left unset when blank: Issue.save() fills the project's default state.

    start_date = _parse_date(row.get("start_date"), row_number, "Start Date", errors)
    target_date = _parse_date(row.get("target_date"), row_number, "Target Date", errors)
    if start_date is not None:
        payload["start_date"] = start_date
    if target_date is not None:
        payload["target_date"] = target_date
    if start_date and target_date and start_date > target_date:
        errors.append(RowError(row_number, "Target Date", "Target Date cannot be before Start Date."))

    assignee_ids = []
    for email in _split_multi(row.get("assignees")):
        user_id = ctx.member_by_email.get(email.lower())
        if user_id:
            assignee_ids.append(user_id)
        else:
            errors.append(
                RowError(row_number, "Assignees", f"'{email}' is not an active member of this project.")
            )
    if assignee_ids:
        payload["assignee_ids"] = assignee_ids

    # Unknown labels are queued for creation only for admins; others get a row error.
    label_ids = []
    new_label_names = []
    for label_name in _split_multi(row.get("labels")):
        label_id = ctx.label_by_name.get(label_name.lower())
        if label_id:
            label_ids.append(label_id)
        elif ctx.can_create_labels:
            new_label_names.append(label_name)
        else:
            errors.append(
                RowError(
                    row_number,
                    "Labels",
                    f"Label '{label_name}' does not exist and you lack permission to create it.",
                )
            )
    if label_ids:
        payload["label_ids"] = label_ids

    raw_estimate = (row.get("estimate") or "").strip()
    if raw_estimate:
        if not ctx.features.estimates_enabled:
            errors.append(RowError(row_number, "Estimate", "Estimates are not enabled for this project."))
        else:
            estimate_id = ctx.estimate_by_value.get(raw_estimate.lower())
            if estimate_id:
                payload["estimate_point"] = estimate_id
            else:
                errors.append(RowError(row_number, "Estimate", f"Estimate '{raw_estimate}' not found."))

    raw_parent = (row.get("parent") or "").strip()
    if raw_parent:
        parent_id = ctx.issue_by_identifier.get(raw_parent.upper())
        if parent_id:
            payload["parent_id"] = parent_id
        else:
            errors.append(RowError(row_number, "Parent", f"Parent '{raw_parent}' not found in this project."))

    raw_type = (row.get("type") or "").strip()
    if raw_type:
        if not ctx.features.work_item_types_enabled:
            errors.append(RowError(row_number, "Work Item Type", "Work item types are not enabled for this project."))
        else:
            type_id = ctx.type_by_name.get(raw_type.lower())
            if type_id:
                # Model field is `type`; IssueCreateSerializer exposes it via fields="__all__".
                payload["type"] = type_id
            else:
                errors.append(RowError(row_number, "Work Item Type", f"Type '{raw_type}' not found."))

    cycle_id = None
    raw_cycle = (row.get("cycle") or "").strip()
    if raw_cycle:
        if not ctx.features.cycle_view:
            errors.append(RowError(row_number, "Cycle", "Cycles are not enabled for this project."))
        else:
            cycle_id = ctx.cycle_by_name.get(raw_cycle.lower())
            if not cycle_id:
                errors.append(RowError(row_number, "Cycle", f"Cycle '{raw_cycle}' not found in this project."))

    module_ids = []
    raw_modules = _split_multi(row.get("modules"))
    if raw_modules:
        if not ctx.features.module_view:
            errors.append(RowError(row_number, "Modules", "Modules are not enabled for this project."))
        else:
            for module_name in raw_modules:
                module_id = ctx.module_by_name.get(module_name.lower())
                if module_id:
                    module_ids.append(module_id)
                else:
                    errors.append(RowError(row_number, "Modules", f"Module '{module_name}' not found in this project."))

    external_id = (row.get("external_id") or "").strip()
    if external_id:
        # external_source stamps the origin so re-imports can de-dupe on external_id.
        payload["external_id"] = external_id
        payload["external_source"] = "csv"

    if errors:
        return None, errors

    return (
        ParsedRow(
            row_number=row_number,
            payload=payload,
            module_ids=module_ids,
            cycle_id=cycle_id,
            new_label_names=new_label_names,
        ),
        [],
    )


def _parse_date(value, row_number, field_name, errors):
    """Parse a YYYY-MM-DD cell; append a RowError on a malformed non-empty value."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _DATE_FORMAT).date()
    except ValueError:
        errors.append(RowError(row_number, field_name, f"Invalid date '{raw}'. Use YYYY-MM-DD."))
        return None


def build_preview(csv_text, ctx):
    """Parse + resolve the whole file into an ImportPreview (writes nothing)."""
    rows, file_errors = parse_rows(csv_text)
    preview = ImportPreview(total=len(rows), errors=list(file_errors))
    for row_number, row in rows:
        parsed, row_errors = resolve_row(row_number, row, ctx)
        if parsed is not None:
            preview.valid_rows.append(parsed)
        preview.errors.extend(row_errors)
    return preview
