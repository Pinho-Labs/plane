# Task: CSV Bulk Import for Work Items

## Summary

Add the ability to **create many work items (issues) at once by uploading a CSV file** into a
target project. Today Plane supports only single work-item creation (via the create modal) and
CSV/JSON/xlsx **export** — there is no import path in this repository (the legacy Jira/GitHub
`Importer` scaffolding is a dead stub whose backend lives in the EE/silo service).

The feature ships:

1. A **downloadable CSV template** whose columns are a 1:1 match of the fields in the work-item
   creation modal (name, description, state, priority, assignees, labels, start/target date,
   estimate, parent, cycle, modules, and — when enabled — work-item type).
2. A **backend import pipeline** that parses the CSV, resolves human-friendly values
   (state name, assignee email, label name, …) to their internal IDs, validates every row, and
   creates the issues with the same side effects as the normal create flow (sequence assignment,
   assignee/label/module/cycle membership, activity log, webhooks).
3. A **frontend import experience** — a drop-zone upload modal with a validation/preview step and
   a new **Settings → Imports** page with import history — built to match the existing
   Export modal / Export settings UX exactly.
4. **Automated tests** on both sides: pytest contract + unit tests for the API and parser, and a
   Vitest suite for the frontend parsing/validation/mapping logic.

## Description

A project manager migrating from a spreadsheet, Jira export, or another tool needs to seed a Plane
project with dozens or hundreds of work items in one shot. They download the template, fill it in
with familiar names (state = "In Progress", assignee = "jane@acme.com", labels = "bug;backend"),
upload it, review a preview that flags any bad rows, and commit. Valid rows become real work items;
invalid rows are reported with row numbers and reasons so they can be fixed and re-uploaded.

---

## Goals & non-goals

**Goals**

- Bulk-create work items from a CSV into a single, user-selected project.
- Template columns = every field in the create modal, using human-friendly values, not UUIDs.
- Row-level validation with a dry-run preview before anything is written.
- Match existing UI/UX (Export modal, Settings pages, dropzone attachments, toasts, i18n).
- Idempotency-friendly: support optional `external_id` so re-imports don't duplicate.

**Non-goals (v1)**

- Updating existing work items via CSV (create-only; `external_id` de-dupe is the only update-ish nuance).
- Importing comments, links, relations, sub-issue trees, or attachments (export has them; import defers them).
- Importing from Jira/Asana/GitHub (that stays in the EE silo service).
- Custom EE "additional properties" columns (leave a documented extension point; see Open Questions).

---

## CSV template specification

The template mirrors `DEFAULT_WORK_ITEM_FORM_VALUES`
(`packages/constants/src/issue/modal.ts`) and the `TIssue` payload. Values are **human-friendly**
and resolved server-side to IDs. The **target project is chosen in the UI**, not in the CSV, so
per-project references (state/label/cycle/module/parent) resolve unambiguously within that project.

| CSV column       | Maps to (create payload) | Required | Format / accepted values                          | Resolution                                                            |
| ---------------- | ------------------------ | -------- | ------------------------------------------------- | --------------------------------------------------------------------- |
| `Name`           | `name`                   | **Yes**  | text, ≤255 chars                                  | direct                                                                |
| `Description`    | `description_html`       | No       | plain text or minimal HTML; wrapped to `<p>…</p>` | direct (stripped/sanitized)                                           |
| `State`          | `state_id`               | No¹      | State name (e.g. "Todo")                          | name → `State` in project (case-insensitive); blank → project default |
| `Priority`       | `priority`               | No       | `urgent`/`high`/`medium`/`low`/`none`             | direct choice (default `none`)                                        |
| `Assignees`      | `assignee_ids[]`         | No       | `;`-separated **emails**                          | email → `User` (must be active project member, role ≥ 15)             |
| `Labels`         | `label_ids[]`            | No       | `;`-separated names                               | name → `Label` in project (auto-create optional, see Open Q)          |
| `Start Date`     | `start_date`             | No       | `YYYY-MM-DD`                                      | direct; must be ≤ Target Date                                         |
| `Target Date`    | `target_date`            | No       | `YYYY-MM-DD`                                      | direct; must be ≥ Start Date                                          |
| `Estimate`       | `estimate_point`         | No²      | estimate point value/label                        | value → `EstimatePoint` in project's active estimate                  |
| `Parent`         | `parent_id`              | No       | work-item identifier `PROJ-123`                   | `{identifier}-{sequence_id}` → `Issue` in project                     |
| `Cycle`          | `cycle_id`               | No²      | cycle name (single)                               | name → `Cycle`; creates `CycleIssue` row post-create                  |
| `Modules`        | `module_ids[]`           | No²      | `;`-separated module names                        | name → `Module`; creates `ModuleIssue` rows post-create               |
| `Work Item Type` | `type_id`                | No²      | type name (EE only)                               | name → `IssueType`; omitted/ignored when EE types disabled            |
| `External ID`    | `external_id`            | No       | any string                                        | direct; enables re-import de-dupe with `external_source="csv"`        |

