const { test, expect } = require("../fixtures");

test("PT5-OH-09: term search filters by tag and vocabulary in the public UI", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await page.goto(
    `${ontologyHubRuntime.baseUrl}/dataset/vocabs?q=${encodeURIComponent(ontologyHubRuntime.listingSearchTerm)}`,
    { waitUntil: "networkidle" },
  );
  await page.locator("#searchInput").waitFor({ state: "visible" });
  await page.locator("#SearchGrid").waitFor({ state: "visible" });
  await page.locator("#SearchGrid li").first().waitFor({ state: "visible" });
  await captureStep(page, "01-vocabulary-search-initial");

  const tagFacetLink = page
    .locator(".facet")
    .filter({ has: page.locator(".facet-heading", { hasText: "Tag" }) })
    .locator("a")
    .first();
  await expect(tagFacetLink).toBeVisible();
  const selectedTag = ((await tagFacetLink.textContent()) || "").trim();
  await tagFacetLink.click();
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/tag=/);
  await page.locator("#searchInput").waitFor({ state: "visible" });
  await captureStep(page, "02-vocabulary-tag-filter");

  const languageFacetLink = page
    .locator(".facet")
    .filter({ has: page.locator(".facet-heading", { hasText: "Language" }) })
    .locator("a")
    .first();
  let selectedLanguage = null;
  let languageFilterApplied = false;
  if ((await languageFacetLink.count()) > 0) {
    await expect(languageFacetLink).toBeVisible();
    selectedLanguage = ((await languageFacetLink.textContent()) || "").trim();
    await languageFacetLink.click();
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/lang=/);
    await page.locator("#searchInput").waitFor({ state: "visible" });
    await captureStep(page, "03-vocabulary-language-filter");
    languageFilterApplied = true;
  }

  await attachJson("pt5-oh-09-report", {
    query: ontologyHubRuntime.listingSearchTerm,
    selectedTag,
    selectedLanguage,
    languageFilterApplied,
    resultCount: await page.locator("#SearchGrid li").count(),
    finalUrl: page.url(),
  });
});
