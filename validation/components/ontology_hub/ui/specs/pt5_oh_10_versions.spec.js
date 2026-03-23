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
  await expect(detailPage.versionDownloadLink(ontologyHubRuntime.latestVersionDate)).toBeVisible();
  await captureStep(page, "01-vocab-version-history");

  const pageHtml = await page.content();
  expect(pageHtml).toContain(ontologyHubRuntime.previousVersionDate);
  expect(pageHtml).toContain(ontologyHubRuntime.latestVersionDate);

  const latestResponse = await request.get(
    `${ontologyHubRuntime.baseUrl}/dataset/lov/vocabs/${ontologyHubRuntime.expectedVocabularyPrefix}/versions/${ontologyHubRuntime.latestVersionDate}.n3`,
  );
  const previousResponse = await request.get(
    `${ontologyHubRuntime.baseUrl}/dataset/lov/vocabs/${ontologyHubRuntime.expectedVocabularyPrefix}/versions/${ontologyHubRuntime.previousVersionDate}.n3`,
  );

  expect(latestResponse.ok()).toBeTruthy();
  expect(previousResponse.ok()).toBeTruthy();

  await attachJson("pt5-oh-10-report", {
    latestVersionDate: ontologyHubRuntime.latestVersionDate,
    previousVersionDate: ontologyHubRuntime.previousVersionDate,
    latestVersionStatus: latestResponse.status(),
    previousVersionStatus: previousResponse.status(),
    note: "UI coverage is currently based on the visible history widget plus the versioned .n3 resources exposed by the detail page.",
  });
});
