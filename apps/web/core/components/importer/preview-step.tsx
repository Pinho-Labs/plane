/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, FileText, Search } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { PriorityIcon } from "@plane/propel/icons";
import { Avatar, AvatarGroup, Checkbox } from "@plane/ui";
import { cn, getFileURL, renderFormattedDate } from "@plane/utils";
// services
import type { TCsvImportValidation, TCsvInvalidRow, TCsvPreviewRow, TCsvRowError } from "@/services/project";

type Props = {
  validation: TCsvImportValidation;
  skipInvalid: boolean;
  onToggleSkip: (value: boolean) => void;
};

type TTab = "all" | "valid" | "error";
type TRow = { kind: "valid"; data: TCsvPreviewRow } | { kind: "invalid"; data: TCsvInvalidRow };

const PAGE_SIZE = 25;

// Sticky-left column widths must agree between <th> and <td> so the two frozen
// columns line up while the rest of the table scrolls under them.
const NUM_W = "w-12 min-w-12";
const NAME_LEFT = "left-12";

const HEADERS: { key: string; i18n: string; className?: string }[] = [
  { key: "state", i18n: "common.state" },
  { key: "priority", i18n: "common.priority" },
  { key: "assignees", i18n: "common.assignees" },
  { key: "labels", i18n: "common.labels" },
  { key: "start_date", i18n: "common.order_by.start_date" },
  { key: "target_date", i18n: "common.order_by.due_date" },
  { key: "estimate", i18n: "common.estimate" },
  { key: "parent", i18n: "common.parent" },
  { key: "cycle", i18n: "common.cycle" },
  { key: "modules", i18n: "common.modules" },
  { key: "type", i18n: "workspace_settings.settings.imports.preview.type" },
];

const Dash = () => <span className="text-tertiary">—</span>;

