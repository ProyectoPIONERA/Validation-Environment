import { expect, Page } from "@playwright/test";

import { materialInput, materialSelect, snackBar } from "../../shared/utils/selectors";

export class AssetCreatePage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/assets/create`, {
      waitUntil: "networkidle",
    });
  }

  async expectReady(): Promise<void> {
    await expect(
      this.page.locator("mat-card-title", { hasText: "Create an asset" }),
    ).toBeVisible({ timeout: 30_000 });
  }

  async fillRequiredFields(assetId: string, folderName: string): Promise<void> {
    await materialInput(this.page, "ID").fill(assetId);
    await materialInput(this.page, "Name").fill(`QA Asset ${assetId}`);
    await materialInput(this.page, "Version").fill("1.0");
    await materialInput(this.page, "Short description").fill(
      "Validacion automatica con Playwright para subida de asset",
    );
    await materialInput(this.page, "Keywords").fill("qa,playwright,upload");

    await materialSelect(this.page, "Asset type").click();
    await this.page.locator("mat-option").filter({ hasText: "Dataset" }).first().click();

    const editor = this.page.locator(".ck-editor__editable[contenteditable='true']").first();
    await editor.click();
    await editor.fill("Descripcion de prueba automatizada para subida de asset");

    await this.page.getByRole("tab", { name: "Storage information" }).click();
    await expect(
      this.page.getByRole("tabpanel", { name: "Storage information" }),
    ).toBeVisible({ timeout: 15_000 });

    await materialSelect(this.page, "Destination").click();
    await this.page.locator("mat-option").filter({ hasText: "InesDataStore" }).first().click();
    await materialInput(this.page, "Folder").fill(folderName);
  }

  async uploadFile(filePath: string): Promise<void> {
    await this.page.setInputFiles("input#fileDropRef", filePath);
  }

  async submit(): Promise<void> {
    const uploadProgress = this.page.getByText(/Uploading file:/i).first();
    if ((await uploadProgress.count()) > 0) {
      await expect(uploadProgress).toBeHidden({ timeout: 120_000 });
    }

    const blockingOverlay = this.page.locator("app-spinner .overlay").first();
    if ((await blockingOverlay.count()) > 0) {
      await expect(blockingOverlay).toBeHidden({ timeout: 15_000 });
    }

    await this.page.getByRole("button", { name: /^Create$/ }).click();
  }

  async isCreateButtonVisible(): Promise<boolean> {
    return this.page.getByRole("button", { name: /^Create$/ }).isVisible().catch(() => false);
  }

  async waitForSnackBarText(timeoutMs: number): Promise<string | undefined> {
    const container = snackBar(this.page);
    try {
      await container.waitFor({ state: "visible", timeout: timeoutMs });
      const text = (await container.textContent()) ?? "";
      return text.replace(/\s+/g, " ").trim();
    } catch {
      return undefined;
    }
  }
}
