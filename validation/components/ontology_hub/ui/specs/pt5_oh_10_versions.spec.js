const { test, expect } = require("../fixtures");
const { OntologyHubVocabDetailPage } = require("../pages/vocab-detail.page");

test("PT5-OH-10: version history and version resources are exposed from the vocabulary detail page", async ({
  page,
  request,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const detailPage = new OntologyHubVocabDetailPage(page);

  await detailPage.goto(ontologyHubRuntime.baseUrl, ontologyHubRuntime.expectedVocabularyPrefix);
  await detailPage.expectReady(
    ontologyHubRuntime.expectedVocabularyTitle,
    ontologyHubRuntime.expectedVocabularyPrefix,
  );
  await detailPage.expectVersionHistoryMarkers();
  const versionLabels = page
    .locator("[data-onto-panel='version-history'].is-active")
    .getByText(/v\d{4}-\d{2}-\d{2}/);
  const versionDates = await versionLabels.evaluateAll((nodes) =>
    Array.from(
      new Set(
        nodes
          .map((node) => (node.textContent || "").match(/v(\d{4}-\d{2}-\d{2})/))
          .filter(Boolean)
          .map((match) => match[1]),
      ),
    ),
  );
  expect(versionDates.length).toBeGreaterThan(0);
  await captureStep(page, "01-vocab-version-history");

  const pageHtml = await page.content();
  expect(pageHtml).toContain("Vocabulary Version History");

  const versionUrls = await detailPage.exposedVersionResourceUrls(
    ontologyHubRuntime.baseUrl,
    ontologyHubRuntime.expectedVocabularyPrefix,
  );
  expect(versionUrls.length).toBeGreaterThan(0);

  const resourceDates = versionUrls
    .map((url) => url.match(/\/versions\/(\d{4}-\d{2}-\d{2})\.n3$/))
    .filter(Boolean)
    .map((match) => match[1]);
  expect(resourceDates.length).toBeGreaterThan(0);
  expect(resourceDates.some((dateString) => versionDates.includes(dateString))).toBeTruthy();

  const responseStatuses = [];
  for (const url of versionUrls.slice(0, 2)) {
    const response = await request.get(url);
    responseStatuses.push({
      url,
      status: response.status(),
      ok: response.ok(),
    });
  }
  expect(responseStatuses.length).toBeGreaterThan(0);
  expect(responseStatuses.every((entry) => entry.status < 500)).toBeTruthy();

  await attachJson("pt5-oh-10-report", {
    versionDates,
    versionUrls,
    responseStatuses,
    note: "UI coverage is currently based on the visible history widget plus the versioned .n3 resource URLs exposed by the detail page. Download availability may still depend on the seeded version files present in the current deployment.",
  });
});
