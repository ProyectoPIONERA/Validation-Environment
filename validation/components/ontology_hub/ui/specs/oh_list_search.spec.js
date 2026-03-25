const { test, expect } = require("../fixtures");

test("OH-LIST-SEARCH: public catalog lists vocabularies and opens a search result", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await page.goto(`${ontologyHubRuntime.baseUrl}/dataset/vocabs`, { waitUntil: "networkidle" });
  await page.locator("#searchInput").waitFor({ state: "visible" });
  await page.locator("#SearchGrid").waitFor({ state: "visible" });

  const initialCount = await page.locator("#SearchGrid li").count();
  expect(initialCount).toBeGreaterThan(0);
  await captureStep(page, "01-vocabulary-list");

  await page.locator("#searchInput").fill(ontologyHubRuntime.listingSearchTerm);
  await page.locator("#searchInput").press("Enter");
  await page.waitForLoadState("networkidle");
  await page.locator("#SearchGrid").waitFor({ state: "visible" });

  const firstResult = page.locator("#SearchGrid a[href^='/dataset/vocabs/']").first();
  const firstResultText = ((await firstResult.textContent()) || "").trim();
  await firstResult.click();

  await expect(page).toHaveURL(new RegExp("/dataset/vocabs/[^/]+/?$"));
  await page.locator("section#posts").getByText("Metadata", { exact: true }).waitFor({
    state: "visible",
  });
  await captureStep(page, "02-opened-search-result");

  await attachJson("oh-list-search-report", {
    query: ontologyHubRuntime.listingSearchTerm,
    initialCount,
    openedResult: firstResultText,
    finalUrl: page.url(),
  });
});
