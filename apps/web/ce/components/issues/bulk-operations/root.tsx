/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Pinho Labs (fork): bulk edit destravado. O upstream mostra um paywall aqui
 * (a toolbar real vive no ee/ fechado). Aqui a gente monta a toolbar e aplica o
 * update em massa chamando o partial_update (via useIssueDetail) em cada issue
 * selecionada — mantendo activity log, notificações e webhooks (o backend fica
 * vanilla). Cobre estado, prioridade e responsáveis; a seleção some depois.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { X } from "lucide-react";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssue, TIssuePriorities } from "@plane/types";
import { cn } from "@plane/utils";
// components
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { PriorityDropdown } from "@/components/dropdowns/priority";
import { StateDropdown } from "@/components/dropdowns/state/dropdown";
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
  const { workspaceSlug, projectId } = useParams();
  // store hooks
  const { isSelectionActive, selectedEntityIds } = useMultipleSelectStore();
  const { updateIssue } = useIssueDetail();
  // local state
  const [isUpdating, setIsUpdating] = useState(false);

  if (!isSelectionActive || selectionHelpers.isSelectionDisabled) return null;

  const count = selectedEntityIds.length;
  const canEdit = !!workspaceSlug && !!projectId && count > 0;

  // aplica o mesmo update em TODAS as issues selecionadas (loop no partial_update)
  const applyToAll = async (data: Partial<TIssue>) => {
    if (!canEdit || isUpdating) return;
    setIsUpdating(true);
    try {
      await Promise.all(
        selectedEntityIds.map((issueId) =>
          updateIssue(workspaceSlug!.toString(), projectId!.toString(), issueId, data)
        )
      );
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
          <div className="flex items-center gap-2">
            <StateDropdown
              projectId={projectId.toString()}
              value={null}
              onChange={(val: string) => applyToAll({ state_id: val })}
              buttonVariant="border-with-text"
            />
            <PriorityDropdown
              value={null}
              onChange={(val: TIssuePriorities) => applyToAll({ priority: val })}
              buttonVariant="border-with-text"
            />
            <MemberDropdown
              projectId={projectId.toString()}
              value={[]}
              onChange={(val: string[]) => applyToAll({ assignee_ids: val })}
              multiple
              buttonVariant="border-with-text"
              placeholder="Responsáveis"
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
