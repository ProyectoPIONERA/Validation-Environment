const { clickMarked } = require("../support/live-marker");
const { resolveOntologyHubTimeouts } = require("../runtime");

const { readyTimeoutMs } = resolveOntologyHubTimeouts();

class OntologyHubHomePage {
  constructor(page) {
    this.page = page;
  }

  async goto(baseUrl) {
    await this.page.goto(`${baseUrl}/dataset`, { waitUntil: "domcontentloaded" });
  }

  async expectReady() {
    await this.page.locator("header nav").waitFor({ state: "visible" });
    await this.page.locator("#searchInput").waitFor({ state: "visible" });
  }

  vocabularyBubble(prefix) {
    const escaped = String(prefix || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return this.page
      .locator("#vis svg g.node")
      .filter({
        has: this.page.locator("title", {
          hasText: new RegExp(`^\\s*${escaped}(?:\\s*-.*)?$`, "i"),
        }),
      })
      .first();
  }

  async openVocabularyBubble(prefix) {
    const bubble = this.vocabularyBubble(prefix);
    await bubble.waitFor({ state: "visible", timeout: readyTimeoutMs });
    const circle = bubble.locator("circle").first();
    if ((await circle.count()) > 0) {
      await clickMarked(circle);
      return;
    }
    await clickMarked(bubble);
  }

  navLink(label) {
    return this.page.locator("header nav a").filter({ hasText: label }).first();
  }

  async gotoApiDocs() {
    await this.page.goto(new URL("/dataset/api", this.page.url()).toString(), {
      waitUntil: "domcontentloaded",
    });
  }
}

module.exports = {
  OntologyHubHomePage,
};