¹ State is effectively required by the model but auto-defaults to the project's default state when blank.
² Only meaningful when the project enables that feature (`cycle_view`, `module_view`, estimates,
EE issue types). If a column references a disabled feature, the row is flagged in the preview.

**Multi-value separator:** `;` (semicolon), so commas inside CSV cells stay unambiguous.
**Encoding:** UTF-8. **Delimiter:** comma. First row = headers (case-insensitive match; extra/unknown
columns are ignored with a warning; missing optional columns are fine).

**Example template row**

```csv
Name,Description,State,Priority,Assignees,Labels,Start Date,Target Date,Estimate,Parent,Cycle,Modules,Work Item Type,External ID
"Fix login redirect","User is bounced to /home",In Progress,high,jane@acme.com;bob@acme.com,bug;auth,2026-07-20,2026-07-25,3,PROJ-12,Sprint 5,Auth;Web,Bug,ext-1001
```

The template is served by the backend (single source of truth for column names) and offered as a
**"Download template"** button in the import modal and on the Imports settings page.

---

## Backend design (`apps/api`, Django + DRF)

### Key facts driving the design (from model analysis)

- `Issue.save()` assigns `sequence_id` under a per-project PostgreSQL advisory lock and writes the
  `IssueSequence` row. **We must call `Issue.save()` per row** (or replicate the locked sequence
  logic) — a naive `bulk_create` would break the `PROJ-N` numbering.
- The create serializer (`IssueCreateSerializer`) handles **assignees + labels** through-rows but
  **not cycle/module** — those need explicit `CycleIssue` / `ModuleIssue` inserts after create.
- Side effects to preserve: `issue_activity.delay(type="issue.activity.created", …)` (activity log
  - notifications) and `model_activity.delay(model_name="issue", …)` (webhooks), matching
    `IssueViewSet.create` in `app/views/issue/base.py`.
- References on create are by UUID; the export serializer shows the human-friendly rendering we
  invert here.

### New files

```
apps/api/plane/utils/importers/__init__.py
apps/api/plane/utils/importers/csv_issue_importer.py   # parse + resolve + validate (pure, testable)
apps/api/plane/utils/importers/template.py             # canonical column spec + template CSV bytes
apps/api/plane/app/serializers/importer.py             # extend: IssueCSVImportRowSerializer, IssueImportSerializer
apps/api/plane/app/views/issue/import_csv.py           # IssueCSVImportEndpoint, IssueCSVTemplateEndpoint
apps/api/plane/bgtasks/issue_import_task.py            # async creation for large files (Celery)
apps/api/plane/db/models/importer.py                   # extend: add "csv" service + import model (below)
```

### Data model

Reuse the existing `Importer` model (`db/models/importer.py`) by widening `service` choices to
include `("csv", "CSV")`, and use its `status` (`queued|processing|completed|failed`), `metadata`
(filename, row counts), and `data`/`imported_data` (per-row results, error report) fields. This
gives us the **import-history** list for free (parallels `PrevExports`). No new table required for v1;
if the FK-to-`APIToken` requirement is awkward for web-app flows, make `token` nullable in a
migration or add a slim `IssueImport(ProjectBaseModel)` model — decide in Phase 0.

### Endpoints (web-app API, session auth, under `/api/`)

Registered in `apps/api/plane/app/urls/issue.py`:

