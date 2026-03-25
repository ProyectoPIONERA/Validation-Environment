import { expect, Page } from "@playwright/test";

const SUCCESS_STATES = new Set(["COMPLETED", "ENDED", "TERMINATED", "DEPROVISIONED"]);

export class TransferHistoryPage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/transfer-history`, {
      waitUntil: "networkidle",
    });
  }

  async expectReady(): Promise<void> {
    await expect(this.page).toHaveURL(/\/transfer-history(?:\/)?$/);
    await expect(this.page.getByRole("button", { name: /refresh/i })).toBeVisible({
      timeout: 30_000,
    });
  }

  async waitForSuccessfulTransfer(assetId: string, timeoutMs = 60_000): Promise<string> {
    const startedAt = Date.now();
    let lastState: string | undefined;

    while (Date.now() - startedAt < timeoutMs) {
      const state = await this.readStateForAsset(assetId);
      if (state) {
        lastState = state;
        if (state === "ERROR") {
          throw new Error(`Transfer for asset ${assetId} reached ERROR state`);
        }
        if (SUCCESS_STATES.has(state)) {
          return state;
        }
      }

      await this.refresh();
      await this.page.waitForTimeout(3_000);
    }

    throw new Error(
      `Transfer for asset ${assetId} did not reach a terminal success state. Last state: ${lastState ?? "not found"}`,
    );
  }

  async readStateForAsset(assetId: string): Promise<string | undefined> {
    await this.goToFirstPage();

    let state = await this.readStateOnCurrentPage(assetId);
    if (state) {
      return state;
    }

    while (await this.goToNextPage()) {
      state = await this.readStateOnCurrentPage(assetId);
      if (state) {
        return state;
      }
    }

    return undefined;
  }

  private async refresh(): Promise<void> {
    await this.page.getByRole("button", { name: /refresh/i }).click();
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForTimeout(500);
  }

  private async readStateOnCurrentPage(assetId: string): Promise<string | undefined> {
    const row = this.page.locator("tr.mat-mdc-row, tr.mat-row").filter({ hasText: assetId }).first();
    if ((await row.count()) === 0) {
      return undefined;
    }

    const stateCell = row.locator("td.mat-column-state, td").first();
    const state = ((await stateCell.textContent()) ?? "").trim();
    return state || undefined;
  }

  private async goToFirstPage(): Promise<void> {
    const previousButton = this.page.locator(
      "button.mat-paginator-navigation-previous, button[aria-label*='Previous page']",
    ).first();

    if ((await previousButton.count()) === 0) {
      return;
    }

    while (await previousButton.isEnabled().catch(() => false)) {
      await previousButton.click();
      await this.page.waitForLoadState("networkidle");
      await this.page.waitForTimeout(500);
    }
  }

  private async goToNextPage(): Promise<boolean> {
    const nextButton = this.page.locator(
      "button.mat-paginator-navigation-next, button[aria-label*='Next page']",
    ).first();

    if ((await nextButton.count()) === 0) {
      return false;
    }

    if (!(await nextButton.isEnabled().catch(() => false))) {
      return false;
    }

    await nextButton.click();
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForTimeout(500);
    return true;
  }
}
