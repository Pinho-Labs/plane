/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Test stub for next/navigation (the web app resolves this via a shim at build time).
export const useParams = () => ({ workspaceSlug: "ws" });
export const useRouter = () => ({ push: () => {}, replace: () => {} });
export const useSearchParams = () => new URLSearchParams();
export const usePathname = () => "/";
