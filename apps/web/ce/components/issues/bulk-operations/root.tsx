/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Pinho Labs (fork): bulk edit destravado, com PARIDADE de campos com a EE
 * (TBulkIssueProperties): estado, prioridade, responsáveis, labels, data de
 * início, data de entrega, estimativa, ciclo e módulos.
 *
 * O upstream mostra um paywall aqui (a toolbar real vive no ee/ fechado). Aqui a
 * gente aplica via os mesmos caminhos do editor single-issue:
 *  - 7 campos diretos → updateIssue({...}) em loop (mantém activity/notif/webhook);
 *  - ciclo → addIssueToCycle(...issueIds[]) (bulk nativo do store);
 *  - módulos → changeModulesInIssue(...) por issue.
 * O backend fica vanilla (o endpoint bulk-operation-issues/ é do ee/, ausente).
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { X } from "lucide-react";
// plane imports
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
  // local state
  const [isUpdating, setIsUpdating] = useState(false);

  if (!isSelectionActive || selectionHelpers.isSelectionDisabled) return null;

  const workspaceSlug = wsParam?.toString();
  const projectId = projParam?.toString();
  const ids = selectedEntityIds;
  const count = ids.length;
  const canEdit = !!workspaceSlug && !!projectId && count > 0;

  // executor: roda a ação, mostra toast e trava a toolbar enquanto processa
  const run = async (fn: () => Promise<unknown>) => {
    if (!canEdit || isUpdating) return;
    setIsUpdating(true);
    try {
      await fn();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Atualizado",
        message: `${count} work item(s) atualizados.`,
      });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Erro",
        message: "Não foi possível atualizar todos os work items.",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  // campos diretos do issue → partial_update em cada selecionada
  const applyUpdate = (data: Partial<TIssue>) =>
    run(() => Promise.all(ids.map((id) => updateIssue(workspaceSlug!, projectId!, id, data))));
  // ciclo (relação) → o store tem método bulk que aceita a lista de issueIds
  const applyCycle = (cycleId: string | null) => {
    if (cycleId) run(() => addIssueToCycle(workspaceSlug!, projectId!, cycleId, ids));
  };
  // módulos (relação) → adiciona os módulos escolhidos em cada issue
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
          {count} selecionado{count === 1 ? "" : "s"}
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
              placeholder="Responsáveis"
            />
            <IssuePropertyLabels
              projectId={projectId}
              value={[]}
              onChange={(val: string[]) => applyUpdate({ label_ids: val })}
              renderByDefault
            />
            <DateDropdown
              value={null}
              onChange={(val: Date | null) => applyUpdate({ start_date: val ? renderFormattedPayloadDate(val) : null })}
              buttonVariant="border-with-text"
              placeholder="Início"
            />
            <DateDropdown
              value={null}
              onChange={(val: Date | null) => applyUpdate({ target_date: val ? renderFormattedPayloadDate(val) : null })}
              buttonVariant="border-with-text"
              placeholder="Entrega"
            />
            <EstimateDropdown
              projectId={projectId}
              value={undefined}
              onChange={(val: string | undefined) => applyUpdate({ estimate_point: val })}
              buttonVariant="border-with-text"
            />
            <CycleDropdown
              projectId={projectId}
              value={null}
              onChange={(val: string | null) => applyCycle(val)}
              buttonVariant="border-with-text"
              placeholder="Ciclo"
            />
            <ModuleDropdown
              projectId={projectId}
              value={[]}
              onChange={(val: string[]) => applyModules(val)}
              multiple
              buttonVariant="border-with-text"
              placeholder="Módulos"
            />
          </div>
        )}

        <div className="flex-grow" />
        <button
          type="button"
          onClick={selectionHelpers.handleClearSelection}
          className="flex-shrink-0 rounded p-1 text-custom-text-300 hover:bg-custom-background-80 hover:text-custom-text-100"
          title="Limpar seleção"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
});