export const ImportPreviewStep = function ImportPreviewStep(props: Props) {
  const { validation, skipInvalid, onToggleSkip } = props;
  const { t } = useTranslation();

  const [tab, setTab] = useState<TTab>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const hasErrors = validation.invalid > 0;
  const invalidSample = validation.invalid_sample ?? [];
  const validSample = validation.sample ?? [];
  // File-level problems (empty file, missing Name column, row cap) aren't tied
  // to a data row, so they get a banner instead of a table row.
  const fileErrors = (validation.errors ?? []).filter((e) => e.row === 0);

  const rows = useMemo<TRow[]>(() => {
    const merged: TRow[] = [];
    if (tab !== "error") validSample.forEach((data) => merged.push({ kind: "valid", data }));
    if (tab !== "valid") invalidSample.forEach((data) => merged.push({ kind: "invalid", data }));
    merged.sort((a, b) => a.data.row - b.data.row);
    const q = query.trim().toLowerCase();
    if (!q) return merged;
    return merged.filter((r) => (r.data.name || "").toLowerCase().includes(q));
  }, [tab, query, validSample, invalidSample]);

  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = rows.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const from = rows.length === 0 ? 0 : safePage * PAGE_SIZE + 1;
  const to = Math.min(rows.length, safePage * PAGE_SIZE + PAGE_SIZE);

  const switchTab = (next: TTab) => {
    setTab(next);
    setPage(0);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3 text-13 font-medium">
          <span className="flex items-center gap-1.5 text-success-primary">
            <CheckCircle2 className="size-4" />
            {t("workspace_settings.settings.imports.ready_count", { count: validation.valid })}
          </span>
          {hasErrors && (
            <span className="flex items-center gap-1.5 text-danger-primary">
              <AlertTriangle className="size-4" />
              {t("workspace_settings.settings.imports.error_count", { count: validation.invalid })}
            </span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded-md border border-subtle bg-layer-1 p-0.5">
            {(
              [
                { id: "all", label: t("workspace_settings.settings.imports.preview.tab_all"), count: validation.total },
                { id: "valid", label: t("workspace_settings.settings.imports.preview.tab_valid"), count: validation.valid },
                { id: "error", label: t("workspace_settings.settings.imports.preview.tab_errors"), count: validation.invalid },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => switchTab(item.id)}
                aria-pressed={tab === item.id}
                className={cn(
                  "flex items-center gap-1.5 rounded px-2.5 py-1 text-12 font-medium text-secondary transition-colors hover:text-primary",
                  tab === item.id && "bg-surface-1 text-primary shadow-sm"
                )}
              >
                {item.label}
                <span
                  className={cn(
                    "rounded-full px-1.5 text-10 font-semibold tabular-nums text-tertiary",
                    // Colour is a status signal, not a selection cue.
                    item.id === "error" && item.count > 0 && "bg-danger-subtle text-danger-primary",
                    item.id === "valid" && item.count > 0 && "bg-success-subtle text-success-primary"
                  )}
                >
                  {item.count}
                </span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 rounded-md border border-subtle bg-layer-1 px-2 py-1">
            <Search className="size-3.5 text-tertiary" />
            <input
              type="text"
              aria-label={t("workspace_settings.settings.imports.preview.filter_placeholder")}
              placeholder={t("workspace_settings.settings.imports.preview.filter_placeholder")}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
              className="w-32 bg-transparent text-12 text-primary outline-none placeholder:text-placeholder"
            />
          </div>
        </div>
      </div>

      {fileErrors.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-danger-subtle bg-danger-subtle/40 px-3 py-2 text-12 text-danger-primary">
          {fileErrors.map((e, i) => (
            <span key={`${e.code}-${i}`} className="flex items-center gap-1.5">
              <AlertTriangle className="size-3.5 flex-shrink-0" />
              {translateError(t, e)}
            </span>
          ))}
        </div>
      )}

      {validation.sample_truncated && (
        <div className="rounded-md border border-accent-subtle bg-accent-subtle/40 px-3 py-2 text-12 text-secondary">
          {t("workspace_settings.settings.imports.preview.note", {
            shown: validSample.length,
            valid: validation.valid,
          })}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-subtle">
        <div className="max-h-[46vh] overflow-auto">
          <table className="w-max min-w-full border-separate border-spacing-0 text-13">
            <thead>
              <tr>
                <th
                  className={cn(
                    "sticky left-0 top-0 z-30 border-b border-subtle bg-layer-1 px-3 py-2 text-right text-10 font-semibold uppercase tracking-wider text-tertiary",
                    NUM_W
                  )}
                >
                  #
                </th>
                <th
                  className={cn(
                    "sticky top-0 z-30 min-w-[220px] max-w-[220px] border-b border-r border-subtle bg-layer-1 px-3 py-2 text-left text-10 font-semibold uppercase tracking-wider text-tertiary",
                    NAME_LEFT
                  )}
                >
                  {t("common.name")}
                </th>
                {HEADERS.map((h) => (
                  <th
                    key={h.key}
                    className="sticky top-0 z-20 whitespace-nowrap border-b border-subtle bg-layer-1 px-3 py-2 text-left text-10 font-semibold uppercase tracking-wider text-tertiary"
                  >
                    {t(h.i18n)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.length === 0 ? (
                <tr>
                  <td colSpan={HEADERS.length + 2} className="px-3 py-8 text-center text-12 text-tertiary">
                    {t("workspace_settings.settings.imports.preview.no_rows")}
                  </td>
                </tr>
              ) : (
                pageRows.map((row) =>
                  row.kind === "valid" ? (
                    <ValidRow key={`v-${row.data.row}`} row={row.data} t={t} />
                  ) : (
                    <InvalidRow key={`i-${row.data.row}`} row={row.data} t={t} />
                  )
                )
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between text-12 text-tertiary">
        <span className="tabular-nums">
          {t("workspace_settings.settings.imports.preview.showing", { from, to, total: rows.length })}
        </span>
        {pageCount > 1 && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="grid size-6 place-items-center rounded hover:bg-layer-1 disabled:opacity-40"
              aria-label={t("common.prev")}
            >
              <ChevronLeft className="size-4" />
            </button>
            <span className="tabular-nums text-secondary">
              {safePage + 1} / {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="grid size-6 place-items-center rounded hover:bg-layer-1 disabled:opacity-40"
              aria-label={t("common.next")}
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        )}
      </div>

      {hasErrors && (
        <button
          type="button"
          className="flex w-max cursor-pointer items-center gap-2"
          onClick={() => onToggleSkip(!skipInvalid)}
        >
          <Checkbox checked={skipInvalid} onChange={() => onToggleSkip(!skipInvalid)} />
          <span className="text-13">{t("workspace_settings.settings.imports.skip_invalid")}</span>
        </button>
      )}
    </div>
  );
};

type TFn = ReturnType<typeof useTranslation>["t"];

// Backend validation messages arrive with a stable `code` + `params`; translate
// them here so they follow the user's locale, falling back to the English text.
const translateError = (t: TFn, error: TCsvRowError): string =>
  error.code
    ? t(`workspace_settings.settings.imports.errors.${error.code}`, { ...(error.params ?? {}), defaultValue: error.message })
    : error.message;

const TD = "whitespace-nowrap border-b border-subtle px-3 py-2 align-middle";

function ValidRow({ row, t }: { row: TCsvPreviewRow; t: TFn }) {
  return (
    <tr className="group">
      <td className={cn("sticky left-0 z-10 bg-surface-1 text-right tabular-nums text-tertiary group-hover:bg-layer-1", TD, NUM_W)}>
        {row.row}
      </td>
      <td
        className={cn(
          "sticky z-10 min-w-[220px] max-w-[220px] truncate border-r bg-surface-1 font-medium text-primary group-hover:bg-layer-1",
          TD,
          NAME_LEFT
        )}
      >
        <span className="flex items-center gap-1.5">
          {row.has_description && <FileText className="size-3.5 flex-shrink-0 text-tertiary" />}
          <span className="truncate">{row.name}</span>
        </span>
      </td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.state ? (
          <span className="flex items-center gap-1.5">
            <span className="size-2 flex-shrink-0 rounded-full" style={{ backgroundColor: row.state.color }} />
            <span className="text-secondary">{row.state.name}</span>
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.priority === "none" ? (
          <span className="flex items-center gap-1.5 text-tertiary">
            <PriorityIcon priority="none" size={13} />
            {t("none")}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-secondary">
            <PriorityIcon priority={row.priority as "urgent" | "high" | "medium" | "low"} size={13} withContainer />
            {t(row.priority)}
          </span>
        )}
      </td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.assignees.length ? (
          <AvatarGroup size="sm">
            {row.assignees.map((a) => (
              <Avatar key={a.id} name={a.display_name} src={getFileURL(a.avatar_url ?? "")} />
            ))}
          </AvatarGroup>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.labels.length ? (
          <span className="flex items-center gap-1">
            {row.labels.map((l) => (
              <span
                key={l.name}
                className="inline-flex items-center gap-1 rounded-full border border-subtle px-2 py-0.5 text-11 text-secondary"
              >
                <span
                  className="size-1.5 flex-shrink-0 rounded-full"
                  style={{ backgroundColor: l.color ?? "var(--color-text-tertiary)" }}
                />
                {l.name}
                {l.is_new && <span className="text-10 text-accent-primary">{t("workspace_settings.settings.imports.preview.new_label")}</span>}
              </span>
            ))}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "tabular-nums text-secondary bg-surface-1 group-hover:bg-layer-1")}>
        {row.start_date ? renderFormattedDate(row.start_date) : <Dash />}
      </td>
      <td className={cn(TD, "tabular-nums text-secondary bg-surface-1 group-hover:bg-layer-1")}>
        {row.target_date ? renderFormattedDate(row.target_date) : <Dash />}
      </td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.estimate ? (
          <span className="inline-grid h-5 min-w-5 place-items-center rounded border border-subtle bg-layer-1 px-1.5 text-11 font-medium tabular-nums text-secondary">
            {row.estimate}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "text-secondary bg-surface-1 group-hover:bg-layer-1")}>{row.parent || <Dash />}</td>
      <td className={cn(TD, "text-secondary bg-surface-1 group-hover:bg-layer-1")}>{row.cycle || <Dash />}</td>
      <td className={cn(TD, "bg-surface-1 group-hover:bg-layer-1")}>
        {row.modules.length ? (
          <span className="flex items-center gap-1">
            {row.modules.map((m) => (
              <span key={m} className="rounded-full border border-subtle px-2 py-0.5 text-11 text-secondary">
                {m}
              </span>
            ))}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={cn(TD, "text-secondary bg-surface-1 group-hover:bg-layer-1")}>{row.type || <Dash />}</td>
    </tr>
  );
}

function InvalidRow({ row, t }: { row: TCsvInvalidRow; t: TFn }) {
  const v = row.values;
  // Cells show the raw text the user typed; the field that failed is underlined.
  const badFields = new Set(row.errors.map((e) => e.field.toLowerCase()));
  const raw = (key: string, label?: string) => {
    const value = v[key];
    if (!value) return <Dash />;
    const isBad = badFields.has((label ?? key).toLowerCase());
    return <span className={isBad ? "text-danger-primary underline decoration-wavy" : "text-tertiary"}>{value}</span>;
  };

  return (
    <tr className="group">
      <td className={cn("sticky left-0 z-10 bg-danger-subtle/60 text-right tabular-nums text-danger-primary", TD, NUM_W)}>
        {row.row}
      </td>
      <td className={cn("sticky z-10 min-w-[220px] max-w-[220px] border-r bg-danger-subtle/60", TD, NAME_LEFT)}>
        <span className={cn("block truncate font-medium", row.name ? "text-primary" : "italic text-tertiary")}>
          {row.name || t("workspace_settings.settings.imports.preview.unnamed")}
        </span>
        <span className="mt-0.5 flex items-start gap-1 whitespace-normal text-11 font-normal text-danger-primary">
          <AlertTriangle className="mt-0.5 size-3 flex-shrink-0" />
          <span>{row.errors.map((e) => translateError(t, e)).join(" · ")}</span>
        </span>
      </td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("state", "State")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("priority", "Priority")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("assignees", "Assignees")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("labels", "Labels")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("start_date", "Start Date")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("target_date", "Target Date")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("estimate", "Estimate")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("parent", "Parent")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("cycle", "Cycle")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("modules", "Modules")}</td>
      <td className={cn(TD, "bg-danger-subtle/30")}>{raw("type", "Work Item Type")}</td>
    </tr>
  );
}
