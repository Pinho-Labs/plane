# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Canonical column specification for the work-item CSV bulk importer.

This module is the single source of truth for the CSV template: the column
headers, their mapping to internal field keys, which are required, and which
accept multiple `;`-separated values. It is intentionally pure (stdlib only,
no Django) so it can be imported by both the parser and the template-download
endpoint, and unit-tested without a database.
"""

import csv
from dataclasses import dataclass
from io import StringIO

from plane.utils.csv_utils import sanitize_csv_value

# Separator used inside a single cell for multi-value columns
# (assignees, labels, modules). Semicolon avoids clashing with the CSV comma.
MULTI_VALUE_SEPARATOR = ";"


@dataclass(frozen=True)
class ColumnSpec:
    """Describes one column of the import template."""

    key: str  # internal field key used by the parser/serializer
    header: str  # human-facing CSV header
    required: bool = False
    multi: bool = False  # accepts MULTI_VALUE_SEPARATOR-separated values
    help_text: str = ""


# Order here is the order columns appear in the downloaded template.
# Mirrors the work-item create modal (DEFAULT_WORK_ITEM_FORM_VALUES).
COLUMN_SPECS = (
    ColumnSpec("name", "Name", required=True, help_text="Work item title (required, <=255 chars)"),
    ColumnSpec("description", "Description", help_text="Plain text or minimal HTML"),
    ColumnSpec("state", "State", help_text="State name; blank uses the project default state"),
    ColumnSpec("priority", "Priority", help_text="urgent | high | medium | low | none"),
    ColumnSpec("assignees", "Assignees", multi=True, help_text="Project member emails, ;-separated"),
    ColumnSpec("labels", "Labels", multi=True, help_text="Label names, ;-separated"),
    ColumnSpec("start_date", "Start Date", help_text="YYYY-MM-DD"),
    ColumnSpec("target_date", "Target Date", help_text="YYYY-MM-DD"),
    ColumnSpec("estimate", "Estimate", help_text="Estimate point value/label in the project's estimate"),
    ColumnSpec("parent", "Parent", help_text="Parent work item identifier, e.g. PROJ-12"),
    ColumnSpec("cycle", "Cycle", help_text="Cycle name (single)"),
    ColumnSpec("modules", "Modules", multi=True, help_text="Module names, ;-separated"),
    ColumnSpec("type", "Work Item Type", help_text="Work item type name (when enabled)"),
    ColumnSpec("external_id", "External ID", help_text="Optional stable id for re-import de-duplication"),
)

CANONICAL_HEADERS = [spec.header for spec in COLUMN_SPECS]

# Header match is case-insensitive so spreadsheet apps that re-case headers still resolve.
HEADER_TO_KEY = {spec.header.strip().lower(): spec.key for spec in COLUMN_SPECS}

SPEC_BY_KEY = {spec.key: spec for spec in COLUMN_SPECS}

# Shipped with the template so users see the expected value format for every column.
EXAMPLE_ROW = {
    "Name": "Fix login redirect",
    "Description": "User is bounced to /home after signing in",
    "State": "In Progress",
    "Priority": "high",
    "Assignees": "jane@acme.com;bob@acme.com",
    "Labels": "bug;auth",
    "Start Date": "2026-07-20",
    "Target Date": "2026-07-25",
    "Estimate": "3",
    "Parent": "PROJ-12",
    "Cycle": "Sprint 5",
    "Modules": "Auth;Web",
    "Work Item Type": "Bug",
    "External ID": "ext-1001",
}


def normalize_header(header):
    """Return the internal field key for a raw CSV header, or None if unknown."""
    if header is None:
        return None
    return HEADER_TO_KEY.get(header.strip().lower())


def build_template_csv(include_example=True):
    """Return the CSV template as a string (headers + one optional example row).

    Values are passed through the export sanitizer so the shipped template can
    never itself carry a formula-injection payload.
    """
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([sanitize_csv_value(h) for h in CANONICAL_HEADERS])
    if include_example:
        writer.writerow([sanitize_csv_value(EXAMPLE_ROW.get(h, "")) for h in CANONICAL_HEADERS])
    return buffer.getvalue()
