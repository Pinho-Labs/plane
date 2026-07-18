/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";

// Test stub for @plane/ui (the real package ships as a built artifact). Only the
// exports used by the importer components are provided, as lightweight elements.

export const Checkbox = (props: { checked?: boolean; onChange?: () => void }) => (
  <input type="checkbox" checked={!!props.checked} onChange={props.onChange} readOnly />
);

export const CustomSearchSelect = (props: {
  label?: React.ReactNode;
  options?: { value?: string; content?: React.ReactNode }[];
  onChange?: (value: string) => void;
}) => (
  <div data-testid="project-select">
    <span>{props.label}</span>
    {(props.options ?? []).map((o) => (
      <button
        key={o.value}
        type="button"
        data-testid={`project-option-${o.value}`}
        onClick={() => props.onChange?.(o.value as string)}
      >
        {o.content}
      </button>
    ))}
  </div>
);

export enum EModalPosition {
  CENTER = "center",
  TOP = "top",
}

export enum EModalWidth {
  XL = "xl",
}

export const ModalCore = ({ children, isOpen }: { children: React.ReactNode; isOpen: boolean }) =>
  isOpen ? <div data-testid="modal-core">{children}</div> : null;
