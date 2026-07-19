/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TCsvImportError = {
  row: number;
  field: string;
  // English fallback; `code` + `params` let the frontend localize the message.
  message: string;
  code?: string;
  params?: Record<string, string | number>;
};

export type TCsvRowError = Pick<TCsvImportError, "field" | "message" | "code" | "params">;

export type TCsvPreviewAssignee = { id: string; display_name: string; avatar_url: string | null };
export type TCsvPreviewLabel = { name: string; color: string | null; is_new?: boolean };
export type TCsvPreviewState = { name: string; color: string };

/** A valid row resolved to display values, ready to render like a real work item. */
export type TCsvPreviewRow = {
  row: number;
  name: string;
  has_description: boolean;
  priority: string;
  state: TCsvPreviewState | null;
  assignees: TCsvPreviewAssignee[];
  labels: TCsvPreviewLabel[];
  start_date: string | null;
  target_date: string | null;
  estimate: string | null;
  parent: string | null;
  cycle: string | null;
  modules: string[];
  type: string | null;
};

/** An invalid row: the raw cells the user typed plus the reasons it failed. */
export type TCsvInvalidRow = {
  row: number;
  name: string;
  values: Record<string, string>;
  errors: TCsvRowError[];
};

export type TCsvImportValidation = {
  total: number;
  valid: number;
  invalid: number;
  errors: TCsvImportError[];
  sample: TCsvPreviewRow[];
  // Always present from the API; optional here so older/partial fixtures type-check.
  invalid_sample?: TCsvInvalidRow[];
  preview_limit?: number;
  sample_truncated?: boolean;
};

export type TCsvImportResult = {
  id: string;
  status: string;
  async: boolean;
  created?: number;
  skipped?: number;
  failed?: number;
  total: number;
  errors?: TCsvImportError[];
};

export type TIssueImportRecord = {
  id: string;
  file_name: string;
  status: "queued" | "processing" | "completed" | "failed";
  total_rows: number;
  created_rows: number;
  skipped_rows: number;
  failed_rows: number;
  error_report: TCsvImportError[];
  created_at: string;
  initiated_by_detail?: { display_name?: string; email?: string } | null;
};

const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } };

export class ProjectImportService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private importBase(workspaceSlug: string, projectId: string): string {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/import-csv/`;
  }

  /** Dry-run: parse + resolve + validate the CSV without writing anything. */
  async validateCsv(workspaceSlug: string, projectId: string, file: File): Promise<TCsvImportValidation> {
    const formData = new FormData();
    formData.append("file", file);
    return this.post(`${this.importBase(workspaceSlug, projectId)}validate/`, formData, MULTIPART)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Commit the import. Small files return a full result; large ones return a queued record. */
  async importCsv(
    workspaceSlug: string,
    projectId: string,
    file: File,
    skipInvalid: boolean
  ): Promise<TCsvImportResult> {
    const formData = new FormData();
    formData.append("file", file);
    if (skipInvalid) formData.append("skip_invalid", "true");
    return this.post(this.importBase(workspaceSlug, projectId), formData, MULTIPART)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getImports(workspaceSlug: string, projectId: string): Promise<TIssueImportRecord[]> {
    return this.get(this.importBase(workspaceSlug, projectId))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** The template as raw CSV text (for copy-to-clipboard). */
  async getTemplateCsv(workspaceSlug: string, projectId: string): Promise<string> {
    return this.get(`${this.importBase(workspaceSlug, projectId)}template/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** A Markdown rules document with this project's live allowed values, for AI-assisted CSVs. */
  async getImportRules(workspaceSlug: string, projectId: string): Promise<string> {
    return this.get(`${this.importBase(workspaceSlug, projectId)}rules/`)
      .then((response) => response?.data?.markdown ?? "")
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Absolute URL for the downloadable CSV template (browser handles the download). */
  getTemplateUrl(workspaceSlug: string, projectId: string): string {
    return `${this.baseURL}${this.importBase(workspaceSlug, projectId)}template/`;
  }
}
