class OntologyHubVocabCatalogPage {
  constructor(page) {
    this.page = page;
    this.searchInput = page.locator("#searchInput");
  }

  async goto(baseUrl, query) {
    const url = new URL("/dataset/vocabs", baseUrl);
    if (query) {
      url.searchParams.set("q", query);
    }
    await this.page.goto(url.toString(), { waitUntil: "domcontentloaded" });
  }

  async expectReady() {
    await this.searchInput.waitFor({ state: "visible" });
  }

  resultItems() {
    return this.page.locator("#SearchGrid li.SearchBoxvocabulary, #SearchGrid li");
  }

  async waitForResults() {
    await this.page.locator(".count-items .count").first().waitFor({
      state: "attached",
      timeout: 15000,
    });
    await this.resultItems().first().waitFor({
      state: "attached",
      timeout: 15000,
    });
  }

  async expectResultVisible(prefixOrLabel) {
    await this.page
      .locator("#SearchGrid")
      .getByText(prefixOrLabel, { exact: false })
      .first()
      .waitFor({ state: "visible", timeout: 15000 });
  }

  async openResult(prefix) {
    const target = this.page
      .locator("#SearchGrid .prefix a")
      .filter({ hasText: prefix })
      .first();
    await target.waitFor({ state: "visible", timeout: 15000 });
    const label = ((await target.textContent()) || "").trim();
    await target.click();
    return label;
  }

  facet(groupLabel) {
    return this.page
      .locator(".facet")
      .filter({ has: this.page.locator(".facet-heading", { hasText: groupLabel }) })
      .first();
  }

  facetLink(groupLabel, valueLabel) {
    return this.facet(groupLabel).locator("a").filter({ hasText: valueLabel }).first();
  }

  firstFacetLink(groupLabel) {
    return this.facet(groupLabel).locator("a").first();
  }

  async facetLabels(groupLabel) {
    return this.facet(groupLabel)
      .locator("a")
      .evaluateAll((nodes) =>
        nodes
          .map((node) => (node.textContent || "").trim())
          .filter(Boolean),
      );
  }

  async facetHref(locator) {
    const href = await locator.getAttribute("href");
    return String(href || "").trim();
  }

  async currentResultCount() {
    const countText = await this.page.locator(".count-items .count").first().textContent().catch(() => "");
    const parsed = Number(countText || "0");
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed;
    }
    return this.resultItems().count();
  }

  suggestionItems() {
    return this.page.locator("ul.ui-autocomplete li");
  }

  async search(query) {
    await this.searchInput.fill("");
    await this.searchInput.fill(query);
  }

  async waitForSuggestions() {
    await this.suggestionItems().first().waitFor({ state: "visible" });
  }

  async suggestionLabels() {
    return this.suggestionItems().evaluateAll((nodes) =>
      nodes
        .map((node) => (node.textContent || "").trim())
        .filter(Boolean),
    );
  }

  async openSuggestion(prefix) {
    const target = prefix
      ? this.suggestionItems().filter({ hasText: prefix }).first()
      : this.suggestionItems().first();
    await target.waitFor({ state: "visible" });
    const label = ((await target.textContent()) || "").trim();
    await target.click();
    return label;
  }
}

module.exports = {
  OntologyHubVocabCatalogPage,
};
