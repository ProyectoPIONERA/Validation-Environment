// Excel traceability: Ontology Hub cases 10, 11, 12, 13 and 14.
const { test } = require("../../ui/fixtures");
const {
  createVersion,
  deleteRunState,
  deleteVersion,
  deleteVocabulary,
  downloadFirstN3,
  editVersion,
  loadRunState,
  openVocabularyDetail,
  openVersionsPage,
  REPOSITORY_VOCAB_STATE_KEY,
  runtimeFromCreatedVocabulary,
  saveRunState,
  signInToEdition,
  signOut,
  updateVocabularyMetadata,
  URI_VOCAB_STATE_KEY,
  VISUALIZATION_N3_STATE_KEY,
  VERSION_STATE_KEY,
} = require("../support/excel-flows");

function versionForCase(label, issued) {
  return {
    name: label,
    issued,
  };
}

function resolveVersionSourceDownload() {
  try {
    const downloaded = loadRunState(VISUALIZATION_N3_STATE_KEY);
    const candidate = downloaded.persistedPath || downloaded.filePath || "";
    if (candidate) {
      return {
        ...downloaded,
        filePath: candidate,
        source: "oh-app-05",
      };
    }
  } catch (error) {
    // Fall back to an inline download to keep the suite runnable when OH-05 has not run.
  }

  return null;
}

test("OH-APP-10: edit ontology metadata and tags", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  test.setTimeout(180000);
  const created = loadRunState(URI_VOCAB_STATE_KEY);
  const runtime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  const updatedReview = "ADMIN TEST";
  const updatedTag = "Vocabularies";

  await updateVocabularyMetadata(page, runtime, created.prefix, {
    review: updatedReview,
    tag: updatedTag,
  });
  await page.getByText(updatedTag, { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });
  await page.getByText(updatedReview, { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });
  await captureStep(page, "10-vocab-edited");
  await signOut(page, runtime);

  await attachJson("10-vocab-edit-report", {
    prefix: created.prefix,
    title: created.title,
    updatedReview,
    updatedTag,
  });
});

test("OH-APP-11: add a new ontology version", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}, testInfo) => {
  test.setTimeout(180000);
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  let downloadInfo = resolveVersionSourceDownload();
  if (!downloadInfo) {
    await openVocabularyDetail(page, runtime, created.prefix, created.title || "");
    downloadInfo = await downloadFirstN3(page, testInfo, "11-source-version", {
      strategy: "request",
    });
  }

  await signInToEdition(page, runtime);
  await openVersionsPage(page, runtime, created.prefix);
  const newVersion = versionForCase("1.0", "2026-03-31");
  await createVersion(page, newVersion, downloadInfo.filePath);
  await captureStep(page, "11-version-created");
  await signOut(page, runtime);
  saveRunState(VERSION_STATE_KEY, newVersion);

  await attachJson("11-version-create-report", {
    prefix: created.prefix,
    downloadInfo,
    newVersion,
  });
});

test("OH-APP-12: edit an ontology version", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  test.setTimeout(180000);
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  const initialVersion = loadRunState(VERSION_STATE_KEY);
  await signInToEdition(page, runtime);
  await openVersionsPage(page, runtime, created.prefix);
  const updatedVersion = versionForCase("v2026-01-01", "2026-01-01");
  const editOutcome = await editVersion(page, runtime, created.prefix, initialVersion.name, updatedVersion);
  await captureStep(page, "12-version-edited");
  await signOut(page, runtime);
  saveRunState(VERSION_STATE_KEY, updatedVersion);

  await attachJson("12-version-edit-report", {
    prefix: created.prefix,
    initialVersion,
    updatedVersion,
    editOutcome,
  });
});

test("OH-APP-13: delete an ontology version", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  test.setTimeout(180000);
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  const version = loadRunState(VERSION_STATE_KEY);
  await signInToEdition(page, runtime);
  await openVersionsPage(page, runtime, created.prefix);
  await deleteVersion(page, version.name);
  await captureStep(page, "13-version-deleted");
  await signOut(page, runtime);
  deleteRunState(VERSION_STATE_KEY);

  await attachJson("13-version-delete-report", {
    prefix: created.prefix,
    version,
  });
});

test("OH-APP-14: delete an ontology", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  test.setTimeout(180000);
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  await deleteVocabulary(page, runtime, created.prefix);
  await captureStep(page, "14-vocabulary-deleted");
  await signOut(page, runtime);
  deleteRunState(REPOSITORY_VOCAB_STATE_KEY);

  await attachJson("14-vocabulary-delete-report", {
    prefix: created.prefix,
  });
});
