/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";

// Test stub for @plane/propel/button (the real package ships as a built artifact).
export const Button = ({
  children,
  onClick,
  disabled,
  loading,
  variant: _variant,
  ...rest
}: {
  children?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: string;
}) => (
  <button type="button" onClick={onClick} disabled={!!disabled} {...rest}>
    {children}
  </button>
);
