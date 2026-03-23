class OntologyHubTermsPage {
  constructor(page) {
    this.page = page;
  }

  async goto(baseUrl, query) {
    const url = new URL("/dataset/lov/terms", baseUrl);
    if (query) {
      url.searchParams.set("q", query);
    }
    await this.page.goto(url.toString(), { waitUntil: "networkidle" });
  }

  async expectReady() {
    await this.page.locator("#searchInput").waitFor({ state: "visible" });
    await this.page.locator("#SearchGrid").waitFor({ state: "visible" });
  }

  async expectResultVisible(resultLabel) {
    await this.page.locator("#SearchGrid").getByText(resultLabel, { exact: false }).first().waitFor({
      state: "visible",
    });
  }

  facet(groupLabel) {
    return this.page.locator(".facet").filter({ has: this.page.locator(".facet-heading", { hasText: groupLabel }) }).first();
  }

  facetLink(groupLabel, valueLabel) {
    return this.facet(groupLabel).locator("a").filter({ hasText: valueLabel }).first();
  }

  async clickFacetLink(groupLabel, valueLabel) {
    await this.facetLink(groupLabel, valueLabel).click();
    await this.page.waitForLoadState("networkidle");
  }

  async currentResultCount() {
    const text = await this.page.locator(".count-items .count").first().textContent();
    return Number(text || "0");
  }
}

module.exports = {
  OntologyHubTermsPage,
};
