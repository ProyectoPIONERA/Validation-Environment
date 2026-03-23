const { test } = require("../fixtures");
const { OntologyHubVocabDetailPage } = require("../pages/vocab-detail.page");

test("PT5-OH-12: vocabulary detail exposes statistics and LOD usage markers", async ({
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
  await detailPage.expectStatisticsMarkers();
  await page.getByText("Vocabulary used in", { exact: false }).waitFor({ state: "visible" });
  await captureStep(page, "01-vocab-detail-statistics");

  await attachJson("pt5-oh-12-report", {
    chartSelector: "#chartElements",
    lodSectionVisible: true,
    url: page.url(),
  });
});
