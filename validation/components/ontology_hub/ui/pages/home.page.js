class OntologyHubHomePage {
  constructor(page) {
    this.page = page;
  }

  async goto(baseUrl) {
    await this.page.goto(`${baseUrl}/dataset`, { waitUntil: "networkidle" });
  }

  async expectReady() {
    await this.page.locator("header nav").waitFor({ state: "visible" });
    await this.page.locator("#searchInput").waitFor({ state: "visible" });
  }

  navLink(label) {
    return this.page.locator("header nav a").filter({ hasText: label }).first();
  }

  async gotoApiDocs() {
    await this.page.goto(new URL("/dataset/api", this.page.url()).toString(), {
      waitUntil: "networkidle",
    });
  }
}

module.exports = {
  OntologyHubHomePage,
};
