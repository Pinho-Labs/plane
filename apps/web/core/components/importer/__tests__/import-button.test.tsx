/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImportWorkItemsButton } from "../import-button";

// The button renders the import modal, which reads projects from the stores.
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
const TAB_UPLOAD = "workspace_settings.settings.imports.tab_upload";

describe("ImportWorkItemsButton", () => {
  it("opens the import modal (locked to the project) when clicked", async () => {
    render(<ImportWorkItemsButton projectId="p1" />);
    // Modal is closed initially — its tabs are not rendered.
    expect(screen.queryByText(TAB_UPLOAD)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText(IMPORT_BTN));

    // Modal open -> the upload/paste tabs are now visible.
    expect(screen.getByText(TAB_UPLOAD)).toBeInTheDocument();
  });
});
