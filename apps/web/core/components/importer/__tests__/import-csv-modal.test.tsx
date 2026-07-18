/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
// `toastCalls` is a stub-only recorder; import it from the stub directly so tsc
// resolves it (the vitest alias maps @plane/propel/toast to this same file at runtime).
import { toastCalls } from "../../../../test-stubs/plane-propel-toast";
import { ProjectImportService } from "@/services/project";
import type { TCsvImportValidation } from "@/services/project";
import { ImportCSVModal } from "../import-csv-modal";

// The modal reads target projects from the stores; provide one creatable project.
vi.mock("@/hooks/store/use-project", () => ({
  useProject: () => ({
    workspaceProjectIds: ["p1"],
    getProjectById: () => ({ id: "p1", name: "Alpha", identifier: "AL" }),
  }),
}));
vi.mock("@/hooks/store/user", () => ({
  useUser: () => ({ projectsWithCreatePermissions: { p1: {} } }),
}));

const IMPORT_BTN = "workspace_settings.settings.imports.import_button";

const validation = (over?: Partial<TCsvImportValidation>): TCsvImportValidation => ({
  total: 2,
  valid: 2,
  invalid: 0,
  errors: [],
  sample: [],
  ...over,
});

function chooseProjectAndFile(container: HTMLElement, file: File) {
  fireEvent.click(screen.getByTestId("project-option-p1"));
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

describe("ImportCSVModal", () => {
  beforeEach(() => {
    toastCalls.length = 0;
    vi.restoreAllMocks();
    vi.spyOn(ProjectImportService.prototype, "getTemplateUrl").mockReturnValue("http://api.test/template/");
  });

  it("validates on file select, then imports and closes on confirm", async () => {
    const validateSpy = vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(validation());
    const importSpy = vi
      .spyOn(ProjectImportService.prototype, "importCsv")
      .mockResolvedValue({ id: "1", status: "completed", async: false, created: 2, total: 2 });
    const handleClose = vi.fn();
    const onImported = vi.fn();

    const { container } = render(<ImportCSVModal isOpen handleClose={handleClose} onImported={onImported} />);
    const file = new File(["Name\nA"], "items.csv", { type: "text/csv" });
    chooseProjectAndFile(container, file);

    await waitFor(() => expect(validateSpy).toHaveBeenCalledWith("ws", "p1", file));

    const importBtn = await screen.findByRole("button", { name: IMPORT_BTN });
    expect(importBtn).toBeEnabled();
    await userEvent.click(importBtn);

    await waitFor(() => expect(importSpy).toHaveBeenCalledWith("ws", "p1", file, false));
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(toastCalls.some((t) => t.type === "success")).toBe(true);
  });

  it("locks to a given project and hides the selector", async () => {
    const validateSpy = vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(validation());

    const { container } = render(<ImportCSVModal isOpen handleClose={vi.fn()} projectId="p1" />);
    expect(screen.queryByTestId("project-select")).not.toBeInTheDocument();

    const file = new File(["Name\nA"], "items.csv", { type: "text/csv" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(validateSpy).toHaveBeenCalledWith("ws", "p1", file));
  });

  it("copies the AI rules document to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    vi.spyOn(ProjectImportService.prototype, "getImportRules").mockResolvedValue("# import rules");

    render(<ImportCSVModal isOpen handleClose={vi.fn()} projectId="p1" />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.copy_rules"));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("# import rules"));
    expect(toastCalls.some((t) => t.title === "workspace_settings.settings.imports.toasts.copied.title")).toBe(true);
  });

  it("shows a copy-failed toast when the clipboard is unavailable", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("blocked"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    vi.spyOn(ProjectImportService.prototype, "getImportRules").mockResolvedValue("# rules");

    render(<ImportCSVModal isOpen handleClose={vi.fn()} projectId="p1" />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.copy_rules"));

    await waitFor(() =>
      expect(toastCalls.some((t) => t.title === "workspace_settings.settings.imports.toasts.copy_failed.title")).toBe(
        true
      )
    );
  });

  it("copies the CSV template to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    vi.spyOn(ProjectImportService.prototype, "getTemplateCsv").mockResolvedValue("Name,State\n");

    render(<ImportCSVModal isOpen handleClose={vi.fn()} projectId="p1" />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.copy_template"));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Name,State\n"));
  });

  it("downloads the rules as a markdown file", async () => {
    const createObjectURL = vi.fn(() => "blob:rules");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const rulesSpy = vi.spyOn(ProjectImportService.prototype, "getImportRules").mockResolvedValue("# rules");

    render(<ImportCSVModal isOpen handleClose={vi.fn()} projectId="p1" />);
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.download_rules"));

    await waitFor(() => expect(rulesSpy).toHaveBeenCalledWith("ws", "p1"));
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("validates and imports pasted CSV content end-to-end", async () => {
    const validateSpy = vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(validation());
    const importSpy = vi
      .spyOn(ProjectImportService.prototype, "importCsv")
      .mockResolvedValue({ id: "1", status: "completed", async: false, created: 1, total: 1 });
    const onImported = vi.fn();
    const handleClose = vi.fn();

    render(<ImportCSVModal isOpen handleClose={handleClose} onImported={onImported} projectId="p1" />);

    await userEvent.click(screen.getByText("workspace_settings.settings.imports.tab_paste"));
    await userEvent.type(screen.getByLabelText("csv-paste"), "Name{Enter}Task A");
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.paste_validate"));

    await waitFor(() => expect(validateSpy).toHaveBeenCalled());
    expect((validateSpy.mock.calls[0][2] as File).name).toBe("pasted.csv");

    await userEvent.click(await screen.findByRole("button", { name: IMPORT_BTN }));
    await waitFor(() => expect(importSpy).toHaveBeenCalled());
    expect((importSpy.mock.calls[0][2] as File).name).toBe("pasted.csv");
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("blocks import while invalid rows exist until skip-invalid is toggled", async () => {
    vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(
      validation({ valid: 1, invalid: 1, errors: [{ row: 2, field: "State", message: "bad state" }] })
    );

    const { container } = render(<ImportCSVModal isOpen handleClose={vi.fn()} />);
    chooseProjectAndFile(container, new File(["x"], "a.csv", { type: "text/csv" }));

    const importBtn = await screen.findByRole("button", { name: IMPORT_BTN });
    expect(importBtn).toBeDisabled();

    await userEvent.click(screen.getByText("workspace_settings.settings.imports.skip_invalid"));
    expect(importBtn).toBeEnabled();
  });

  it("passes skip_invalid=true to the import call when the user opts in", async () => {
    vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(
      validation({ valid: 1, invalid: 1, errors: [{ row: 2, field: "State", message: "bad" }] })
    );
    const importSpy = vi
      .spyOn(ProjectImportService.prototype, "importCsv")
      .mockResolvedValue({ id: "1", status: "completed", async: false, created: 1, total: 2 });

    const { container } = render(<ImportCSVModal isOpen handleClose={vi.fn()} />);
    const file = new File(["x"], "a.csv", { type: "text/csv" });
    chooseProjectAndFile(container, file);

    await screen.findByRole("button", { name: IMPORT_BTN });
    await userEvent.click(screen.getByText("workspace_settings.settings.imports.skip_invalid"));
    await userEvent.click(screen.getByRole("button", { name: IMPORT_BTN }));

    await waitFor(() => expect(importSpy).toHaveBeenCalledWith("ws", "p1", file, true));
  });

  it("shows a queued toast for a large (async) import", async () => {
    vi.spyOn(ProjectImportService.prototype, "validateCsv").mockResolvedValue(validation());
    vi.spyOn(ProjectImportService.prototype, "importCsv").mockResolvedValue({
      id: "1",
      status: "queued",
      async: true,
      total: 2,
    });
    const onImported = vi.fn();

    const { container } = render(<ImportCSVModal isOpen handleClose={vi.fn()} onImported={onImported} />);
    chooseProjectAndFile(container, new File(["x"], "a.csv", { type: "text/csv" }));

    await userEvent.click(await screen.findByRole("button", { name: IMPORT_BTN }));

    await waitFor(() => expect(onImported).toHaveBeenCalled());
    expect(toastCalls.some((t) => t.type === "success")).toBe(true);
    expect(toastCalls.at(-1)?.title).toBe("workspace_settings.settings.imports.toasts.queued.title");
  });
});
