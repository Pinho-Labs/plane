/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import { ProjectImportService } from "../project-import.service";

// The service methods return an AxiosResponse; only `data` matters here.
const asResponse = (data: unknown) => ({ data }) as unknown as AxiosResponse;

describe("ProjectImportService", () => {
  it("builds the template URL from the import base path", () => {
    const service = new ProjectImportService();
    expect(service.getTemplateUrl("ws", "proj-1")).toContain(
      "/api/workspaces/ws/projects/proj-1/issues/import-csv/template/"
    );
  });

  it("validateCsv posts multipart to the validate endpoint and unwraps data", async () => {
    const service = new ProjectImportService();
    const spy = vi
      .spyOn(service, "post")
      .mockResolvedValue(asResponse({ total: 2, valid: 2, invalid: 0, errors: [], sample: [] }));
    const file = new File(["Name\nA"], "x.csv", { type: "text/csv" });

    const result = await service.validateCsv("ws", "proj-1", file);

    const [url, formData, config] = spy.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws/projects/proj-1/issues/import-csv/validate/");
    expect(formData).toBeInstanceOf(FormData);
    expect((formData as FormData).get("file")).toBeInstanceOf(File);
    expect(config).toEqual({ headers: { "Content-Type": "multipart/form-data" } });
    expect(result.valid).toBe(2);
  });

  it("importCsv appends skip_invalid=true and posts to the commit endpoint", async () => {
    const service = new ProjectImportService();
    const spy = vi
      .spyOn(service, "post")
      .mockResolvedValue(asResponse({ id: "1", status: "completed", async: false, created: 1, total: 1 }));
    const file = new File(["Name\nA"], "x.csv", { type: "text/csv" });

    const result = await service.importCsv("ws", "proj-1", file, true);

    const [url, formData] = spy.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws/projects/proj-1/issues/import-csv/");
    expect((formData as FormData).get("skip_invalid")).toBe("true");
    expect(result.created).toBe(1);
  });

  it("importCsv omits skip_invalid when false", async () => {
    const service = new ProjectImportService();
    const spy = vi
      .spyOn(service, "post")
      .mockResolvedValue(asResponse({ id: "1", status: "completed", async: false, total: 1 }));
    const file = new File(["Name\nA"], "x.csv", { type: "text/csv" });

    await service.importCsv("ws", "proj-1", file, false);

    const [, formData] = spy.mock.calls[0];
    expect((formData as FormData).get("skip_invalid")).toBeNull();
  });

  it("getImportRules reads the rules endpoint and unwraps markdown", async () => {
    const service = new ProjectImportService();
    const spy = vi.spyOn(service, "get").mockResolvedValue(asResponse({ markdown: "# rules" }));

    const result = await service.getImportRules("ws", "proj-1");

    expect(spy).toHaveBeenCalledWith("/api/workspaces/ws/projects/proj-1/issues/import-csv/rules/");
    expect(result).toBe("# rules");
  });

  it("getTemplateCsv reads the template endpoint as text", async () => {
    const service = new ProjectImportService();
    const spy = vi.spyOn(service, "get").mockResolvedValue(asResponse("Name,State\n"));

    const result = await service.getTemplateCsv("ws", "proj-1");

    expect(spy).toHaveBeenCalledWith("/api/workspaces/ws/projects/proj-1/issues/import-csv/template/");
    expect(result).toBe("Name,State\n");
  });

  it("getImports reads the history endpoint", async () => {
    const service = new ProjectImportService();
    const spy = vi.spyOn(service, "get").mockResolvedValue(asResponse([{ id: "1" }]));

    const result = await service.getImports("ws", "proj-1");

    expect(spy).toHaveBeenCalledWith("/api/workspaces/ws/projects/proj-1/issues/import-csv/");
    expect(result).toHaveLength(1);
  });

  it("rethrows the server error payload on failure", async () => {
    const service = new ProjectImportService();
    vi.spyOn(service, "post").mockRejectedValue({ response: { data: { error: "boom" } } });
    const file = new File(["Name\nA"], "x.csv", { type: "text/csv" });

    await expect(service.validateCsv("ws", "proj-1", file)).rejects.toEqual({ error: "boom" });
  });
});
