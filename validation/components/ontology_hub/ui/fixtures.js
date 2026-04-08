const fs = require("fs");

const { test: base, expect } = require("./playwright-runtime");
const { resolveOntologyHubRuntime } = require("./runtime");
const { ensureOntologyHubBootstrap } = require("./support/bootstrap");

const test = base.extend({
  page: async ({ page }, use) => {
    page.setDefaultTimeout(5000);
    page.setDefaultNavigationTimeout(5000);
    await use(page);
  },

  ontologyHubRuntime: async ({}, use) => {
    await use(resolveOntologyHubRuntime());
  },

  ontologyHubBootstrap: async ({ page, ontologyHubRuntime }, use) => {
    await use(await ensureOntologyHubBootstrap(page, ontologyHubRuntime));
  },

  captureStep: async ({}, use, testInfo) => {
    await use(async (page, name) => {
      const outputPath = testInfo.outputPath(`${name}.png`);
      await page.screenshot({ path: outputPath, fullPage: true });
      await testInfo.attach(name, {
        path: outputPath,
        contentType: "image/png",
      });
    });
  },

  attachJson: async ({}, use, testInfo) => {
    await use(async (name, payload) => {
      const outputPath = testInfo.outputPath(`${name}.json`);
      fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2), "utf8");
      await testInfo.attach(name, {
        path: outputPath,
        contentType: "application/json",
      });
    });
  },
});

module.exports = {
  test,
  expect,
};
