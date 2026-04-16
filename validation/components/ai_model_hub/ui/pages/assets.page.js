const { expect } = require("../fixtures");

class AssetCreateDialog {
  constructor(page) {
    this.page = page;
    this.root = page.locator("lib-asset-create");
    this.idInput = this.root.locator("input[name='id']");
    this.nameInput = this.root.locator("input[placeholder='Name']");
    this.contentTypeInput = this.root.locator("input[name='contenttype']");
    this.dataTypeSelect = this.root.locator("select[name='dataType']");
    this.baseUrlInput = this.root.locator("input[name='baseUrl']");
    this.enableMlMetadataToggle = this.root.locator("input[formcontrolname='mlEnabled']");
    this.mlDescriptionTextarea = this.root.locator("textarea[formcontrolname='mlDescription']");
    this.mlVersionInput = this.root.locator("input[formcontrolname='mlVersion']");
    this.mlAssetKindSelect = this.root.locator("select[formcontrolname='mlAssetKind']");
    this.mlTaskSelect = this.root.locator("select[formcontrolname='mlTask']");
    this.propertiesEditor = this.root.locator("lib-json-object-input").first();
    this.propertyKeyInput = this.propertiesEditor.locator("input[placeholder='Key']");
    this.propertyValueInput = this.propertiesEditor.locator("input[placeholder='Value']");
    this.propertyAddButton = this.propertiesEditor.locator("button").filter({ hasText: /^Add$/i }).first();
    this.createAssetButton = this.root.locator("button").filter({ hasText: /Create Asset/i }).first();
    this.errorLabel = this.root.locator(".text-error");
  }

  async waitUntilReady() {
    await expect(this.root).toBeVisible();
    await expect(this.dataTypeSelect).toBeVisible();
  }

  async fillCommonFields({ id, name, contentType }) {
    if (id) {
      await this.idInput.fill(id);
    }
    if (name) {
      await this.nameInput.fill(name);
    }
    if (contentType) {
      await this.contentTypeInput.fill(contentType);
    }
  }

  async selectFirstDataType() {
    const options = await this.dataTypeSelect.locator("option").allTextContents();
    const normalizedOptions = options.map((option) => option.trim());
    if (normalizedOptions.includes("HttpData")) {
      await this.dataTypeSelect.selectOption({ label: "HttpData" });
    } else {
      await this.dataTypeSelect.selectOption({ index: 0 });
    }
    await expect(this.baseUrlInput).toBeVisible();
  }

  async fillBaseUrl(baseUrl) {
    await this.baseUrlInput.fill(baseUrl);
  }

  async enableMlMetadataHelper() {
    await this.enableMlMetadataToggle.check({ force: true });
    await expect(this.mlDescriptionTextarea).toBeVisible();
    await expect(this.mlVersionInput).toBeVisible();
  }

  async fillMlMetadata({ description, version, assetKind, task }) {
    if (description) {
      await this.mlDescriptionTextarea.fill(description);
    }
    if (version) {
      await this.mlVersionInput.fill(version);
    }
    if (assetKind) {
      await this.mlAssetKindSelect.selectOption(assetKind);
    }
    if (task) {
      await this.mlTaskSelect.selectOption(task);
    }
  }

  async addProperty(key, value) {
    await this.propertyKeyInput.fill(key);
    await this.propertyValueInput.fill(value);
    await this.propertyAddButton.click();
    await expect(this.propertyKeyInput).toHaveValue("");
    await expect(this.propertyValueInput).toHaveValue("");
  }

  async submit() {
    await this.createAssetButton.click();
  }
}

class AssetsPage {
  constructor(page, runtime) {
    this.page = page;
    this.runtime = runtime;
    this.searchInput = page.locator("lib-filter-input input");
    this.createButtons = page.locator("#router-content button").filter({ hasText: /Create/i });
    this.assetCards = page.locator("lib-asset-card");
    this.successAlert = page.locator(".alert-success");
    this.errorAlert = page.locator(".alert-error");
    this.connectorDropdownButton = page
      .locator(".navbar-center [role='button']")
      .filter({ hasText: /Provider|Consumer/i })
      .first();
  }

  async goto() {
    await this.page.goto(`${this.runtime.baseUrl}${this.runtime.assetsPath}`);
  }

  async waitUntilReady() {
    await expect(this.searchInput).toBeVisible();
    await expect(this.createButtons.first()).toBeVisible();
  }

  async switchToConnector(connectorName) {
    await this.connectorDropdownButton.click();
    const option = this.page.locator(
      `input[name='edc-config-dropdown'][aria-label='${connectorName}']`,
    );
    await option.click({ force: true });
    await expect(this.connectorDropdownButton).toContainText(connectorName);
  }

  async openCreateAssetDialog() {
    await this.createButtons.first().click();
    const dialog = new AssetCreateDialog(this.page);
    await dialog.waitUntilReady();
    return dialog;
  }
}

module.exports = {
  AssetsPage,
  AssetCreateDialog,
};
