/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Test stub for @plane/i18n (the real package ships as a built artifact).
// Returns the key so assertions can target stable strings.
export const useTranslation = () => ({ t: (key: string) => key });
