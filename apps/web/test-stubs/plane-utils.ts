/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Test stub for @plane/utils (the real package ships as a built artifact).
// Only the helpers used by the importer components are provided.

type ClassValue = string | number | null | false | undefined | ClassValue[] | Record<string, boolean | undefined | null>;

export const cn = (...inputs: ClassValue[]): string => {
  const out: string[] = [];
  const walk = (value: ClassValue) => {
    if (!value) return;
    if (typeof value === "string" || typeof value === "number") out.push(String(value));
    else if (Array.isArray(value)) value.forEach(walk);
    else if (typeof value === "object") for (const key in value) if (value[key]) out.push(key);
  };
  inputs.forEach(walk);
  return out.join(" ");
};

export const getFileURL = (path: string): string | undefined => path || undefined;

export const renderFormattedDate = (date: string | Date | null | undefined): string =>
  date ? String(date) : "";
