/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useState } from "react";
import { Copy, Download, FileDown, Sparkles } from "lucide-react";
import { useDropzone } from "react-dropzone";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { CustomSearchSelect } from "@plane/ui";

export const MAX_CSV_SIZE = 5 * 1024 * 1024; // 5 MB — mirrors the backend cap

const tabClass = (active: boolean) =>
  `border-b-2 px-1 pb-1.5 text-13 transition-colors ${
    active ? "border-accent-strong text-primary" : "border-transparent text-secondary hover:text-primary"
  }`;

type TInputMode = "upload" | "paste";

type TProjectOption = {
  value: string | undefined;
  query: string;
  content: React.ReactNode;
};

type Props = {
  projectOptions: TProjectOption[];
  selectedProjectId: string | null;
  onSelectProject: (projectId: string) => void;
  onFileSelected: (file: File) => void;
  fileName: string | null;
  fileError: string | null;
  templateUrl: string | null;
  onCopyTemplate?: () => void;
  onCopyRules?: () => void;
  onDownloadRules?: () => void;
  disabled?: boolean;
  // When the modal is opened from a specific project, the target is fixed and the selector is hidden.
  hideProjectSelect?: boolean;
};

export const ImportUploadStep = function ImportUploadStep(props: Props) {
  const {
    projectOptions,
    selectedProjectId,
    onSelectProject,
    onFileSelected,
    fileName,
    fileError,
    templateUrl,
    onCopyTemplate,
    onCopyRules,
    onDownloadRules,
    disabled = false,
    hideProjectSelect = false,
  } = props;
  const { t } = useTranslation();
  const [mode, setMode] = useState<TInputMode>("upload");
  const [pasteText, setPasteText] = useState("");

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (file) onFileSelected(file);
    },
    [onFileSelected]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxSize: MAX_CSV_SIZE,
    multiple: false,
    accept: { "text/csv": [".csv"], "application/vnd.ms-excel": [".csv"] },
    disabled: disabled || !selectedProjectId,
  });

  const selectedOption = projectOptions.find((option) => option.value === selectedProjectId);
  const selectedLabel = selectedOption ? selectedOption.query : t("workspace_settings.settings.imports.select_project");

  // Pasted content is turned into a CSV File so it flows through the same validate path.
  const submitPaste = () => {
    const text = pasteText.trim();
    if (!text) return;
    onFileSelected(new File([text], "pasted.csv", { type: "text/csv" }));
  };

  return (
    <div className="flex flex-col gap-4">
      {!hideProjectSelect && (
        <CustomSearchSelect
          value={selectedProjectId ?? ""}
          onChange={(value: string) => onSelectProject(value)}
          options={projectOptions}
          input
          label={selectedLabel}
          optionsClassName="max-w-48 sm:max-w-[532px]"
          placement="bottom-start"
        />
      )}

      <div className="flex items-center gap-4 border-b border-subtle">
        <button type="button" className={tabClass(mode === "upload")} onClick={() => setMode("upload")}>
          {t("workspace_settings.settings.imports.tab_upload")}
        </button>
        <button type="button" className={tabClass(mode === "paste")} onClick={() => setMode("paste")}>
          {t("workspace_settings.settings.imports.tab_paste")}
        </button>
      </div>

      {mode === "upload" ? (
        <div
          {...getRootProps()}
          aria-label="csv-dropzone"
          className={`flex h-[96px] flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed px-4 text-13 ${
            isDragActive ? "border-accent-strong bg-accent-primary/10" : "border-subtle bg-accent-primary/5"
          } ${!selectedProjectId || disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer text-accent-primary"}`}
        >
          <input {...getInputProps()} />
          {isDragActive ? (
            <p>{t("workspace_settings.settings.imports.drop_active")}</p>
          ) : fileName ? (
            <p className="font-medium">{fileName}</p>
          ) : (
            <p>{t("workspace_settings.settings.imports.drop_csv")}</p>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-end gap-2">
          <textarea
            aria-label="csv-paste"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={t("workspace_settings.settings.imports.paste_placeholder")}
            disabled={disabled || !selectedProjectId}
            className="font-mono h-40 w-full resize-y rounded-md border border-subtle bg-transparent p-3 text-12 outline-none focus:border-accent-strong disabled:cursor-not-allowed disabled:opacity-60"
          />
          <Button
            variant="primary"
            onClick={submitPaste}
            disabled={disabled || !selectedProjectId || !pasteText.trim()}
          >
            {t("workspace_settings.settings.imports.paste_validate")}
          </Button>
        </div>
      )}

      {fileError && <p className="text-11 text-danger-primary">{fileError}</p>}

      {templateUrl && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-11 text-accent-primary">
          <a href={templateUrl} className="flex items-center gap-1 hover:underline" download>
            <Download className="size-3.5" />
            {t("workspace_settings.settings.imports.download_template")}
          </a>
          <button type="button" onClick={onCopyTemplate} className="flex items-center gap-1 hover:underline">
            <Copy className="size-3.5" />
            {t("workspace_settings.settings.imports.copy_template")}
          </button>
          <button type="button" onClick={onDownloadRules} className="flex items-center gap-1 hover:underline">
            <FileDown className="size-3.5" />
            {t("workspace_settings.settings.imports.download_rules")}
          </button>
          <button type="button" onClick={onCopyRules} className="flex items-center gap-1 hover:underline">
            <Sparkles className="size-3.5" />
            {t("workspace_settings.settings.imports.copy_rules")}
          </button>
        </div>
      )}
    </div>
  );
};
