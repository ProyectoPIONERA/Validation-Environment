const { expect } = require("../fixtures");

class CatalogPage {
  constructor(page, runtime) {
    this.page = page;
    this.runtime = runtime;
    this.root = page.locator("lib-catalog-request");
    this.requestButton = page.locator("lib-catalog-request .btn");
    this.catalogCards = page.locator("lib-catalog-card");
    this.errorAlert = page.locator(".alert-error");
  }

  async goto() {
    await this.page.goto(`${this.runtime.baseUrl}${this.runtime.catalogPath}`);
  }

  async waitUntilReady() {
    await expect(this.root).toBeVisible();
  }
}

module.exports = {
  CatalogPage,
};
