# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import csv
from io import StringIO

import pytest

from plane.utils.importers.csv_issue_importer import (
    FILE_LEVEL_ROW,
    MAX_ROWS,
    ProjectFeatures,
    ResolutionContext,
    build_preview,
    parse_rows,
    resolve_row,
)
from plane.utils.importers.template import (
    CANONICAL_HEADERS,
    build_template_csv,
    normalize_header,
)

STATE_ID = "11111111-1111-1111-1111-111111111111"
DONE_STATE_ID = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"
LABEL_ID = "44444444-4444-4444-4444-444444444444"
CYCLE_ID = "55555555-5555-5555-5555-555555555555"
MODULE_ID = "66666666-6666-6666-6666-666666666666"
ESTIMATE_ID = "77777777-7777-7777-7777-777777777777"
PARENT_ID = "88888888-8888-8888-8888-888888888888"
TYPE_ID = "99999999-9999-9999-9999-999999999999"


def _ctx(**overrides):
    """Build a ResolutionContext with sensible resolvable defaults."""
    ctx = ResolutionContext(
        state_by_name={"todo": STATE_ID, "in progress": DONE_STATE_ID},
        default_state_id=STATE_ID,
        member_by_email={"jane@acme.com": USER_ID},
        label_by_name={"bug": LABEL_ID},
        cycle_by_name={"sprint 5": CYCLE_ID},
        module_by_name={"auth": MODULE_ID},
        estimate_by_value={"3": ESTIMATE_ID},
        issue_by_identifier={"PROJ-12": PARENT_ID},
        type_by_name={"bug": TYPE_ID},
        can_create_labels=False,
        features=ProjectFeatures(work_item_types_enabled=True),
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _csv(headers, *rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


@pytest.mark.unit
class TestTemplate:
    def test_build_template_has_headers_and_example(self):
        content = build_template_csv()
        rows = list(csv.reader(StringIO(content)))
        assert rows[0] == CANONICAL_HEADERS
        assert len(rows) == 2  # header + one example
        assert rows[1][0] == "Fix login redirect"

    def test_build_template_without_example(self):
        rows = list(csv.reader(StringIO(build_template_csv(include_example=False))))
        assert len(rows) == 1

    def test_normalize_header_is_case_insensitive(self):
        assert normalize_header("  NAME ") == "name"
        assert normalize_header("Work Item Type") == "type"
        assert normalize_header("Nope") is None


@pytest.mark.unit
class TestParseRows:
    def test_maps_headers_and_ignores_unknown_columns(self):
        content = _csv(["Name", "Priority", "Bogus"], ["Task A", "high", "x"])
        rows, errors = parse_rows(content)
        assert errors == []
        assert rows[0][0] == 1
        assert rows[0][1] == {"name": "Task A", "priority": "high"}

    def test_missing_name_column_is_file_error(self):
        _, errors = parse_rows(_csv(["Priority"], ["high"]))
        assert any(e.row == FILE_LEVEL_ROW and e.field == "Name" for e in errors)

    def test_blank_lines_are_skipped(self):
        content = _csv(["Name"], ["Task A"], ["   "], ["Task B"])
        rows, _ = parse_rows(content)
        assert [r[1]["name"] for r in rows] == ["Task A", "Task B"]

    def test_empty_file_is_file_error(self):
        rows, errors = parse_rows("")
        assert rows == []
        assert errors and errors[0].row == FILE_LEVEL_ROW

    def test_row_cap_is_enforced(self):
        content = _csv(["Name"], *[[f"Task {i}"] for i in range(MAX_ROWS + 5)])
        rows, errors = parse_rows(content)
        assert len(rows) == MAX_ROWS
        assert any("exceeds the maximum" in e.message for e in errors)


@pytest.mark.unit
class TestResolveRow:
    def test_happy_path_resolves_all_fields(self):
        row = {
            "name": "Fix login",
            "description": "bounced to home",
            "state": "In Progress",
            "priority": "high",
            "assignees": "jane@acme.com",
            "labels": "bug",
            "start_date": "2026-07-20",
            "target_date": "2026-07-25",
            "estimate": "3",
            "parent": "proj-12",
            "cycle": "Sprint 5",
            "modules": "Auth",
            "type": "Bug",
            "external_id": "ext-1",
        }
        parsed, errors = resolve_row(1, row, _ctx())
        assert errors == []
        assert parsed.payload["name"] == "Fix login"
        assert parsed.payload["description_html"] == "<p>bounced to home</p>"
        assert parsed.payload["state_id"] == DONE_STATE_ID
        assert parsed.payload["priority"] == "high"
        assert parsed.payload["assignee_ids"] == [USER_ID]
        assert parsed.payload["label_ids"] == [LABEL_ID]
        assert str(parsed.payload["start_date"]) == "2026-07-20"
        assert parsed.payload["estimate_point"] == ESTIMATE_ID
        assert parsed.payload["parent_id"] == PARENT_ID  # case-insensitive identifier
        assert parsed.payload["type"] == TYPE_ID
        assert parsed.payload["external_id"] == "ext-1"
        assert parsed.payload["external_source"] == "csv"
        assert parsed.cycle_id == CYCLE_ID
        assert parsed.module_ids == [MODULE_ID]

    def test_missing_name_errors(self):
        parsed, errors = resolve_row(2, {"name": ""}, _ctx())
        assert parsed is None
        assert any(e.field == "Name" and e.row == 2 for e in errors)

    def test_blank_priority_defaults_to_none(self):
        parsed, _ = resolve_row(1, {"name": "A", "priority": ""}, _ctx())
        assert parsed.payload["priority"] == "none"

    def test_invalid_priority_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "priority": "sky-high"}, _ctx())
        assert parsed is None
        assert any(e.field == "Priority" for e in errors)

    def test_blank_state_uses_project_default(self):
        parsed, _ = resolve_row(1, {"name": "A", "state": ""}, _ctx())
        assert parsed.payload["state_id"] == STATE_ID

    def test_unknown_state_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "state": "Nirvana"}, _ctx())
        assert parsed is None
        assert any(e.field == "State" for e in errors)

    def test_invalid_date_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "start_date": "20/07/2026"}, _ctx())
        assert parsed is None
        assert any(e.field == "Start Date" for e in errors)

    def test_start_after_target_errors(self):
        row = {"name": "A", "start_date": "2026-07-25", "target_date": "2026-07-20"}
        parsed, errors = resolve_row(1, row, _ctx())
        assert parsed is None
        assert any("before Start Date" in e.message for e in errors)

    def test_non_member_assignee_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "assignees": "ghost@acme.com"}, _ctx())
        assert parsed is None
        assert any(e.field == "Assignees" for e in errors)

    def test_unknown_label_without_admin_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "labels": "bug;backend"}, _ctx())
        assert parsed is None
        assert any(e.field == "Labels" and "backend" in e.message for e in errors)

    def test_unknown_label_with_admin_queues_creation(self):
        parsed, errors = resolve_row(1, {"name": "A", "labels": "bug;backend"}, _ctx(can_create_labels=True))
        assert errors == []
        assert parsed.payload["label_ids"] == [LABEL_ID]
        assert parsed.new_label_names == ["backend"]

    def test_estimate_disabled_errors(self):
        ctx = _ctx(features=ProjectFeatures(estimates_enabled=False))
        parsed, errors = resolve_row(1, {"name": "A", "estimate": "3"}, ctx)
        assert parsed is None
        assert any(e.field == "Estimate" for e in errors)

    def test_cycle_disabled_errors(self):
        ctx = _ctx(features=ProjectFeatures(cycle_view=False))
        parsed, errors = resolve_row(1, {"name": "A", "cycle": "Sprint 5"}, ctx)
        assert parsed is None
        assert any(e.field == "Cycle" for e in errors)

    def test_module_not_found_errors(self):
        parsed, errors = resolve_row(1, {"name": "A", "modules": "Auth;Ghost"}, _ctx())
        assert parsed is None
        assert any(e.field == "Modules" and "Ghost" in e.message for e in errors)

    def test_type_disabled_errors(self):
        ctx = _ctx(features=ProjectFeatures(work_item_types_enabled=False))
        parsed, errors = resolve_row(1, {"name": "A", "type": "Bug"}, ctx)
        assert parsed is None
        assert any(e.field == "Work Item Type" for e in errors)

    def test_html_description_passthrough(self):
        parsed, _ = resolve_row(1, {"name": "A", "description": "<p>hi</p>"}, _ctx())
        assert parsed.payload["description_html"] == "<p>hi</p>"

    def test_description_escapes_html_special_chars(self):
        parsed, _ = resolve_row(1, {"name": "A", "description": "a < b & c"}, _ctx())
        assert parsed.payload["description_html"] == "<p>a &lt; b &amp; c</p>"

    def test_all_errors_accumulated_for_a_row(self):
        row = {"name": "", "priority": "bad", "state": "Nope"}
        parsed, errors = resolve_row(3, row, _ctx())
        assert parsed is None
        fields = {e.field for e in errors}
        assert {"Name", "Priority", "State"} <= fields


