/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const stub = (relativePath: string) => fileURLToPath(new URL(relativePath, import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // mirrors tsconfig paths (avoids pulling tsconfig-paths plugin).
      // order matters: "@" would swallow the more specific prefixes below it.
      "@/helpers": stub("./helpers"),
      "@/plane-web": stub("./ce"),
      "@/app": stub("./app"),
      "@": stub("./core"),
      // @plane/* ship as built artifacts (dist) not present in a dev checkout;
      // alias the ones touched by tests to lightweight local stubs.
      "@plane/i18n": stub("./test-stubs/plane-i18n.tsx"),
      "@plane/ui": stub("./test-stubs/plane-ui.tsx"),
      "@plane/utils": stub("./test-stubs/plane-utils.ts"),
      "@plane/constants": stub("./test-stubs/plane-constants.ts"),
      "@plane/propel/button": stub("./test-stubs/plane-propel-button.tsx"),
      "@plane/propel/icons": stub("./test-stubs/plane-propel-icons.tsx"),
      "@plane/propel/toast": stub("./test-stubs/plane-propel-toast.ts"),
      "next/navigation": stub("./test-stubs/next-navigation.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["{core,ce,helpers}/**/*.test.{ts,tsx}", "{core,ce,helpers}/**/*.spec.{ts,tsx}"],
    css: false,
  },
});
