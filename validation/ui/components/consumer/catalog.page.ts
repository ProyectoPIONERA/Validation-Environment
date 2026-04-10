import { expect, Page } from "@playwright/test";

import { clickMarked } from "../../shared/utils/live-marker";

export class CatalogPage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/#/catalog`, {
      waitUntil: "networkidle",
    });
  }

  async expectReady(): Promise<void> {
    await expect(this.page).toHaveURL(/\/catalog/);
  }

  async openFirstDetails(): Promise<boolean> {
    const detailButton = this.page
      .locator("button:visible")
      .filter({ hasText: /view details and contract offers/i })
      .first();

    if ((await detailButton.count()) === 0) {
      return false;
    }

    await clickMarked(detailButton);
    await this.page.waitForTimeout(500);
    return true;
  }

  async openDetailsForAsset(assetId: string): Promise<boolean> {
    const assetCard = this.page.locator(".card mat-card").filter({
      has: this.page.locator("mat-card-title", { hasText: assetId }),
    }).first();

    if ((await assetCard.count()) === 0) {
      return false;
    }

    await clickMarked(assetCard.getByRole("button", { name: /view details and contract offers/i }));
    await this.page.waitForTimeout(500);
    return true;
  }

  async hasNextPage(): Promise<boolean> {
    const nextButton = this.page.locator(
      "button.mat-paginator-navigation-next, button[aria-label*='Next page']",
    ).first();

    if ((await nextButton.count()) === 0) {
      return false;
    }

    return nextButton.isEnabled().catch(() => false);
  }

  async goToNextPage(): Promise<boolean> {
    const nextButton = this.page.locator(
      "button.mat-paginator-navigation-next, button[aria-label*='Next page']",
    ).first();

    if ((await nextButton.count()) === 0) {
      return false;
    }

    if (!(await nextButton.isEnabled().catch(() => false))) {
      return false;
    }

    await clickMarked(nextButton);
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForTimeout(500);
    return true;
  }

  async expectDetailsVisible(): Promise<void> {
    const markers = this.page.locator(
      "text=/Go back|Volver|Asset information|Informaci[oó]n del asset|Contract Offers|Ofertas de contrato|General information|Informaci[oó]n general/i",
    );
    await expect(markers.first()).toBeVisible({ timeout: 15_000 });
  }
}