@pytest.mark.unit
class TestBuildPreview:
    def test_counts_valid_and_invalid_rows(self):
        content = _csv(
            ["Name", "Priority"],
            ["Good", "high"],
            ["", "high"],  # missing name -> invalid
            ["Also Good", "low"],
        )
        preview = build_preview(content, _ctx())
        assert preview.total == 3
        assert preview.valid_count == 2
        assert preview.invalid_count == 1

    def test_file_level_error_not_counted_as_invalid_row(self):
        preview = build_preview(_csv(["Priority"], ["high"]), _ctx())
        assert preview.valid_count == 0
        assert preview.invalid_count == 0
        assert any(e.row == FILE_LEVEL_ROW for e in preview.errors)


@pytest.mark.unit
class TestErrorCodes:
    """Lock the stable error `code` for every failure so the frontend i18n keys
    (workspace_settings.settings.imports.errors.<code>) can't silently drift."""

    @pytest.mark.parametrize(
        "row,features,expected_code",
        [
            ({"name": ""}, None, "name_required"),
            ({"name": "N" * 256}, None, "name_too_long"),
            ({"name": "A", "priority": "sky-high"}, None, "priority_invalid"),
            ({"name": "A", "state": "Nirvana"}, None, "state_not_found"),
            ({"name": "A", "start_date": "20/07/2026"}, None, "date_invalid"),
            ({"name": "A", "start_date": "2026-07-10", "target_date": "2026-07-01"}, None, "target_before_start"),
            ({"name": "A", "assignees": "ghost@acme.com"}, None, "assignee_not_member"),
            ({"name": "A", "labels": "unknown-label"}, None, "label_missing_permission"),
            ({"name": "A", "estimate": "3"}, ProjectFeatures(estimates_enabled=False), "estimate_disabled"),
            ({"name": "A", "estimate": "99"}, None, "estimate_not_found"),
            ({"name": "A", "parent": "NOPE-9"}, None, "parent_not_found"),
            ({"name": "A", "type": "Bug"}, ProjectFeatures(work_item_types_enabled=False), "type_disabled"),
            ({"name": "A", "type": "Ghost"}, None, "type_not_found"),
            ({"name": "A", "cycle": "Sprint 5"}, ProjectFeatures(cycle_view=False), "cycle_disabled"),
            ({"name": "A", "cycle": "Ghost"}, None, "cycle_not_found"),
            ({"name": "A", "modules": "Auth"}, ProjectFeatures(module_view=False), "module_disabled"),
            ({"name": "A", "modules": "Ghost"}, None, "module_not_found"),
        ],
    )
    def test_resolve_row_error_codes(self, row, features, expected_code):
        ctx = _ctx(features=features) if features is not None else _ctx()
        _, errors = resolve_row(1, row, ctx)
        assert expected_code in {e.code for e in errors}

    def test_file_level_error_codes(self):
        assert parse_rows("")[1][0].code == "file_empty"
        assert parse_rows(_csv(["Priority"], ["high"]))[1][0].code == "name_column_missing"
        over_cap = _csv(["Name"], *[[f"row {i}"] for i in range(MAX_ROWS + 1)])
        _, errors = parse_rows(over_cap)
        assert any(e.code == "max_rows" and e.params == {"max": MAX_ROWS} for e in errors)
