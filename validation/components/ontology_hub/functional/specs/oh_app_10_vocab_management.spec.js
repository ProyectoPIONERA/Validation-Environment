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
  saveRunState,
  signInToEdition,
  signOut,
  updateVocabularyMetadata,
  VERSION_STATE_KEY,
} = require("../support/excel-flows");

test.setTimeout(60000);

function versionForCase(label, issued) {
  return {
    name: label,
    issued,
  };
}

test("OH-APP-10: edit ontology metadata and tags", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = { ...ontologyHubRuntime, ...created };
  const updatedTitle = `${created.title} Updated`;
  const updatedReview = "ADMIN TEST";
  const updatedTag = "Vocabularies";

  await updateVocabularyMetadata(page, runtime, created.prefix, {
    title: updatedTitle,
    review: updatedReview,
    tag: updatedTag,
  });
  await page.getByText(updatedTag, { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });
  await page.getByText(updatedReview, { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });
  await captureStep(page, "10-vocab-edited");
  await signOut(page, runtime);
  saveRunState(REPOSITORY_VOCAB_STATE_KEY, {
    ...created,
    title: updatedTitle,
  });

  await attachJson("10-vocab-edit-report", {
    prefix: created.prefix,
    updatedTitle,
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
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = { ...ontologyHubRuntime, ...created };
  await openVocabularyDetail(page, runtime, created.prefix, created.title || "");
  const downloadInfo = await downloadFirstN3(page, testInfo, "11-source-version", {
    strategy: "request",
  });

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
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = { ...ontologyHubRuntime, ...created };
  const initialVersion = loadRunState(VERSION_STATE_KEY);
  await signInToEdition(page, runtime);
  await openVersionsPage(page, runtime, created.prefix);
  const updatedVersion = versionForCase("v2026-01-01", "2026-01-01");
  await editVersion(page, initialVersion.name, updatedVersion);
  await captureStep(page, "12-version-edited");
  await signOut(page, runtime);
  saveRunState(VERSION_STATE_KEY, updatedVersion);

  await attachJson("12-version-edit-report", {
    prefix: created.prefix,
    initialVersion,
    updatedVersion,
  });
});

test("OH-APP-13: delete an ontology version", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = { ...ontologyHubRuntime, ...created };
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
  const created = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const runtime = { ...ontologyHubRuntime, ...created };
  await deleteVocabulary(page, runtime, created.prefix);
  await captureStep(page, "14-vocabulary-deleted");
  await signOut(page, runtime);
  deleteRunState(REPOSITORY_VOCAB_STATE_KEY);

  await attachJson("14-vocabulary-delete-report", {
    prefix: created.prefix,
  });
});