| Method & path                                              | View                                  | Purpose                                                                     |
| ---------------------------------------------------------- | ------------------------------------- | --------------------------------------------------------------------------- |
| `GET  …/projects/<project_id>/issues/import-csv/template/` | `IssueCSVTemplateEndpoint`            | Download the canonical template CSV                                         |
| `POST …/projects/<project_id>/issues/import-csv/validate/` | `IssueCSVImportEndpoint` (`validate`) | Dry-run: parse + resolve + validate, return preview & errors, write nothing |
| `POST …/projects/<project_id>/issues/import-csv/`          | `IssueCSVImportEndpoint` (`create`)   | Commit: create valid rows, return summary + per-row results                 |
| `GET  …/projects/<project_id>/issues/import-csv/`          | `IssueCSVImportEndpoint` (`list`)     | Import history for the project                                              |

Multipart upload (`request.FILES["file"]`), guarded by project membership + create permission
(reuse the permission classes on `IssueViewSet`). Enforce a max file size and a max row cap
(e.g. 5,000 rows) with a clear error; `log()`-style surface the cap so it isn't silent.

### Import flow (per request)

1. **Parse** — stream the CSV (`csv.DictReader`), normalize headers, coerce/trim values.
2. **Build resolution maps once per project** (avoid N queries): `{state_name→id}`,
   `{email→member_id}` (active, role ≥ 15), `{label_name→id}`, `{cycle_name→id}`,
   `{module_name→id}`, `{estimate_value→id}`, `{PROJ-N→issue_id}`, `{type_name→id}`.
3. **Validate each row** via `IssueCSVImportRowSerializer` → collect `{row, field, message}` errors;
   reuse `IssueCreateSerializer`'s referential rules (state in project, assignees are members,
   start ≤ target, point 0–12, etc.). Sanitize description HTML.
4. **Validate mode:** return `{total, valid, invalid, preview:[…first N resolved rows…], errors:[…]}`
   — nothing written.
5. **Commit mode:**
   - Small files (≤ threshold, e.g. 200 rows): synchronous. Wrap in `transaction.atomic()`
     (optionally `partial=True` to skip only bad rows). For each valid row call
     `IssueCreateSerializer(...).save()` (gets sequence, assignees, labels), then insert
     `ModuleIssue` / `CycleIssue` rows, then `issue_activity.delay(...)` + `model_activity.delay(...)`.
   - Large files: create an `Importer(service="csv", status="queued")` row and dispatch
     `issue_import_task.delay(importer_id, …)`; the Celery task does the same per-row work,
     updates `status`/`metadata`, and stores the error report in `imported_data`. Frontend polls
     the history endpoint (like exports).
   - De-dupe: if `External ID` present, `get_or_create` on `(project, external_source="csv",
external_id)` so re-uploads are safe.
6. **Response:** `{created, skipped, failed, errors:[{row, messages}], importer_id}`.

### Why a dedicated serializer + pure parser

Keeping `csv_issue_importer.py` pure (no request/ORM writes; takes prefetched maps) makes it unit
testable without a DB and mirrors the existing pure `CSVFormatter` in `utils/porters/formatters.py`
(which already has sanitization unit tests we parallel).

---

## Frontend design (`apps/web`, Next.js + React + MobX + `@plane/ui`)

### UX brainstorm & chosen approach

**Two entry points**, matching how Export works:

- **Contextual:** an **"Import"** action (next to Export) in the work-items header / project
  quick-actions that opens the import modal pre-scoped to the current project.
- **Settings hub:** a new **Settings → Imports** page (parallel to Settings → Exports) with the
  import form + a **history list** of previous imports and their status.

**The import modal — a 3-step wizard inside one `ModalCore`** (mirrors `Exporter` in
`core/components/exporter/export-modal.tsx`, `EModalWidth.XL`/`XXL`, `EModalPosition.CENTER`):

1. **Upload** — a react-dropzone drop area (pattern from
   `core/components/issues/attachment/attachment-upload.tsx`, `accept={{ "text/csv": [".csv"] }}`,
   `multiple:false`), a **target-project `CustomSearchSelect`** (only projects the user can create
   in — `useUserPermissions().projectsWithCreatePermissions`), and a prominent
   **"Download CSV template"** link. Client-side guard on extension + size.
