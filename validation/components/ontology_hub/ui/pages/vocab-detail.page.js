class OntologyHubVocabDetailPage {
  constructor(page) {
    this.page = page;
  }

  async goto(baseUrl, prefix) {
    await this.page.goto(`${baseUrl}/dataset/lov/vocabs/${prefix}`, { waitUntil: "networkidle" });
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
    await this.page.getByText("Vocabulary Version History", { exact: true }).waitFor({
      state: "visible",
    });
    await this.page.locator("#timeline").waitFor({ state: "visible" });
  }

  versionDownloadLink(dateString) {
    return this.page.locator(`a[href$='/dataset/lov/vocabs/demohub/versions/${dateString}.n3']`).first();
  }
}

module.exports = {
  OntologyHubVocabDetailPage,
};
