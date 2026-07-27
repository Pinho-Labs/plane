/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Test stub for @plane/utils (the real package ships as a built artifact).
// Only the helpers used by the components under test are provided.

import { API_BASE_URL } from "./plane-constants";

type ClassValue =
  | string
  | number
  | null
  | false
  | undefined
  | ClassValue[]
  | Record<string, boolean | undefined | null>;

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

// must stay faithful to the real helper: cover image tests assert on relative vs absolute paths.
export const getFileURL = (path: string): string | undefined => {
  if (!path) return undefined;
  if (path.startsWith("http")) return path;
  return `${API_BASE_URL}${path}`;
};

export const renderFormattedDate = (date: string | Date | null | undefined): string => (date ? String(date) : "");
