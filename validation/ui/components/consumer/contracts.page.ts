import { expect, Page } from "@playwright/test";

import { materialSelect, snackBar } from "../../shared/utils/selectors";

export class ContractsPage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/contracts`, {
      waitUntil: "networkidle",
    });
  }

  async expectReady(): Promise<void> {
    await expect(this.page).toHaveURL(/\/contracts(?:\/)?$/);
    await expect(
      this.page.locator(".container .card mat-card, .no-items").first(),
    ).toBeVisible({ timeout: 30_000 });
  }

  async hasContractForAsset(assetId: string): Promise<boolean> {
    return (await this.contractCard(assetId).count()) > 0;
  }

  async startInesDataStoreTransfer(assetId: string): Promise<string> {
    const card = this.contractCard(assetId);
    await expect(card).toBeVisible({ timeout: 30_000 });

    await card.getByRole("button", { name: /^Transfer$/i }).click();
    const dialog = this.page.getByRole("dialog", { name: /Transfer/i });
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    await materialSelect(this.page, "Destination").click();
    await this.page.locator("mat-option").filter({ hasText: /InesDataStore/i }).first().click();
    await dialog.getByRole("button", { name: /start transfer/i }).click();

    const notification = snackBar(this.page);
    await expect(notification).toContainText(/transfer initiated successfully/i, {
      timeout: 30_000,
    });
    return ((await notification.textContent()) ?? "").replace(/\s+/g, " ").trim();
  }

  private contractCard(assetId: string) {
    return this.page.locator(".card mat-card").filter({ hasText: assetId }).first();
  }
}
