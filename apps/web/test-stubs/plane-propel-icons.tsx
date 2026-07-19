/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";

// Test stub for @plane/propel/icons (the real package ships as a built artifact).
// Only the icons used by the importer components are provided.

export const PriorityIcon = (props: { priority?: string | null; size?: number }) => (
  <span data-testid="priority-icon" data-priority={props.priority ?? "none"} />
);
