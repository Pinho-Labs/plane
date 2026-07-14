/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Pinho Labs (fork): bulk edit unlocked, at field parity with the EE toolbar
 * (TBulkIssueProperties): state, priority, assignees, labels, start date,
 * target date, estimate, cycle and modules.
 *
 * Upstream ships a paywall stub here (the real toolbar lives in the closed ee/).
 * We apply changes through the same paths as the single-issue editor:
 *  - 7 direct fields -> updateIssue({...}) per selected issue (keeps activity
 *    log, notifications and webhooks working);
 *  - cycle -> addIssueToCycle(...issueIds[]) (the store's native bulk method);
 *  - modules -> changeModulesInIssue(...) per issue.
 * The backend stays vanilla (the ee/ bulk-operation-issues/ endpoint is absent).
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { X } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssue, TIssuePriorities } from "@plane/types";
import { cn, renderFormattedPayloadDate } from "@plane/utils";
// dropdowns
import { CycleDropdown } from "@/components/dropdowns/cycle";
import { DateDropdown } from "@/components/dropdowns/date";
import { EstimateDropdown } from "@/components/dropdowns/estimate";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { ModuleDropdown } from "@/components/dropdowns/module/dropdown";
import { PriorityDropdown } from "@/components/dropdowns/priority";
import { StateDropdown } from "@/components/dropdowns/state/dropdown";
// components
import { IssuePropertyLabels } from "@/components/issues/issue-layouts/properties/labels";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useMultipleSelectStore } from "@/hooks/store/use-multiple-select-store";
import type { TSelectionHelper } from "@/hooks/use-multiple-select";

type Props = {
  className?: string;
  selectionHelpers: TSelectionHelper;
};

export const IssueBulkOperationsRoot = observer(function IssueBulkOperationsRoot(props: Props) {
  const { className, selectionHelpers } = props;
  // router
  const { workspaceSlug: wsParam, projectId: projParam } = useParams();
  // store hooks
  const { isSelectionActive, selectedEntityIds } = useMultipleSelectStore();
  const { updateIssue, addIssueToCycle, changeModulesInIssue } = useIssueDetail();
  // i18n
  const { t } = useTranslation();
  // local state
  const [isUpdating, setIsUpdating] = useState(false);

  if (!isSelectionActive || selectionHelpers.isSelectionDisabled) return null;

  const workspaceSlug = wsParam?.toString();
  const projectId = projParam?.toString();
  const ids = selectedEntityIds;
  const count = ids.length;
  const canEdit = !!workspaceSlug && !!projectId && count > 0;

  // executor: runs the action, toasts the outcome and locks the toolbar while it works
  const run = async (fn: () => Promise<unknown>) => {
    if (!canEdit || isUpdating) return;
    setIsUpdating(true);
    try {
      await fn();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("bulk_operations.update_success.title"),
        message: t("bulk_operations.update_success.message", { count }),
      });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("bulk_operations.update_error.title"),
        message: t("bulk_operations.update_error.message"),
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // direct issue fields -> partial update on every selected issue
  const applyUpdate = (data: Partial<TIssue>) =>
    run(() => Promise.all(ids.map((id) => updateIssue(workspaceSlug!, projectId!, id, data))));
  // cycle (relation) -> the store exposes a bulk method that takes the issueIds list
  const applyCycle = (cycleId: string | null) => {
    if (cycleId) run(() => addIssueToCycle(workspaceSlug!, projectId!, cycleId, ids));
  };
  // modules (relation) -> add the chosen modules to each selected issue
  const applyModules = (moduleIds: string[]) =>
    run(() => Promise.all(ids.map((id) => changeModulesInIssue(workspaceSlug!, projectId!, id, moduleIds, []))));

  return (
    <div className={cn("sticky bottom-0 left-0 z-[2] grid h-20 place-items-center px-3.5", className)}>
      <div
        className={cn(
          "flex h-14 w-full items-center gap-2 rounded-md border-[0.5px] border-custom-border-300 bg-custom-background-100 px-3.5 py-4 shadow-custom-shadow-sm",
          { "pointer-events-none opacity-60": isUpdating }
        )}
      >
        <span className="whitespace-nowrap text-sm font-medium text-custom-text-200">
          {t("bulk_operations.selected_count", { count })}
        </span>
        <div className="mx-1 h-6 w-px flex-shrink-0 bg-custom-border-200" />

        {projectId && (
          <div className="flex items-center gap-2 overflow-x-auto">
            <StateDropdown
              projectId={projectId}
              value={null}
              onChange={(val: string) => applyUpdate({ state_id: val })}
              buttonVariant="border-with-text"
            />
            <PriorityDropdown
              value={null}
              onChange={(val: TIssuePriorities) => applyUpdate({ priority: val })}
              buttonVariant="border-with-text"
            />
            <MemberDropdown
              projectId={projectId}
              value={[]}
              onChange={(val: string[]) => applyUpdate({ assignee_ids: val })}
              multiple
              buttonVariant="border-with-text"
              placeholder={t("common.assignees")}
            />
            <IssuePropertyLabels
              projectId={projectId}
              value={[]}
              onChange={(val: string[]) => applyUpdate({ label_ids: val })}
              placeholderText={t("common.labels")}
              renderByDefault
            />
            <DateDropdown
              value={null}
              onChange={(val: Date | null) => applyUpdate({ start_date: val ? renderFormattedPayloadDate(val) : null })}
              buttonVariant="border-with-text"
              placeholder={t("common.order_by.start_date")}
            />
            <DateDropdown
              value={null}
              onChange={(val: Date | null) => applyUpdate({ target_date: val ? renderFormattedPayloadDate(val) : null })}
              buttonVariant="border-with-text"
              placeholder={t("common.order_by.due_date")}
            />
            <EstimateDropdown
              projectId={projectId}
              value={undefined}
              onChange={(val: string | undefined) => applyUpdate({ estimate_point: val })}
              buttonVariant="border-with-text"
              placeholder={t("common.estimate")}
            />
            <CycleDropdown
              projectId={projectId}
              value={null}
              onChange={(val: string | null) => applyCycle(val)}
              buttonVariant="border-with-text"
              placeholder={t("common.cycle")}
            />
            <ModuleDropdown
              projectId={projectId}
              value={[]}
              onChange={(val: string[]) => applyModules(val)}
              multiple
              buttonVariant="border-with-text"
              placeholder={t("common.modules")}
            />
          </div>
        )}

        <div className="flex-grow" />
        <button
          type="button"
          onClick={selectionHelpers.handleClearSelection}
          className="flex-shrink-0 rounded p-1 text-custom-text-300 hover:bg-custom-background-80 hover:text-custom-text-100"
          title={t("bulk_operations.clear_selection")}
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
});
