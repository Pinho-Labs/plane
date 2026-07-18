/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { AlertTriangle, CheckCircle2 } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Checkbox } from "@plane/ui";
// services
import type { TCsvImportValidation } from "@/services/project";

type Props = {
  validation: TCsvImportValidation;
  skipInvalid: boolean;
  onToggleSkip: (value: boolean) => void;
};

export const ImportPreviewStep = function ImportPreviewStep(props: Props) {
  const { validation, skipInvalid, onToggleSkip } = props;
  const { t } = useTranslation();

  const hasErrors = validation.invalid > 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4 text-13">
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

      {hasErrors && (
        <div className="max-h-48 overflow-y-auto rounded-md border border-danger-subtle bg-danger-subtle/40">
          <ul className="divide-y divide-danger-subtle text-11">
            {validation.errors.map((error) => (
              <li key={`${error.row}-${error.field}-${error.message}`} className="flex gap-2 px-3 py-1.5">
                <span className="flex-shrink-0 font-medium text-danger-primary">
                  {t("workspace_settings.settings.imports.row_label", { row: error.row })}
                </span>
                <span className="text-secondary">{error.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

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
