/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Pinho Labs (fork): bulk operations unlocked. Upstream returns false here
// (the feature lives in the closed ee/). The real toolbar is in
// ce/components/issues/bulk-operations/root.tsx.
export const useBulkOperationStatus = () => true;
