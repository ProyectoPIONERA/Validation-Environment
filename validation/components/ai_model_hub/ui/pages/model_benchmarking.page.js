const { expect } = require("../fixtures");

class ModelBenchmarkingPage {
  constructor(page, runtime) {
    this.page = page;
    this.runtime = runtime;
    this.root = page.locator("app-model-benchmarking");
    this.heading = page.getByRole("heading", { name: "Model Benchmarking" });
    this.modelSearchInput = page.getByPlaceholder("Search by name, id, tag, or task...");
    this.datasetSearchInput = page.getByPlaceholder("Search datasets by name, id, task, tags...");
    this.loadSelectedDatasetButton = page.getByRole("button", { name: /Load Selected Dataset/i });
    this.validateInputButton = page.getByRole("button", { name: /Validate Input/i });
    this.runBenchmarkButton = page.getByRole("button", { name: /Run Benchmark/i });
    this.inputPathInput = page.getByPlaceholder("ex: input");
    this.expectedPathInput = page.getByPlaceholder("ex: expected_label");
    this.predictionPathInput = page.getByPlaceholder("ex: result.label");
    this.statusMessage = page.locator("div.text-sm.opacity-80").last();
    this.datasetParseMessage = page.locator("div.text-success").filter({
      hasText: /Loaded \d+ rows from dataspace asset/i,
    });
  }

  async goto() {
    await this.page.goto(`${this.runtime.baseUrl}${this.runtime.modelBenchmarkingPath}`);
  }

  async waitUntilReady() {
    await expect(this.root).toBeVisible();
    await expect(this.heading).toBeVisible();
    await expect(this.modelSearchInput).toBeVisible();
    await expect(this.datasetSearchInput).toBeVisible();
  }

  modelOptionByText(text) {
    return this.page
      .locator("label")
      .filter({
        has: this.page.locator("input[type='checkbox']"),
        hasText: text,
      })
      .first();
  }

  datasetOptionByText(text) {
    return this.page
      .locator("label")
      .filter({
        has: this.page.locator("input[type='radio'][name='dataspaceDataset']"),
        hasText: text,
      })
      .first();
  }

  async selectModelByText(text) {
    const option = this.modelOptionByText(text);
    await expect(option).toBeVisible({ timeout: 20000 });
    await option.locator("input[type='checkbox']").check();
  }

  async selectDataspaceDatasetByText(text) {
    const option = this.datasetOptionByText(text);
    await expect(option).toBeVisible({ timeout: 20000 });
    await option.locator("input[type='radio']").check();
  }

  async loadSelectedDataset() {
    await expect(this.loadSelectedDatasetButton).toBeEnabled();
    await this.loadSelectedDatasetButton.click();
    await expect(this.datasetParseMessage).toBeVisible({ timeout: 30000 });
  }
}

module.exports = {
  ModelBenchmarkingPage,
};
