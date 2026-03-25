const { expect } = require("../fixtures");

class MlAssetsPage {
  constructor(page, runtime) {
    this.page = page;
    this.runtime = runtime;
    this.root = page.locator("app-ml-assets-browser");
    this.searchInput = page.locator("lib-filter-input input");
    this.filterHeading = page.getByRole("heading", { name: "Filters" });
    this.clearFiltersButton = page.locator("aside button").filter({ hasText: "Clear" });
    this.errorAlert = page.locator(".alert-error");
    this.assetCards = page.locator("article.card");
    this.filterCheckboxes = page.locator("aside input[type='checkbox']");
    this.noResultsMessage = page.locator("section p.text-sm.text-center.opacity-60");
  }

  async goto() {
    await this.page.goto(`${this.runtime.baseUrl}${this.runtime.mlAssetsPath}`);
  }

  async waitUntilReady() {
    await expect(this.root).toBeVisible();
    await expect(this.searchInput).toBeVisible();
    await Promise.race([
      this.assetCards.first().waitFor({ state: "visible", timeout: 15000 }).catch(() => null),
      this.noResultsMessage.first().waitFor({ state: "visible", timeout: 15000 }).catch(() => null),
      this.errorAlert.first().waitFor({ state: "visible", timeout: 15000 }).catch(() => null),
    ]);
  }
}

module.exports = {
  MlAssetsPage,
};
