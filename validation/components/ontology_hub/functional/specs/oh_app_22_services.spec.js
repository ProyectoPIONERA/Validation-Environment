// Excel traceability: Ontology Hub cases 22, 23 and 24.
const fs = require("fs");

const { test, expect } = require("../../ui/fixtures");
const { OntologyHubHomePage } = require("../../ui/pages/home.page");
const { OntologyHubVocabCatalogPage } = require("../../ui/pages/vocab-catalog.page");
const {
  expectHealthyPage,
  listZipEntries,
  loadRunState,
  openVocabularyDetail,
  persistGeneratedArtifact,
  resolveThemisTestFile,
  runtimeFromCreatedVocabulary,
  resolveThemisSource,
  signInToEdition,
  signOut,
  URI_VOCAB_STATE_KEY,
} = require("../support/excel-flows");

test.setTimeout(60000);

test("OH-APP-22: patterns page generates a zip", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}, testInfo) => {
  await signInToEdition(page, ontologyHubRuntime);
  await page.goto(`${ontologyHubRuntime.baseUrl}/dataset/patterns`, { waitUntil: "domcontentloaded" });
  await expectHealthyPage(page, "Patterns");

  const selectAllButton = page.locator("button, input[type='submit'], input[type='button']").filter({
    hasText: /select all/i,
  }).first();
  if ((await selectAllButton.count()) === 0) {
    throw new Error("Patterns page does not expose the 'Select All' control expected by the Excel flow.");
  }

  await selectAllButton.click();

  const bothOption = page.getByLabel(/both/i).first();
  if ((await bothOption.count()) > 0) {
    await bothOption.check().catch(async () => {
      await bothOption.click();
    });
  }

  const noOption = page.getByLabel(/^no$/i).first();
  if ((await noOption.count()) > 0) {
    await noOption.check().catch(async () => {
      await noOption.click();
    });
  }

  const submitButton = page.locator("button, input[type='submit']").filter({ hasText: /submit/i }).first();
  if ((await submitButton.count()) === 0) {
    throw new Error("Patterns page does not expose the Submit control expected by the Excel flow.");
  }

  const downloadPromise = page.waitForEvent("download", { timeout: 5000 });
  await submitButton.click();
  const download = await downloadPromise;
  const filePath = testInfo.outputPath("patterns.zip");
  await download.saveAs(filePath);
  const persistedPath = persistGeneratedArtifact(filePath, "excel-22-patterns.zip", "patterns");

  const stat = fs.statSync(filePath);
  expect(stat.size).toBeGreaterThan(0);
  const entries = listZipEntries(filePath);
  const hasDataFolder = entries.some((entry) => entry.startsWith("data/"));
  const hasWebFolder = entries.some((entry) => entry.startsWith("web/"));
  expect(hasDataFolder).toBeTruthy();
  expect(hasWebFolder).toBeTruthy();
  await captureStep(page, "22-patterns");
  await signOut(page, ontologyHubRuntime);

  await attachJson("22-patterns-report", {
    downloadFile: download.suggestedFilename(),
    size: stat.size,
    entries,
    hasDataFolder,
    hasWebFolder,
    persistedPath,
  });
});

