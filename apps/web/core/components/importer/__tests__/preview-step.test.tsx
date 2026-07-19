/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { TCsvImportValidation, TCsvPreviewRow } from "@/services/project";
import { ImportPreviewStep } from "../preview-step";

const validRow = (over?: Partial<TCsvPreviewRow>): TCsvPreviewRow => ({
  row: 1,
  name: "Fix login redirect",
  has_description: false,
  priority: "high",
  state: { name: "Todo", color: "#3f76ff" },
  assignees: [],
  labels: [],
  start_date: null,
  target_date: null,
  estimate: null,
  cycle: null,
  modules: [],
  type: null,
  ...over,
});

const buildValidation = (overrides?: Partial<TCsvImportValidation>): TCsvImportValidation => ({
  total: 3,
  valid: 2,
  invalid: 1,
  errors: [{ row: 4, field: "State", message: "State 'Nirvana' not found" }],
  sample: [
    validRow(),
    validRow({ row: 2, name: "Ship onboarding", state: { name: "In Progress", color: "#f59e0b" } }),
  ],
  invalid_sample: [
    { row: 4, name: "Publish notes", values: { state: "Nirvana" }, errors: [{ field: "State", message: "State 'Nirvana' not found" }] },
  ],
  preview_limit: 200,
  sample_truncated: false,
  ...overrides,
});

describe("ImportPreviewStep", () => {
  it("renders valid rows with their resolved values", () => {
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={vi.fn()} />);
    expect(screen.getByText("Fix login redirect")).toBeInTheDocument();
    expect(screen.getByText("Ship onboarding")).toBeInTheDocument();
    expect(screen.getByText("Todo")).toBeInTheDocument();
  });

  it("shows invalid rows with their error reason", () => {
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={vi.fn()} />);
    expect(screen.getByText("Publish notes")).toBeInTheDocument();
    // No `code` on this fixture -> falls back to the English message.
    expect(screen.getByText("State 'Nirvana' not found")).toBeInTheDocument();
  });

  it("localizes an error message via its code when present", () => {
    render(
      <ImportPreviewStep
        validation={buildValidation({
          invalid_sample: [
            {
              row: 4,
              name: "Publish notes",
              values: { state: "Nirvana" },
              errors: [{ field: "State", message: "fallback", code: "state_not_found", params: { value: "Nirvana" } }],
            },
          ],
        })}
        skipInvalid={false}
        onToggleSkip={vi.fn()}
      />
    );
    // The i18n stub echoes the key, so seeing the key (not "fallback") proves
    // the code drove an i18n lookup.
    expect(screen.getByText("workspace_settings.settings.imports.errors.state_not_found")).toBeInTheDocument();
    expect(screen.queryByText("fallback")).not.toBeInTheDocument();
  });

  it("filters to only invalid rows on the errors tab", async () => {
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={vi.fn()} />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.preview.tab_errors"));
    expect(screen.queryByText("Fix login redirect")).not.toBeInTheDocument();
    expect(screen.getByText("Publish notes")).toBeInTheDocument();
  });

  it("filters rows by name", async () => {
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={vi.fn()} />);
    await userEvent.type(
      screen.getByLabelText("workspace_settings.settings.imports.preview.filter_placeholder"),
      "onboarding"
    );
    expect(screen.getByText("Ship onboarding")).toBeInTheDocument();
    expect(screen.queryByText("Fix login redirect")).not.toBeInTheDocument();
  });

  it("paginates at 25 rows per page and navigates between pages", async () => {
    const sample = Array.from({ length: 30 }, (_, i) => validRow({ row: i + 1, name: `Item ${i + 1}` }));
    render(
      <ImportPreviewStep
        validation={buildValidation({ total: 30, valid: 30, invalid: 0, errors: [], invalid_sample: [], sample })}
        skipInvalid={false}
        onToggleSkip={vi.fn()}
      />
    );
    expect(screen.getByText("Item 1")).toBeInTheDocument();
    expect(screen.getByText("Item 25")).toBeInTheDocument();
    expect(screen.queryByText("Item 26")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "common.next" }));
    expect(screen.getByText("Item 26")).toBeInTheDocument();
    expect(screen.getByText("Item 30")).toBeInTheDocument();
    expect(screen.queryByText("Item 1")).not.toBeInTheDocument();
  });

  it("surfaces file-level errors (row 0) in a banner", () => {
    render(
      <ImportPreviewStep
        validation={buildValidation({
          total: 0,
          valid: 0,
          invalid: 0,
          sample: [],
          invalid_sample: [],
          errors: [{ row: 0, field: "Name", message: "fallback", code: "name_column_missing" }],
        })}
        skipInvalid={false}
        onToggleSkip={vi.fn()}
      />
    );
    expect(screen.getByText("workspace_settings.settings.imports.errors.name_column_missing")).toBeInTheDocument();
  });

  it("hides the skip toggle when every row is valid", () => {
    render(
      <ImportPreviewStep
        validation={buildValidation({ invalid: 0, errors: [], invalid_sample: [] })}
        skipInvalid={false}
        onToggleSkip={vi.fn()}
      />
    );
    expect(screen.queryByText(/not found/)).not.toBeInTheDocument();
    expect(screen.queryByText("workspace_settings.settings.imports.skip_invalid")).not.toBeInTheDocument();
  });

  it("invokes onToggleSkip when the skip option is clicked", async () => {
    const onToggleSkip = vi.fn();
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={onToggleSkip} />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.skip_invalid"));
    expect(onToggleSkip).toHaveBeenCalledWith(true);
  });
});
