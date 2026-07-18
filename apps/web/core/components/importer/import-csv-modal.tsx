/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { intersection } from "lodash-es";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUser } from "@/hooks/store/user";
// services
import { ProjectImportService } from "@/services/project";
import type { TCsvImportValidation } from "@/services/project";
// local imports
import { ImportPreviewStep } from "./preview-step";
import { ImportUploadStep, MAX_CSV_SIZE } from "./upload-step";

type Props = {
  isOpen: boolean;
  handleClose: () => void;
  onImported?: () => void;
  // When set (e.g. opened from a project's work-items list), the import is locked
  // to this project and the in-modal project selector is hidden.
  projectId?: string;
};

const projectImportService = new ProjectImportService();

export const ImportCSVModal = observer(function ImportCSVModal(props: Props) {
  const { isOpen, handleClose, onImported, projectId } = props;
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const { workspaceProjectIds, getProjectById } = useProject();
  const { projectsWithCreatePermissions } = useUser();
  const { t } = useTranslation();
  // state
  const [step, setStep] = useState<"upload" | "preview">("upload");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(projectId ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [validation, setValidation] = useState<TCsvImportValidation | null>(null);
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const slug = workspaceSlug?.toString();

  const projectOptions = useMemo(() => {
    const allowedProjectIds = projectsWithCreatePermissions
      ? intersection(workspaceProjectIds, Object.keys(projectsWithCreatePermissions))
      : [];
    return allowedProjectIds.map((id) => {
      const projectDetails = getProjectById(id);
      return {
        value: projectDetails?.id,
        query: `${projectDetails?.name} ${projectDetails?.identifier}`,
        content: (
          <div className="flex items-center gap-2">
            <span className="flex-shrink-0 text-10 text-secondary">{projectDetails?.identifier}</span>
            <span className="truncate">{projectDetails?.name}</span>
          </div>
        ),
      };
    });
  }, [projectsWithCreatePermissions, workspaceProjectIds, getProjectById]);

  const resetState = () => {
    setStep("upload");
    setSelectedProjectId(projectId ?? null);
    setFile(null);
    setFileError(null);
    setValidation(null);
    setSkipInvalid(false);
    setIsValidating(false);
    setIsImporting(false);
  };

  const onClose = () => {
    resetState();
    handleClose();
  };

  const handleFileSelected = async (selected: File) => {
    setFileError(null);
    if (selected.size > MAX_CSV_SIZE) {
      setFileError(t("workspace_settings.settings.imports.invalid_file", { size: MAX_CSV_SIZE / 1024 / 1024 }));
      return;
    }
    if (!slug || !selectedProjectId) return;
    setFile(selected);
    setIsValidating(true);
    try {
      const result = await projectImportService.validateCsv(slug, selectedProjectId, selected);
      setValidation(result);
      setStep("preview");
    } catch {
      setFileError(t("workspace_settings.settings.imports.toasts.error.message"));
    } finally {
      setIsValidating(false);
    }
  };

  const handleImport = async () => {
    if (!slug || !selectedProjectId || !file) return;
    setIsImporting(true);
    try {
      const result = await projectImportService.importCsv(slug, selectedProjectId, file, skipInvalid);
      if (result.async) {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: t("workspace_settings.settings.imports.toasts.queued.title"),
          message: t("workspace_settings.settings.imports.toasts.queued.message"),
        });
      } else {
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: t("workspace_settings.settings.imports.toasts.success.title"),
          message: t("workspace_settings.settings.imports.toasts.success.message", { count: result.created ?? 0 }),
        });
      }
      onImported?.();
      onClose();
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("workspace_settings.settings.imports.toasts.error.title"),
        message: t("workspace_settings.settings.imports.toasts.error.message"),
      });
      setIsImporting(false);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("workspace_settings.settings.imports.toasts.copied.title") });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("workspace_settings.settings.imports.toasts.copy_failed.title"),
        message: t("workspace_settings.settings.imports.toasts.copy_failed.message"),
      });
    }
  };

  const failToast = () =>
    setToast({ type: TOAST_TYPE.ERROR, title: t("workspace_settings.settings.imports.toasts.error.title") });

  const handleCopyTemplate = async () => {
    if (!slug || !selectedProjectId) return;
    try {
      await copyToClipboard(await projectImportService.getTemplateCsv(slug, selectedProjectId));
    } catch {
      failToast();
    }
  };

  const handleCopyRules = async () => {
    if (!slug || !selectedProjectId) return;
    try {
      await copyToClipboard(await projectImportService.getImportRules(slug, selectedProjectId));
    } catch {
      failToast();
    }
  };

  const handleDownloadRules = async () => {
    if (!slug || !selectedProjectId) return;
    try {
      const markdown = await projectImportService.getImportRules(slug, selectedProjectId);
      const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "import-rules.md";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      failToast();
    }
  };

  // Import is blocked when there are no valid rows, or invalid rows exist and the
  // user hasn't opted into a partial import.
  const importDisabled =
    !validation || validation.valid === 0 || (validation.invalid > 0 && !skipInvalid) || isImporting;

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      <div className="flex flex-col gap-6 gap-y-4 p-6">
        <h3 className="text-18 font-medium 2xl:text-20">{t("workspace_settings.settings.imports.import_button")}</h3>

        {step === "upload" ? (
          <ImportUploadStep
            projectOptions={projectOptions}
            selectedProjectId={selectedProjectId}
            onSelectProject={(id) => {
              setSelectedProjectId(id);
              setFile(null);
              setFileError(null);
              setValidation(null);
            }}
            onFileSelected={handleFileSelected}
            fileName={file?.name ?? null}
            fileError={fileError}
            templateUrl={
              slug && selectedProjectId ? projectImportService.getTemplateUrl(slug, selectedProjectId) : null
            }
            onCopyTemplate={handleCopyTemplate}
            onCopyRules={handleCopyRules}
            onDownloadRules={handleDownloadRules}
            disabled={isValidating}
            hideProjectSelect={!!projectId}
          />
        ) : (
          validation && (
            <ImportPreviewStep validation={validation} skipInvalid={skipInvalid} onToggleSkip={setSkipInvalid} />
          )
        )}

        <div className="flex justify-end gap-2">
          {step === "preview" && (
            <Button variant="secondary" onClick={() => setStep("upload")} disabled={isImporting}>
              {t("workspace_settings.settings.imports.back")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose} disabled={isImporting}>
            {t("cancel")}
          </Button>
          {step === "preview" && (
            <Button variant="primary" onClick={handleImport} disabled={importDisabled} loading={isImporting}>
              {isImporting
                ? `${t("workspace_settings.settings.imports.importing")}...`
                : t("workspace_settings.settings.imports.import_button")}
            </Button>
          )}
        </div>
      </div>
    </ModalCore>
  );
});
