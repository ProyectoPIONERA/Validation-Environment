import { expect, Page } from "@playwright/test";

import { materialInput, materialSelect, snackBar } from "../../shared/utils/selectors";

type ContractDefinitionListExpectations = {
  policyId?: string;
  assetId?: string;
};

export class ContractDefinitionCreatePage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/contract-definitions/create`, {
      waitUntil: "networkidle",
    });
  }

  async gotoList(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/contract-definitions`, {
      waitUntil: "networkidle",
    });
  }

  async expectReady(): Promise<void> {
    await expect(
      this.page.locator("mat-card-title", { hasText: /Create a contract definition/i }),
    ).toBeVisible({ timeout: 30_000 });
  }

  async fillContractDefinitionId(contractDefinitionId: string): Promise<void> {
    await materialInput(this.page, /^ID$/).fill(contractDefinitionId);
  }

  async selectAccessPolicy(policyId: string): Promise<void> {
    await materialSelect(this.page, /Access policy/i).click();
    await this.page.locator("mat-option").filter({ hasText: policyId }).first().click();
  }

  async selectContractPolicy(policyId: string): Promise<void> {
    await materialSelect(this.page, /Contract policy/i).click();
    await this.page.locator("mat-option").filter({ hasText: policyId }).first().click();
  }

  async addAsset(assetId: string): Promise<void> {
    const assetInput = this.page.locator("input[placeholder='Search assets']").first();
    await expect(assetInput).toBeVisible({ timeout: 15_000 });
    await assetInput.fill(assetId);
    await this.page.locator("mat-option").filter({ hasText: assetId }).first().click();

    await expect(this.page.locator("mat-chip").filter({ hasText: assetId }).first()).toBeVisible({
      timeout: 15_000,
    });
  }

  async submit(): Promise<void> {
    await this.page.getByRole("button", { name: /^Create$/i }).click();
  }

  async waitForCreationSuccess(timeoutMs = 30_000): Promise<string> {
    const notification = snackBar(this.page);
    await expect(notification).toContainText(/contract definition created/i, {
      timeout: timeoutMs,
    });
    return ((await notification.textContent()) ?? "").replace(/\s+/g, " ").trim();
  }

  async expectContractDefinitionListed(
    contractDefinitionId: string,
    expectations: ContractDefinitionListExpectations = {},
    timeoutMs = 45_000,
  ): Promise<void> {
    await expect(async () => {
      const found = await this.findContractDefinition(contractDefinitionId, expectations);
      expect(
        found,
        `Contract definition ${contractDefinitionId} is not visible in the contract definitions list`,
      ).toBeTruthy();
    }).toPass({
      timeout: timeoutMs,
      intervals: [1_000, 2_000, 5_000],
    });
  }

  private async findContractDefinition(
    contractDefinitionId: string,
    expectations: ContractDefinitionListExpectations,
  ): Promise<boolean> {
    if ((await this.contractDefinitionCard(contractDefinitionId, expectations).count()) > 0) {
      return true;
    }

    while (await this.goToNextPage()) {
      if ((await this.contractDefinitionCard(contractDefinitionId, expectations).count()) > 0) {
        return true;
      }
    }

    return false;
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

  private contractDefinitionCard(
    contractDefinitionId: string,
    expectations: ContractDefinitionListExpectations,
  ) {
    let card = this.page.locator(".card mat-card").filter({ hasText: contractDefinitionId });

    if (expectations.policyId) {
      card = card.filter({ hasText: expectations.policyId });
    }

    if (expectations.assetId) {
      card = card.filter({ hasText: expectations.assetId });
    }

    return card.first();
  }
}
