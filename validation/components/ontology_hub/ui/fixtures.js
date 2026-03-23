const fs = require("fs");

const { test: base, expect } = require("./playwright-runtime");
const { resolveOntologyHubRuntime } = require("./runtime");

const test = base.extend({
  ontologyHubRuntime: async ({}, use) => {
    await use(resolveOntologyHubRuntime());
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