2. **Preview & validate** — on file select, POST to `…/validate/`; render a compact table of the
   first N resolved rows plus a **red banner listing invalid rows** ("Row 14: assignee
   'x@y.com' is not a member"). Show counts: _"142 ready · 3 with errors"_. A toggle
   **"Skip invalid rows and import the rest"** vs. block-until-clean.
3. **Confirm & result** — primary **Import** button (`loading` state like the export button); on
   success show a success toast (`setToast({ type: TOAST_TYPE.SUCCESS })`), refresh the issues
   list/history, and route to `…/settings/imports` for large/async imports.

Rationale: the validate-before-commit step is the single most important UX affordance — spreadsheet
data is messy, and surfacing row-level errors before anything is written prevents half-imported
projects. It reuses components users already know (dropzone, `CustomSearchSelect`, `CustomSelect`,
toasts) so it feels native.

### New / changed files

```
apps/web/core/services/project/project-import.service.ts     # ProjectImportService extends APIService
apps/web/core/components/importer/import-csv-modal.tsx        # the wizard modal (mirrors export-modal.tsx)
apps/web/core/components/importer/upload-step.tsx             # dropzone + project select + template link
apps/web/core/components/importer/preview-step.tsx            # validation preview table + error banner
apps/web/core/components/importer/guide.tsx                   # ImportGuide (form + PrevImports history)
apps/web/core/components/importer/prev-imports.tsx            # history list (mirrors PrevExports)
apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/imports/page.tsx
apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/imports/header.tsx
packages/constants/src/workspace.ts                          # add IMPORTERS_LIST csv entry (type:"import")
packages/constants/src/settings/workspace.ts                 # add `imports` to WORKSPACE_SETTINGS + grouped
packages/i18n/src/locales/*/*.json                           # import keys (via /translate skill)
```

### Service (mirrors `project-export.service.ts`)

```ts
export class ProjectImportService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }
  validateCsv(workspaceSlug, projectId, file: File) {
    /* multipart POST …/import-csv/validate/ */
  }
  importCsv(workspaceSlug, projectId, payload) {
    /* multipart POST …/import-csv/ */
  }
  getImports(workspaceSlug, projectId) {
    /* GET …/import-csv/ */
  }
  downloadTemplate(workspaceSlug, projectId) {
    /* GET …/import-csv/template/ */
  }
}
```

### Settings page wiring

- Copy the `exports/` route (`page.tsx` + `header.tsx`) to `imports/`: permission gate via
  `useUserPermissions().allowPermissions([ADMIN, MEMBER], WORKSPACE)`, `SettingsContentWrapper`,
  `SettingsHeading`, and render `<ImportGuide />`.
- Register the tab: add an `imports` entry to `WORKSPACE_SETTINGS` and `GROUPED_WORKSPACE_SETTINGS`
  (`packages/constants/src/settings/workspace.ts`), add it to the `TWorkspaceSettingsTabs` type, and
  give it an icon in `WORKSPACE_SETTINGS_ICONS`.
- Reuse `ImportExportSettingsLoader`
  (`core/components/ui/loader/settings/import-and-export.tsx`) for loading state.

### i18n

Add an `workspace_settings.settings.imports.*` block (heading, description, modal title, toasts,
row-error strings) and an `importer.csv.*` title/description, mirroring the export keys. **All locale
JSON changes go through the `/translate` skill** per repo convention.

---

## Testing plan

### Backend (pytest + pytest-django — conventions in `apps/api/pytest.ini`, `tests/conftest.py`)

**Unit tests** — `apps/api/plane/tests/unit/utils/test_csv_issue_importer.py`
(pattern: `@pytest.mark.unit`, pure, no DB, like `test_csv_export_sanitization.py`):

- Header normalization; unknown/missing columns.
- Priority coercion & invalid priority rejected.
- Multi-value split on `;` for assignees/labels/modules.
- Date parsing + start ≤ target rule; point range 0–12.
- Parent `PROJ-123` parsing.
- Description HTML sanitization (formula-injection parity with the export sanitizer).
- Row error objects have `{row, field, message}` shape.

**Contract tests** — `apps/api/plane/tests/contract/app/test_issue_import_app.py`
(pattern: `@pytest.mark.contract` + `@pytest.mark.django_db`, `session_client` + `workspace`
fixtures, `get_url()` helper, assert status + DB side effects):

- `GET …/template/` returns 200 with expected header row.
- `validate/`: happy path returns correct valid/invalid counts and writes **no** `Issue` rows.
- `validate/`: bad state name / non-member assignee / bad date / missing name → row errors.
- Commit happy path: creates N issues with correct `sequence_id` continuity, assignees, labels,
  `ModuleIssue` + `CycleIssue` rows.
- Commit with `partial=True`: valid rows created, invalid skipped, error report returned.
- `external_id` de-dupe: re-upload does not duplicate.
- Side effects: `mock.patch(... issue_activity)` / `mock.patch(... model_activity)` asserted called
  (use `@pytest.mark.django_db(transaction=True)` if the task fires on commit, matching the
  project-create test precedent).
- Permission: non-member / viewer role → 403.
- Async path: large file creates an `Importer(service="csv")` row and enqueues the task
  (`mock.patch` the `.delay`).

Run locally (CI runs lint only for the API): `cd apps/api && python -m pytest plane/tests/unit
plane/tests/contract/app/test_issue_import_app.py`.

### Frontend

`apps/web` has **no test framework today** (confirmed: no jest/vitest/testing-library, no `test`
script). **Decision: introduce full test infra in this PR.**

**Infra setup (net-new):**

- Add `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`
  to `apps/web` devDependencies (use the pnpm `catalog:` versions where present, following
  `apps/live`).
- Add `apps/web/vitest.config.ts` with `environment: "jsdom"`, `globals: true`, a `setup` file for
  `@testing-library/jest-dom` matchers, and the `@/` path alias mirroring the app's tsconfig paths.
- Add a `"test": "vitest run"` (+ `"test:watch"`) script to `apps/web/package.json`; `turbo run test`
  already fans out to it (`turbo.json` has the `test` task). No CI job runs it today (CI is
  lint/build only) — document running it locally.

**1. Logic tests (pure, node-friendly):** parsing/validation/mapping helpers —
header mapping, `;`-split (assignees/labels/modules), priority/date coercion, `PROJ-N` parse,
error aggregation `{row, field, message}`, and building the `TIssue`-shaped payload from a resolved
row.

**2. Component tests (jsdom + testing-library):** `import-csv-modal`, `upload-step`, `preview-step` —
dropzone rejects non-CSV / oversized files, preview renders the error banner from a mocked
`validateCsv`, the Import button stays disabled until both a file and a target project are chosen,
and a success toast fires on import (mock `ProjectImportService`).

---

## Implementation phases

- **Phase 0 — decisions:** ✅ DONE — all 7 decisions confirmed (see Decisions section above).
- **Phase 1 — backend parser + template:** ✅ DONE —
  `apps/api/plane/utils/importers/template.py` (canonical column spec + template CSV),
  `apps/api/plane/utils/importers/csv_issue_importer.py` (pure parse/resolve/validate, Django-free),
  and `apps/api/plane/tests/unit/utils/test_csv_issue_importer.py` (34 unit cases, `@pytest.mark.unit`).
  Logic verified via a standalone runner mirroring the pytest cases (local env lacks backend deps;
  pytest runs in Docker/CI). No API yet.
- **Phase 2 — backend endpoints:** ✅ DONE —
  `IssueImport` model (`db/models/importer.py`) + migration `0122_issueimport.py`;
  `IssueImportSerializer`; `plane/utils/importers/context.py` (ORM adapter building the
  `ResolutionContext`); `plane/app/views/issue/import_csv.py` with `IssueCSVTemplateEndpoint`,
  `IssueCSVImportValidateEndpoint`, `IssueCSVImportEndpoint` (commit + history); URL + view wiring;
  side-effect parity (`issue_activity` + `model_activity`); admin label auto-create; external_id
  de-dupe; module/cycle membership. Contract tests in
  `tests/contract/app/test_issue_import_app.py` (template, validate, commit, partial/skip-invalid,
  dedupe, missing-name, label auto-create, non-member 403, module/cycle, history). Commit path is
  synchronous for all sizes in Phase 2; the `SYNC_ROW_THRESHOLD` branch to Celery is Phase 3.
- **Phase 3 — async path:** ✅ DONE —
  extracted the request-free creation engine into `plane/utils/importers/runner.py` (shared by the
  sync view and the task); `plane/bgtasks/issue_import_task.py` Celery task
  (queued→processing→completed/failed, updates counters + error_report); the view now branches on
  `preview.total > SYNC_ROW_THRESHOLD` (200) — small imports run inline (201), large ones dispatch
  the task and return **202 queued** for the client to poll the history endpoint. Added async
  contract tests (dispatch + task execution). Full suite: **43 passed** in Docker (Postgres+Django).
- **Phase 4 — frontend service + modal wizard:** ✅ DONE —
  `ProjectImportService` (`services/project/project-import.service.ts`: validateCsv / importCsv /
  getImports / getTemplateUrl); `components/importer/` wizard (`upload-step`, `preview-step`,
  `import-csv-modal` upload→preview→confirm with skip-invalid gating + toasts + template download).
- **Phase 5 — frontend settings page:** ✅ DONE —
  `settings/(workspace)/imports/` page (`page.tsx` + `header.tsx`) mirroring exports. **The route must
  be registered explicitly** in `apps/web/app/routes/core.ts` (react-router `RouteConfig`, not
  filesystem-auto) — `route(":workspaceSlug/settings/imports", ".../(workspace)/imports/page.tsx")`
  next to the exports entry; without it the page 404s even though the file typechecks. New `import`
  tab registered in `TWorkspaceSettingsTabs` (packages/types), `WORKSPACE_SETTINGS` +
  `GROUPED_WORKSPACE_SETTINGS` (packages/constants), and `WORKSPACE_SETTINGS_ICONS`
  (`ArrowDownToLine`); `ImportGuide` card opens the modal. **Second entry point:** an "Import"
  button in the project work-items header (`apps/web/ce/components/issues/header.tsx`, gated by
  create permission) opens the modal with `projectId` set — a new optional `ImportCSVModal` prop
  that pre-selects and hides the project selector (locked to the current project). i18n keys under
  `workspace_settings.settings.imports.*` translated into **all 19 locales** via `/translate`
  (merged into the pre-existing `imports` stub; placeholder/CSV-token integrity verified;
  `sync:check` shows zero drift on the imports keys; `generate:types` regenerated).
  History list deferred: the backend history endpoint is per-project; a workspace-wide list would
  need a new endpoint (documented follow-up).
- **Phase 6 — frontend tests + infra:** ✅ DONE —
  added vitest + jsdom + @testing-library to `apps/web` (catalog entries, `vitest.config.ts` with
  `@plane/*` + `next/navigation` → local test-stubs aliases, `vitest.setup.ts`, `test` script).
  **18 tests passing**: service (URL/FormData/skip_invalid/error unwrap); preview-step (error list,
  skip toggle, all-valid); upload-step (template link, drop prompt, file name, error, gated link);
  **import-csv-modal integration** (validate→preview→import flow, invalid-row gating, skip_invalid
  passthrough, async queued toast).

### Final test coverage — 80 total (all green, run for real)

- **Backend: 50** (28 parser unit + 22 endpoint contract) via Docker (Postgres+Django): template,
  rules (disabled note + **enabled enumeration of cycles/modules/estimate/type** + 403), validate,
  commit/dedupe/partial/async/history, file-size guard (413/400), non-admin member label denial,
  parent+assignee+date persistence, start>target, 403, module-cycle, admin-label-autocreate.
- **Frontend: 30** via vitest+jsdom (5 files): service, upload-step (dropzone + tabs/paste),
  preview-step, import-csv-modal (upload/paste flows, gating, skip_invalid, async toast, copy
  rules/template, **copy-failed toast**, download rules, locked project), and the extracted
  **ImportWorkItemsButton** (opens the locked modal). The header just renders that component, so its
  button behavior is now covered without mocking the whole header.
- **Regression:** full `pytest plane/tests/contract plane/tests/unit` → 507 pass (only the 8
  pre-existing magic-link 429 auth-flakiness fail, unrelated); full web `tsc --noEmit` green; i18n
  `sync:check` zero drift on imports keys.
- **Notable finding from testing:** oversized uploads are rejected at the Django layer
  (`DATA_UPLOAD_MAX_MEMORY_SIZE` = `FILE_SIZE_LIMIT`, 5MB) with **413** before reaching the view —
  the view's `MAX_FILE_SIZE` is a secondary guard. All three limits (Caddy, Django, view) align at 5MB.

---

## Add-on: AI-assisted CSV authoring (built)

A per-project **import rules document** generated live so an LLM can author a CSV that imports
cleanly. `GET .../issues/import-csv/rules/` → `{markdown}` built by
`plane/utils/importers/rules.py` (`build_import_rules_markdown`) — reuses the same project queries
as the resolver: for each column it states required/optional + format, and enumerates the project's
**live allowed values** (state names, member emails, label names, cycle/module names, estimate
values, work-item-type names), flagging feature-disabled columns. The import modal's upload step
exposes four actions once a project is selected: **Download template**, **Copy template**
(`getTemplateCsv`), **Copy rules for AI** (clipboard) and **Download rules** (.md blob) — the latter
two call `getImportRules`. i18n keys (`copy_template`, `copy_rules`, `download_rules`, toast
`copied`/`copy_failed`) translated into all 19 locales. Verified: backend 49 pytest, frontend 22
vitest, web tsc clean.

## Decisions (confirmed)

1. **Label auto-create — DECIDED: auto-create for admins only.** If a CSV references a label that
   doesn't exist, the importer creates it **only when the user is a project ADMIN** (the same rule
   the create modal and `LabelViewSet`/`BulkCreateIssueLabelsEndpoint` already enforce via
   `@allow_permission([ROLE.ADMIN])`). For non-admins, an unknown label flags the row as an error.
   Keeps import consistent with the rest of the system's permissions.
