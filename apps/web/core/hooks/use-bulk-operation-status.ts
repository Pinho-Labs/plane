/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Pinho Labs (fork): bulk operations destravado. O upstream retorna false aqui
// (a feature vive no ee/ fechado). A toolbar real está em
// ce/components/issues/bulk-operations/root.tsx.
export const useBulkOperationStatus = () => true;
