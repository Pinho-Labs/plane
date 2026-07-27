/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Test stub for @plane/propel/toast (the real package ships as a built artifact).
// Records calls so tests can assert which toast fired.
export const TOAST_TYPE = {
  SUCCESS: "success",
  ERROR: "error",
  WARNING: "warning",
  INFO: "info",
} as const;

export const toastCalls: { type: string; title?: string; message?: string }[] = [];

export const setToast = (payload: { type: string; title?: string; message?: string }) => {
  toastCalls.push(payload);
};
