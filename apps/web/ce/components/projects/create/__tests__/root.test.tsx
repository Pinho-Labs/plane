/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
// `toastCalls` is a stub-only recorder; import it from the stub directly so tsc
// resolves it (the vitest alias maps @plane/propel/toast to this same file at runtime).
import { toastCalls } from "../../../../../test-stubs/plane-propel-toast";
import { STATIC_COVER_IMAGES } from "@/helpers/cover-image.helper";
import { CreateProjectForm } from "../root";

const { createProject, updateProject, addProjectToFavorites, uploadCoverImage } = vi.hoisted(() => ({
  createProject: vi.fn(),
  updateProject: vi.fn(),
  addProjectToFavorites: vi.fn(),
  uploadCoverImage: vi.fn(),
}));

vi.mock("@/hooks/store/use-project", () => ({
  useProject: () => ({ createProject, updateProject, addProjectToFavorites }),
}));
vi.mock("@/hooks/use-platform-os", () => ({ usePlatformOS: () => ({ isMobile: false }) }));

// partial mock: the payload under test depends on the real classification, only the upload is stubbed.
vi.mock("@/helpers/cover-image.helper", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/helpers/cover-image.helper")>()),
  uploadCoverImage,
}));

// the presentational children are irrelevant to the submit payload; only the submit button matters.
vi.mock("@/components/project/create/header", () => ({ default: () => <div data-testid="header" /> }));
vi.mock("@/components/project/create/common-attributes", () => ({ default: () => <div data-testid="common" /> }));
vi.mock("../attributes", () => ({ ProjectAttributes: () => <div data-testid="attributes" /> }));
vi.mock("@/components/project/create/project-create-buttons", () => ({
  default: () => <button type="submit">submit</button>,
}));

const UPLOADED_ASSET = "/uploads/cover-asset.jpg";
const STATIC_COVER = STATIC_COVER_IMAGES.IMAGE_6;
const EXTERNAL_COVER = "https://images.unsplash.com/photo-123";
// a cover picked from the "Upload" tab: already an asset, stored as a relative path
const RELATIVE_ASSET_COVER = "/uploads/existing-cover.jpg";

const onClose = vi.fn();
const handleNextStep = vi.fn();
const updateCoverImageStatus = vi.fn<(projectId: string, coverImage: string) => Promise<void>>();

const renderForm = (coverImageUrl?: string) =>
  render(
    <CreateProjectForm
      workspaceSlug="ws"
      onClose={onClose}
      handleNextStep={handleNextStep}
      updateCoverImageStatus={updateCoverImageStatus}
      data={{ name: "Alpha", identifier: "AL", cover_image_url: coverImageUrl }}
    />
  );

const submit = async () => userEvent.click(screen.getByRole("button", { name: "submit" }));

const payload = () => createProject.mock.calls[0][1];

describe("CreateProjectForm cover image handling", () => {
  beforeEach(() => {
    toastCalls.length = 0;
    vi.clearAllMocks();
    createProject.mockResolvedValue({ id: "new-project-id" });
    updateCoverImageStatus.mockResolvedValue(undefined);
    uploadCoverImage.mockResolvedValue(UPLOADED_ASSET);
  });

  it("uploads a bundled cover and persists it via cover_image (not the read-only cover_image_url)", async () => {
    renderForm(STATIC_COVER);
    await submit();

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(1));
    expect(uploadCoverImage).toHaveBeenCalledTimes(1);
    // absolute URL, because cover_image is a plain text column read back as-is by the API
    expect(payload()).toMatchObject({
      cover_image: `http://api.test${UPLOADED_ASSET}`,
      cover_image_asset: null,
    });
    // regression: the bundled asset path must never reach the API as the cover
    expect(payload().cover_image).not.toBe(STATIC_COVER);
  });

  it("sends an external cover URL straight through without uploading it", async () => {
    renderForm(EXTERNAL_COVER);
    await submit();

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(1));
    expect(uploadCoverImage).not.toHaveBeenCalled();
    expect(payload()).toMatchObject({ cover_image: EXTERNAL_COVER, cover_image_asset: null });
  });

  it("binds the uploaded asset to the new project and does not follow up with a project update", async () => {
    renderForm(STATIC_COVER);
    await submit();

    await waitFor(() => expect(updateCoverImageStatus).toHaveBeenCalledTimes(1));
    expect(updateCoverImageStatus).toHaveBeenCalledWith("new-project-id", UPLOADED_ASSET);
    // the old PATCH sent cover_image_url, which the API ignores: it only desynced the local
    // store from the server, so the cover vanished on reload
    expect(updateProject).not.toHaveBeenCalled();
  });

  it("absolutizes a cover already uploaded to the workspace and binds its status", async () => {
    renderForm(RELATIVE_ASSET_COVER);
    await submit();

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(1));
    expect(uploadCoverImage).not.toHaveBeenCalled();
    // a relative asset path stored raw in cover_image is not resolvable by the clients reading it back
    expect(payload()).toMatchObject({ cover_image: `http://api.test${RELATIVE_ASSET_COVER}` });
    expect(updateCoverImageStatus).toHaveBeenCalledWith("new-project-id", RELATIVE_ASSET_COVER);
  });

  it("still reports success when binding the cover asset fails", async () => {
    updateCoverImageStatus.mockRejectedValue(new Error("asset not found"));
    renderForm(STATIC_COVER);
    await submit();

    // the project exists and carries its cover, so a failed binding is not a creation failure
    await waitFor(() => expect(handleNextStep).toHaveBeenCalledWith("new-project-id"));
    expect(toastCalls[0]).toMatchObject({ type: "success" });
  });

  it("leaves the cover fields untouched when no cover is selected", async () => {
    renderForm(undefined);
    await submit();

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(1));
    expect(uploadCoverImage).not.toHaveBeenCalled();
    expect(payload().cover_image).toBeUndefined();
  });

  it("aborts creation when the cover upload fails", async () => {
    uploadCoverImage.mockRejectedValue(new Error("upload boom"));
    renderForm(STATIC_COVER);
    await submit();

    await waitFor(() => expect(toastCalls).toHaveLength(1));
    expect(toastCalls[0]).toMatchObject({ type: "error", message: "upload boom" });
    expect(createProject).not.toHaveBeenCalled();
  });

  it("advances to the next step and reports success once the project is created", async () => {
    renderForm(EXTERNAL_COVER);
    await submit();

    await waitFor(() => expect(handleNextStep).toHaveBeenCalledWith("new-project-id"));
    expect(toastCalls[0]).toMatchObject({ type: "success" });
  });

  it("surfaces the API error code when the identifier is already taken", async () => {
    createProject.mockRejectedValue({ data: { identifier: ["PROJECT_IDENTIFIER_ALREADY_EXIST"] } });
    renderForm(EXTERNAL_COVER);
    await submit();

    await waitFor(() => expect(toastCalls).toHaveLength(1));
    expect(toastCalls[0]).toMatchObject({ type: "error", message: "project_identifier_already_taken" });
    expect(handleNextStep).not.toHaveBeenCalled();
  });
});