test("OH-APP-23: FOOPS metrics are shown for a vocabulary", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const created = loadRunState(URI_VOCAB_STATE_KEY);
  const flowRuntime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  await signInToEdition(page, flowRuntime);
  const prefix = created.prefix;
  const title = created.title;

  const catalogPage = new OntologyHubVocabCatalogPage(page);
  await Promise.all([
    page.waitForURL(/\/dataset\/vocabs(?:\?|$)/, { timeout: 5000 }),
    page.getByRole("link", { name: /vocabs/i }).first().click(),
  ]);
  await catalogPage.expectReady();
  await catalogPage.search("saref4grid");
  await catalogPage.waitForSuggestions().catch(async () => {
    await catalogPage.waitForResults();
  });
  if ((await catalogPage.suggestionItems().count().catch(() => 0)) > 0) {
    await catalogPage.openSuggestion("saref4grid");
  } else {
    await catalogPage.expectResultVisible("saref4grid");
    await catalogPage.openResult(prefix);
  }

  await openVocabularyDetail(page, flowRuntime, prefix, title);
  await page.locator(".ontology-tab, a, button").filter({ hasText: /foops/i }).first().click();
  await page.locator("#foopsHeader").waitFor({ state: "visible", timeout: 5000 });
  const foopsResults = page.locator("#foops-results");
  const callFoopsButton = page.locator("#callFoopsButton");
  const bodyText = await page
    .locator("body")
    .evaluate((node) => (node.textContent || "").replace(/\s+/g, " ").trim())
    .catch(() => "");
  const foopsAlreadyRendered =
    /FOOPS! FAIR VALIDATOR/i.test(bodyText) &&
    /(Reusable|Findable|Accessible|Interoperable)/i.test(bodyText);
  if (!(await foopsResults.isVisible().catch(() => false)) && !foopsAlreadyRendered) {
    await callFoopsButton.waitFor({ state: "visible", timeout: 5000 });
    await callFoopsButton.click();
    await foopsResults.waitFor({ state: "visible", timeout: 5000 });
  }
  await page.locator("text=/FOOPS! FAIR VALIDATOR/i").first().waitFor({ state: "visible", timeout: 5000 });
  await captureStep(page, "23-foops");
  await signOut(page, flowRuntime);

  await attachJson("23-foops-report", {
    prefix,
    title,
    searchTerm: "saref4grid",
    url: page.url(),
  });
});

test("OH-APP-24: Themis accepts a test file and downloads results", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}, testInfo) => {
  const created = loadRunState(URI_VOCAB_STATE_KEY);
  const flowRuntime = runtimeFromCreatedVocabulary(ontologyHubRuntime, created);
  await signInToEdition(page, flowRuntime);
  const prefix = created.prefix;
  const title = created.title;

  const homePage = new OntologyHubHomePage(page);
  await homePage.goto(flowRuntime.baseUrl);
  await homePage.expectReady();
  await homePage.openVocabularyBubble(prefix);
  await page.waitForURL(new RegExp(`/dataset/vocabs/${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`), {
    timeout: 5000,
  });
  await expectHealthyPage(page, `Vocabulary detail for ${prefix}`);

  await page.locator("#normal-button").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#normal-button").click();
  await page.locator("#user-options").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#user-options img[src='/img/themis.png']").first().click();

  await page.locator("#themisVocabContainer").waitFor({ state: "visible", timeout: 5000 });
  const themisSource = await resolveThemisSource(page);
  const sourceUrl = themisSource.sourceUrl || `/dataset/vocabs/${prefix}/versions/${themisSource.prefix || ""}.n3`;
  const testFilePath = resolveThemisTestFile();
  const persistedUploadedPath = persistGeneratedArtifact(testFilePath, "excel-24-test_cases.txt", "themis");

  await page.locator("#themisModeManual").check().catch(async () => {
    await page.locator("#themisModeManual").click();
  });
  await page.locator("label").filter({ hasText: /user tests/i }).first().waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
  await page.locator("#themisUploadContainer").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#themisTestFile").setInputFiles(testFilePath);
  await page.locator("#executeThemisButton").click();
  await page.locator("#themis-results").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#themisResultsBody tr").first().waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#downloadThemisButton").waitFor({ state: "visible", timeout: 5000 });

  const downloadPromise = page.waitForEvent("download", { timeout: 5000 });
  await page.locator("#downloadThemisButton").click();
  const download = await downloadPromise;
  const outputPath = testInfo.outputPath("themis-results.txt");
  await download.saveAs(outputPath);
  const persistedResultPath = persistGeneratedArtifact(outputPath, "excel-24-themis-results.txt", "themis");
  const stat = fs.statSync(outputPath);
  expect(stat.size).toBeGreaterThan(0);
  const themisUrl = page.url();

  await captureStep(page, "24-themis");
  await signOut(page, flowRuntime);

  await attachJson("24-themis-report", {
    prefix,
    title,
    sourceUrl,
    themisUrl,
    uploadedFile: testFilePath,
    persistedUploadedPath,
    resultDownload: download.suggestedFilename(),
    resultSize: stat.size,
    persistedResultPath,
  });
});
