/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import {
  STATIC_COVER_IMAGES,
  getCoverImageDisplayURL,
  getCoverImageType,
  getRandomCoverImage,
  isStaticCoverImage,
} from "../cover-image.helper";

// the project create/update flows branch on these buckets to decide whether a cover must be
// uploaded first, so they are behaviour rather than detail.
describe("getCoverImageType", () => {
  it("classifies every bundled cover as local_static", () => {
    for (const cover of Object.values(STATIC_COVER_IMAGES)) {
      expect(getCoverImageType(cover)).toBe("local_static");
    }
  });

  it("classifies unsplash URLs, including subdomains", () => {
    expect(getCoverImageType("https://unsplash.com/photos/abc")).toBe("unsplash");
    expect(getCoverImageType("https://images.unsplash.com/photo-123")).toBe("unsplash");
  });

  it("classifies remaining absolute URLs and relative asset paths as uploaded_asset", () => {
    expect(getCoverImageType("https://cdn.example.com/cover.jpg")).toBe("uploaded_asset");
    expect(getCoverImageType("/uploads/cover.jpg")).toBe("uploaded_asset");
  });

  it("does not mistake a lookalike host for unsplash", () => {
    expect(getCoverImageType("https://notunsplash.com/photo.jpg")).toBe("uploaded_asset");
  });
});

describe("isStaticCoverImage", () => {
  it("returns false for empty and non-bundled values", () => {
    expect(isStaticCoverImage(null)).toBe(false);
    expect(isStaticCoverImage(undefined)).toBe(false);
    expect(isStaticCoverImage("")).toBe(false);
    expect(isStaticCoverImage("/uploads/cover.jpg")).toBe(false);
  });

  it("returns true for a bundled cover", () => {
    expect(isStaticCoverImage(STATIC_COVER_IMAGES.IMAGE_1)).toBe(true);
  });
});

describe("getCoverImageDisplayURL", () => {
  it("falls back when there is no image", () => {
    expect(getCoverImageDisplayURL(null, "fallback.jpg")).toBe("fallback.jpg");
    expect(getCoverImageDisplayURL(undefined, null)).toBeNull();
  });

  it("serves bundled and unsplash covers untouched", () => {
    expect(getCoverImageDisplayURL(STATIC_COVER_IMAGES.IMAGE_1, null)).toBe(STATIC_COVER_IMAGES.IMAGE_1);
    expect(getCoverImageDisplayURL("https://images.unsplash.com/photo-123", null)).toBe(
      "https://images.unsplash.com/photo-123"
    );
  });

  it("resolves relative asset paths against the API host", () => {
    expect(getCoverImageDisplayURL("/uploads/cover.jpg", null)).toBe("http://api.test/uploads/cover.jpg");
  });
});

describe("getRandomCoverImage", () => {
  it("always returns a bundled cover", () => {
    for (let i = 0; i < 20; i++) {
      expect(isStaticCoverImage(getRandomCoverImage())).toBe(true);
    }
  });
});
