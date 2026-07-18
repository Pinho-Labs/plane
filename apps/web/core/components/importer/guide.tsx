/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Upload } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
// local imports
import { ImportCSVModal } from "./import-csv-modal";

export const ImportGuide = observer(function ImportGuide() {
  const { t } = useTranslation();
  const [isModalOpen, setIsModalOpen] = useState(false);

  return (
    <>
      <ImportCSVModal isOpen={isModalOpen} handleClose={() => setIsModalOpen(false)} />
      <div className="flex items-center justify-between rounded-md border border-subtle bg-layer-2 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="grid size-8 flex-shrink-0 place-items-center rounded-md bg-accent-primary/10 text-accent-primary">
            <Upload className="size-4" />
          </span>
          <div className="flex flex-col">
            <span className="text-13 font-medium">{t("workspace_settings.settings.imports.title")} · CSV</span>
            <span className="text-11 text-secondary">{t("workspace_settings.settings.imports.description")}</span>
          </div>
        </div>
        <Button variant="primary" onClick={() => setIsModalOpen(true)}>
          {t("workspace_settings.settings.imports.import_button")}
        </Button>
      </div>
    </>
  );
});
