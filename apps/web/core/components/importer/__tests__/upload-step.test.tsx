/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImportUploadStep } from "../upload-step";

const PASTE_TAB = "workspace_settings.settings.imports.tab_paste";
const VALIDATE = "workspace_settings.settings.imports.paste_validate";

const baseProps = {
  projectOptions: [],
  selectedProjectId: "p1" as string | null,
  onSelectProject: vi.fn(),
  onFileSelected: vi.fn(),
  fileName: null as string | null,
  fileError: null as string | null,
  templateUrl: "http://api.test/api/workspaces/ws/projects/p1/issues/import-csv/template/" as string | null,
  disabled: false,
};

describe("ImportUploadStep", () => {
  it("shows the template download link pointing at the template URL", () => {
    render(<ImportUploadStep {...baseProps} />);
    const link = screen.getByText("workspace_settings.settings.imports.download_template").closest("a");
    expect(link).toHaveAttribute("href", baseProps.templateUrl!);
    expect(link).toHaveAttribute("download");
  });

  it("prompts to drop a CSV when no file is chosen", () => {
    render(<ImportUploadStep {...baseProps} />);
    expect(screen.getByText("workspace_settings.settings.imports.drop_csv")).toBeInTheDocument();
  });

  it("shows the chosen file name once a file is selected", () => {
    render(<ImportUploadStep {...baseProps} fileName="my-items.csv" />);
    expect(screen.getByText("my-items.csv")).toBeInTheDocument();
  });

  it("surfaces a file error", () => {
    render(<ImportUploadStep {...baseProps} fileError="File too large" />);
    expect(screen.getByText("File too large")).toBeInTheDocument();
  });

  it("hides the template link until a project is selected", () => {
    render(<ImportUploadStep {...baseProps} selectedProjectId={null} templateUrl={null} />);
    expect(screen.queryByText("workspace_settings.settings.imports.download_template")).not.toBeInTheDocument();
  });

  it("shows a textarea instead of the dropzone on the Paste tab", async () => {
    render(<ImportUploadStep {...baseProps} />);
    await userEvent.click(screen.getByText(PASTE_TAB));
    expect(screen.getByLabelText("csv-paste")).toBeInTheDocument();
    expect(screen.queryByLabelText("csv-dropzone")).not.toBeInTheDocument();
  });

  it("submits pasted CSV content as a File through onFileSelected", async () => {
    const onFileSelected = vi.fn();
    render(<ImportUploadStep {...baseProps} onFileSelected={onFileSelected} />);
    await userEvent.click(screen.getByText(PASTE_TAB));
    await userEvent.type(screen.getByLabelText("csv-paste"), "Name{Enter}Task A");
    await userEvent.click(screen.getByText(VALIDATE));

    expect(onFileSelected).toHaveBeenCalledTimes(1);
    const file = onFileSelected.mock.calls[0][0] as File;
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe("pasted.csv");
    expect(file.type).toBe("text/csv");
    // Byte size matches the pasted (trimmed) content: "Name\nTask A" == 11 chars.
    expect(file.size).toBe("Name\nTask A".length);
  });

  it("keeps the Validate button disabled while the paste box is empty", async () => {
    render(<ImportUploadStep {...baseProps} />);
    await userEvent.click(screen.getByText(PASTE_TAB));
    expect(screen.getByText(VALIDATE).closest("button")).toBeDisabled();
  });
});
