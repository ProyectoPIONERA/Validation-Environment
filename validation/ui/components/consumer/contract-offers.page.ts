import { expect, Page } from "@playwright/test";

import { snackBar } from "../../shared/utils/selectors";

export class ContractOffersPage {
  constructor(private readonly page: Page) {}

  async expectReady(): Promise<void> {
    await expect(this.page.getByRole("tab", { name: /contract offers/i })).toBeVisible({
      timeout: 30_000,
    });
  }

  async openContractOffersTab(): Promise<void> {
    await this.page.getByRole("tab", { name: /contract offers/i }).click();
    await expect(this.page.getByRole("button", { name: /negotiate contract/i }).first()).toBeVisible({
      timeout: 15_000,
    });
  }

  async negotiateFirstOffer(): Promise<void> {
    await this.page.getByRole("button", { name: /negotiate contract/i }).first().click();
  }

  async waitForNegotiationComplete(timeoutMs = 40_000): Promise<string> {
    const notification = snackBar(this.page);
    await expect(notification).toContainText(/contract negotiation complete!/i, {
      timeout: timeoutMs,
    });
    return ((await notification.textContent()) ?? "").replace(/\s+/g, " ").trim();
  }
}
