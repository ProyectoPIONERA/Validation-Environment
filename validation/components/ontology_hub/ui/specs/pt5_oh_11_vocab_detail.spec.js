const { test } = require("../fixtures");
const { OntologyHubVocabDetailPage } = require("../pages/vocab-detail.page");

test("PT5-OH-11: vocabulary detail displays metadata and descriptive sections", async ({
  page,
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
  await detailPage.expectMetadataMarkers();
  await page.getByText(ontologyHubRuntime.expectedPrimaryTag, { exact: false }).waitFor({
    state: "visible",
  });
  await page.getByText(ontologyHubRuntime.expectedSecondaryTag, { exact: false }).waitFor({
    state: "visible",
  });
  await captureStep(page, "01-vocab-detail-metadata");

  await attachJson("pt5-oh-11-report", {
    vocabularyPrefix: ontologyHubRuntime.expectedVocabularyPrefix,
    vocabularyTitle: ontologyHubRuntime.expectedVocabularyTitle,
    tags: [
      ontologyHubRuntime.expectedPrimaryTag,
      ontologyHubRuntime.expectedSecondaryTag,
    ],
    url: page.url(),
  });
});
