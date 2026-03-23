const { test, expect } = require("../fixtures");
const { OntologyHubTermsPage } = require("../pages/terms.page");

test("PT5-OH-09: term search filters by tag and vocabulary in the public UI", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  const termsPage = new OntologyHubTermsPage(page);

  await termsPage.goto(ontologyHubRuntime.baseUrl, ontologyHubRuntime.expectedSearchTerm);
  await termsPage.expectReady();
  await termsPage.expectResultVisible(ontologyHubRuntime.expectedClassPrefixedName);
  await captureStep(page, "01-terms-search-initial");

  await termsPage.clickFacetLink("Tag", ontologyHubRuntime.expectedPrimaryTag);
  await expect(page).toHaveURL(new RegExp(`tag=${ontologyHubRuntime.expectedPrimaryTag}`));
  await termsPage.expectResultVisible(ontologyHubRuntime.expectedClassPrefixedName);
  await captureStep(page, "02-terms-search-tag-filter");

  await termsPage.clickFacetLink("Vocabulary", ontologyHubRuntime.expectedVocabularyPrefix);
  await expect(page).toHaveURL(new RegExp(`vocab=${ontologyHubRuntime.expectedVocabularyPrefix}`));
  await termsPage.expectResultVisible(ontologyHubRuntime.expectedClassPrefixedName);
  await captureStep(page, "03-terms-search-vocabulary-filter");

  await attachJson("pt5-oh-09-report", {
    query: ontologyHubRuntime.expectedSearchTerm,
    expectedTag: ontologyHubRuntime.expectedPrimaryTag,
    expectedVocabulary: ontologyHubRuntime.expectedVocabularyPrefix,
    resultCount: await termsPage.currentResultCount(),
    finalUrl: page.url(),
  });
});
