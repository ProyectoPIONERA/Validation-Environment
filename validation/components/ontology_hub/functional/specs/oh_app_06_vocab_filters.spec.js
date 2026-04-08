// Excel traceability: Ontology Hub cases 6, 7, 8 and 9.
const { test } = require("../../ui/fixtures");
const { OntologyHubVocabCatalogPage } = require("../../ui/pages/vocab-catalog.page");
const {
  waitForCatalogReady,
  waitForCatalogResults,
} = require("../support/functional");
const {
  loadRunState,
  runtimeFromCreatedVocabulary,
  signInToEdition,
  signOut,
  REPOSITORY_VOCAB_STATE_KEY,
  URI_VOCAB_STATE_KEY,
} = require("../support/excel-flows");

test.setTimeout(45000);

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function applyFacetLink(page, catalogPage, groupLabel, valueLabel) {
  const facetLink = catalogPage.facetLink(groupLabel, valueLabel);
  if ((await facetLink.count()) === 0) {
    throw new Error(`Facet '${groupLabel}' with value '${valueLabel}' is not available in this deployment.`);
  }

  const href = await catalogPage.facetHref(facetLink);
  if (!href) {
    throw new Error(`Facet '${groupLabel}' with value '${valueLabel}' does not expose a navigable link.`);
  }

  const url = new URL(href, page.url()).toString();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await waitForCatalogReady(page, 5000);
  await waitForCatalogResults(page, 5000);
  const count = await catalogPage.currentResultCount().catch(() => null);
  if (!count || count <= 0) {
    throw new Error(`Facet '${groupLabel}' with value '${valueLabel}' returned no catalog results.`);
  }
  return { applied: true, url, count };
}

async function runFacetCase(page, ontologyHubRuntime, facetGroup, facetValue, captureStep, attachJson, reportName) {
  const uriVocabulary = loadRunState(URI_VOCAB_STATE_KEY);
  const repositoryVocabulary = loadRunState(REPOSITORY_VOCAB_STATE_KEY);
  const flowRuntime = runtimeFromCreatedVocabulary(ontologyHubRuntime, uriVocabulary, {
    listingSearchTerm: "",
  });

  await signInToEdition(page, flowRuntime);
  const catalogPage = new OntologyHubVocabCatalogPage(page);
  const query = "";

  await catalogPage.goto(flowRuntime.baseUrl, query);
  await waitForCatalogReady(page, 5000);
  await waitForCatalogResults(page, 5000);

  const outcome = await applyFacetLink(page, catalogPage, facetGroup, facetValue);
  if (/tag|language/i.test(String(facetGroup))) {
    const expectedLabel = uriVocabulary.catalogLabel || repositoryVocabulary.catalogLabel || uriVocabulary.title;
    await catalogPage.expectResultVisible(expectedLabel);
  }
  await captureStep(page, reportName);
  await signOut(page, flowRuntime);

  await attachJson(`${reportName}-report`, {
    query,
    facetGroup: String(facetGroup),
    facetValue: String(facetValue),
    outcome,
    uriVocabulary,
    repositoryVocabulary,
  });
}

test("OH-APP-06: vocabulary catalog filters by class", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await runFacetCase(page, ontologyHubRuntime, /Type/i, /class/i, captureStep, attachJson, "06-class-filter");
});

test("OH-APP-07: vocabulary catalog filters by property", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await runFacetCase(
    page,
    ontologyHubRuntime,
    /Type/i,
    /property/i,
    captureStep,
    attachJson,
    "07-property-filter",
  );
});

test("OH-APP-08: vocabulary catalog filters by tag Services", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await runFacetCase(
    page,
    ontologyHubRuntime,
    /Tag/i,
    new RegExp(`^\\s*${escapeRegExp("Services")}(?:\\s*\\(\\d+\\))?\\s*$`, "i"),
    captureStep,
    attachJson,
    "08-tag-filter",
  );
});

test("OH-APP-09: vocabulary catalog filters by language English", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await runFacetCase(
    page,
    ontologyHubRuntime,
    /Language/i,
    new RegExp(`^\\s*${escapeRegExp("English")}(?:\\s*\\(\\d+\\))?\\s*$`, "i"),
    captureStep,
    attachJson,
    "09-language-filter",
  );
});
