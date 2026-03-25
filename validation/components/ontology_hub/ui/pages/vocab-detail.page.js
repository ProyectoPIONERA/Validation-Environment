class OntologyHubVocabDetailPage {
  constructor(page) {
    this.page = page;
  }

  async goto(baseUrl, prefix) {
    await this.page.goto(`${baseUrl}/dataset/vocabs/${prefix}`, { waitUntil: "networkidle" });
  }

  async expectReady(titleText, prefix) {
    await this.page.locator("section#posts").getByText("Metadata", { exact: true }).waitFor({
      state: "visible",
    });
    await this.page.locator("section#post").getByText(prefix, { exact: false }).first().waitFor({
      state: "visible",
    });
    await this.page.locator("section#post").getByText(titleText, { exact: false }).first().waitFor({
      state: "visible",
    });
  }

  async expectMetadataMarkers() {
    await this.page.getByText("URI", { exact: true }).waitFor({ state: "visible" });
    await this.page.getByText("Description", { exact: true }).waitFor({ state: "visible" });
    await this.page.getByText("Tags", { exact: true }).waitFor({ state: "visible" });
  }

  async expectStatisticsMarkers() {
    await this.page.getByText("Statistics", { exact: true }).waitFor({ state: "visible" });
    await this.page.locator("#chartElements").waitFor({ state: "visible" });
    await this.page.getByText("Classes", { exact: true }).waitFor({ state: "visible" });
    await this.page.getByText("Properties", { exact: true }).waitFor({ state: "visible" });
    await this.page.getByText("Datatypes", { exact: true }).waitFor({ state: "visible" });
    await this.page.getByText("Instances", { exact: true }).waitFor({ state: "visible" });
  }

  async expectVersionHistoryMarkers() {
    await this.page.locator(".ontology-tab").filter({ hasText: "Version History" }).first().click();
    await this.page.getByText("Vocabulary Version History", { exact: true }).waitFor({
      state: "visible",
    });
    await this.page.locator("#timeline").waitFor({ state: "visible" });
  }

  versionDownloadLink(dateString) {
    return this.page
      .locator("[data-onto-panel='version-history'].is-active")
      .getByRole("link", { name: `Download ${dateString}.n3`, exact: true })
      .first();
  }

  async exposedVersionResourceUrls(baseUrl, prefix) {
    const hrefUrls = await this.page
      .locator(`a[href*="/dataset/vocabs/${prefix}/versions/"][href$=".n3"]`)
      .evaluateAll((nodes) =>
        nodes
          .map((node) => node.getAttribute("href") || "")
          .filter(Boolean),
      );
    const dataSourceUrls = await this.page
      .locator("[data-source-url]")
      .evaluateAll((nodes) =>
        nodes
          .map((node) => node.getAttribute("data-source-url") || "")
          .filter(Boolean),
      );
    return Array.from(
      new Set(
        [...hrefUrls, ...dataSourceUrls]
          .filter((value) => value.includes(`/dataset/vocabs/${prefix}/versions/`))
          .map((value) => new URL(value, baseUrl).toString()),
      ),
    );
  }
}

module.exports = {
  OntologyHubVocabDetailPage,
};
