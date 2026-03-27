const { test } = require("../fixtures");
const { OntologyHubVocabCatalogPage } = require("../pages/vocab-catalog.page");
const { OntologyHubVocabDetailPage } = require("../pages/vocab-detail.page");

test("PT5-OH-01: vocabulary can be created from URI and become visible in the catalog", async ({
  page,
  ontologyHubRuntime,
  ontologyHubBootstrap,
  captureStep,
  attachJson,
}) => {
  test.skip(
    ontologyHubBootstrap.source !== "created" &&
      !ontologyHubBootstrap.creationOutcome?.reusedExistingImport &&
      !ontologyHubBootstrap.managedVocabulary,
    "PT5-OH-01 requiere un vocabulario nuevo creado por el bootstrap, uno importado por ese mismo flujo o un vocabulario temporal gestionado por el framework. El entorno actual reutilizo un vocabulario no apto para esta validacion.",
  );

  const detailPage = new OntologyHubVocabDetailPage(page);
  let publicationVerification = "direct-detail";

  if (ontologyHubBootstrap.capabilities.publicVocabularyAutocomplete) {
    publicationVerification = "catalog-autocomplete";
    const catalogPage = new OntologyHubVocabCatalogPage(page);
    await catalogPage.goto(ontologyHubRuntime.baseUrl, ontologyHubBootstrap.prefix);
    await catalogPage.expectReady();
    await catalogPage.search(ontologyHubBootstrap.prefix);
    await catalogPage.waitForSuggestions();
    await catalogPage.openSuggestion(ontologyHubBootstrap.prefix);
  } else {
    await detailPage.goto(ontologyHubRuntime.baseUrl, ontologyHubBootstrap.prefix);
  }

  await detailPage.expectReady(ontologyHubBootstrap.prefix, ontologyHubBootstrap.title);
  await captureStep(page, "01-created-vocabulary-public-detail");

  await attachJson("pt5-oh-01-report", {
    creationMethod: ontologyHubBootstrap.creationMethod,
    creationUri: ontologyHubBootstrap.creationUri,
    creationRepositoryUri: ontologyHubBootstrap.creationRepositoryUri,
    creationPrefix: ontologyHubBootstrap.prefix,
    creationNamespace: ontologyHubBootstrap.creationNamespace,
    source: ontologyHubBootstrap.source,
    managedVocabulary: Boolean(ontologyHubBootstrap.managedVocabulary),
    creationOutcome: ontologyHubBootstrap.creationOutcome,
    capabilities: ontologyHubBootstrap.capabilities,
    finalUrl: page.url(),
    publicationVerification,
  });
});