2. **Data model — DECIDED: new `IssueImport` model** (not extending the legacy `Importer` stub).
   Rationale: `Importer` is modeled for OAuth integrations (required `token` FK with CASCADE,
   `service` = github/jira, `config` = OAuth), is a dead stub owned by the EE/silo service, and
   reusing it would mean weakening its `token` invariant and risking EE migration collisions.
   `IssueImport` gives typed/indexable counters, `SET_NULL` audit safety, and full isolation.
   ```python
   class IssueImport(ProjectBaseModel):   # inherits id, project, workspace, created_by/at, deleted_at
       file_name    = models.CharField(max_length=255)
       status       = models.CharField(choices=QUEUED/PROCESSING/COMPLETED/FAILED, default="queued")
       initiated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issue_imports")
       total_rows   = models.PositiveIntegerField(default=0)
       created_rows = models.PositiveIntegerField(default=0)
       failed_rows  = models.PositiveIntegerField(default=0)
       error_report = models.JSONField(default=list)   # [{row, field, message}]
       external_source = models.CharField(default="csv", max_length=50)
   ```

## Open questions / decisions to confirm

3. **Sync/async threshold — DECIDED: 200 rows** (≤200 sync, >200 async via Celery). Grounded in the
   real env: gunicorn runs `UvicornWorker` with **no explicit `--timeout`** → default **30s**
   (`apps/api/bin/docker-entrypoint-api.sh:38`); Caddy sets no reverse-proxy read/write timeout
   (`apps/proxy/Caddyfile.ce`). Per-row cost is non-trivial and **serialized** by the per-project
   `pg_advisory_xact_lock` in `Issue.save()` (sequence assignment), ~30–80ms/row, so ~200 rows
   ≈ 6–16s — comfortable margin under the 30s worker timeout. Revisit upward only if `--timeout`
   is raised; downward if issues carry many assignees/labels (more inserts per row).
