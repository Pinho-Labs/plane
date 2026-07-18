/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
// local imports
import { ImportCSVModal } from "./import-csv-modal";

type Props = {
  projectId: string;
};

// Contextual "Import" action for a project's work-items list. Opens the import
// modal locked to that project. The caller is responsible for permission gating.
export const ImportWorkItemsButton = function ImportWorkItemsButton({ projectId }: Props) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <ImportCSVModal isOpen={isOpen} handleClose={() => setIsOpen(false)} projectId={projectId} />
      <Button variant="secondary" size="lg" onClick={() => setIsOpen(true)}>
        {t("workspace_settings.settings.imports.import_button")}
      </Button>
    </>
  );
};
