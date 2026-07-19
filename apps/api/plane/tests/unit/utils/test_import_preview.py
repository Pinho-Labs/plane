# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Unit tests for the preview serializers (`plane.utils.importers.preview`).

These exercise `serialize_valid_row` / `serialize_invalid_rows` with in-memory
display maps, so no database is touched (`build_display_maps` is the only piece
that queries the ORM and is covered by the contract tests instead).
"""

import datetime

import pytest

from plane.utils.importers.csv_issue_importer import ParsedRow, RowError
from plane.utils.importers.preview import serialize_invalid_rows, serialize_valid_row

pytestmark = pytest.mark.unit


def _maps():
    return {
        "states": {"s1": {"name": "Todo", "color": "#3f76ff"}},
        "members": {"u1": {"id": "u1", "display_name": "Jane", "avatar_url": None}},
        "labels": {"l1": {"name": "bug", "color": "#ff0000"}},
        "cycles": {"c1": "Sprint 5"},
        "modules": {"m1": "Web"},
        "estimates": {"e1": "3"},
        "types": {"t1": "Bug"},
    }


class TestSerializeValidRow:
    def test_resolves_every_reference_to_display_values(self):
        parsed = ParsedRow(
            row_number=2,
            payload={
                "name": "Fix login",
                "description_html": "<p>hi</p>",
                "priority": "high",
                "state_id": "s1",
                "assignee_ids": ["u1"],
                "label_ids": ["l1"],
                "start_date": datetime.date(2026, 8, 1),
                "target_date": datetime.date(2026, 8, 5),
                "estimate_point": "e1",
                "type": "t1",
            },
            module_ids=["m1"],
            cycle_id="c1",
            new_label_names=["frontend"],
        )

        out = serialize_valid_row(parsed, _maps())

        assert out["row"] == 2
        assert out["name"] == "Fix login"
        assert out["has_description"] is True
        assert out["priority"] == "high"
        assert out["state"] == {"name": "Todo", "color": "#3f76ff"}
        assert out["assignees"][0]["display_name"] == "Jane"
        # Existing label resolved; admin-auto-created label flagged as new.
        assert {label["name"] for label in out["labels"]} == {"bug", "frontend"}
        assert any(label.get("is_new") for label in out["labels"])
        assert out["start_date"] == "2026-08-01"
        assert out["target_date"] == "2026-08-05"
        assert out["estimate"] == "3"
        assert out["cycle"] == "Sprint 5"
        assert out["modules"] == ["Web"]
        assert out["type"] == "Bug"

    def test_blank_description_is_not_flagged(self):
        parsed = ParsedRow(row_number=1, payload={"name": "A", "description_html": "<p></p>", "priority": "none"})
        out = serialize_valid_row(parsed, _maps())
        assert out["has_description"] is False
        assert out["state"] is None
        assert out["assignees"] == []
        assert out["labels"] == []
        assert out["modules"] == []


class TestSerializeInvalidRows:
    def test_keeps_raw_cells_and_row_errors(self):
        rows = [(4, {"name": "", "state": "Nirvana", "priority": ""})]
        errors = [
            RowError(4, "Name", "Name is required."),
            RowError(4, "State", "State 'Nirvana' not found in this project."),
            RowError(0, "file", "file-level, must be ignored"),
        ]

        out = serialize_invalid_rows(rows, errors)

        assert len(out) == 1
        assert out[0]["row"] == 4
        assert out[0]["name"] == ""
        # Blank cells are dropped; only what the user actually typed remains.
        assert out[0]["values"] == {"state": "Nirvana"}
        assert {e["field"] for e in out[0]["errors"]} == {"Name", "State"}