4. **Max rows / file size cap — DECIDED: 5,000 rows / 5 MB.** Excess rejected with a clear 400
   ("CSV exceeds 5000 rows / 5MB"). The 5 MB cap must stay **below the Caddy `FILE_SIZE_LIMIT`**
   (`apps/proxy/Caddyfile.ce` → `request_body max_size {$FILE_SIZE_LIMIT}`); verify that env value
   in the target deployment.
5. **EE additional properties — DECIDED: defer to v2 with an extensible resolver.** v1 covers all
   standard modal fields (including the `Work Item Type` name column). The resolver map is built so
   custom-property columns can be added later without reshaping the pipeline. No per-property EE
   type validation in v1.
6. **Assignee key — DECIDED: email only.** Assignees resolved by email against active project
   members (role ≥ 15); non-member/unknown email → row error. Display name is rejected as ambiguous
   (duplicate full names). Note: export renders `full_name`, so re-importing an exported file needs
   an email column — documented in the template.
7. **Web test infra — DECIDED: full infra now.** Add `vitest + jsdom + @testing-library/react` to
   `apps/web` in this PR and test both the pure logic (parsing/validation/mapping) **and** the modal
   components (dropzone, preview/error banner, gated Import button, success toast). Wire a `test`
   script so `turbo run test` picks it up (`turbo.json` already has the `test` task).
