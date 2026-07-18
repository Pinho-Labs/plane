/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { TCsvImportValidation } from "@/services/project";
import { ImportPreviewStep } from "../preview-step";

const buildValidation = (overrides?: Partial<TCsvImportValidation>): TCsvImportValidation => ({
  total: 3,
  valid: 2,
  invalid: 1,
  errors: [{ row: 4, field: "State", message: "State 'Nirvana' not found" }],
  sample: [],
  ...overrides,
});

describe("ImportPreviewStep", () => {
  it("lists row-level error messages when there are invalid rows", () => {
    render(<ImportPreviewStep validation={buildValidation()} skipInvalid={false} onToggleSkip={vi.fn()} />);
    expect(screen.getByText("State 'Nirvana' not found")).toBeInTheDocument();
  });

  it("hides the error section and skip toggle when every row is valid", () => {
    render(
      <ImportPreviewStep
        validation={buildValidation({ invalid: 0, errors: [] })}
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
