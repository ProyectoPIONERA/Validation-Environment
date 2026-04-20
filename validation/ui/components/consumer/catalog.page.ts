import { expect, Locator, Page } from "@playwright/test";

import { clickMarked } from "../../shared/utils/live-marker";
import { waitForUiTransition } from "../../shared/utils/waiting";

type AttachJson = (name: string, payload: unknown) => Promise<void>;

type DetailExpectationOptions = {
  assetId?: string;
  attachJson?: AttachJson;
  context?: string;
  timeoutMs?: number;
};

export type CatalogDetailDiagnostics = {
  assetId?: string;
  currentUrl: string;
  reachedDetailRoute: boolean;
  detailMarkerCount: number;
  contractOffersTabCount: number;
  visibleHeadings: string[];
  visibleButtons: string[];
  bodyTextSample: string;
};

const DETAIL_MARKERS =
  /Go back|Volver|Asset information|Informaci[oó]n del asset|Contract Offers|Ofertas de contrato|General information|Informaci[oó]n general/i;

export class CatalogPage {
  constructor(private readonly page: Page) {}

  async goto(baseUrl: string): Promise<void> {
    await this.page.goto(`${baseUrl.replace(/\/$/, "")}/catalog`, {
      waitUntil: "domcontentloaded",
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
    await waitForUiTransition(this.page);
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
    await waitForUiTransition(this.page);
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
    await waitForUiTransition(this.page);
    return true;
  }

  async collectDetailDiagnostics(assetId?: string): Promise<CatalogDetailDiagnostics> {
    const detailMarkers = this.page.getByText(DETAIL_MARKERS);
    return {
      assetId,
      currentUrl: this.page.url(),
      reachedDetailRoute: this.page.url().includes("/catalog/datasets/view"),
      detailMarkerCount: await detailMarkers.count().catch(() => 0),
      contractOffersTabCount: await this.page
        .getByRole("tab", { name: /contract offers/i })
        .count()
        .catch(() => 0),
      visibleHeadings: await this.visibleTexts("h1, h2, h3, mat-card-title, .mat-mdc-tab, .mat-tab-label"),
      visibleButtons: await this.visibleTexts("button"),
      bodyTextSample: await this.textSample(this.page.locator("body")),
    };
  }

  async expectDetailsVisible(options: DetailExpectationOptions = {}): Promise<void> {
    const markers = this.page.getByText(DETAIL_MARKERS);

    try {
      await expect(
        markers.first(),
        "Catalog detail view did not render after opening asset details",
      ).toBeVisible({ timeout: options.timeoutMs ?? 15_000 });
    } catch (error: unknown) {
      const diagnostics = await this.collectDetailDiagnostics(options.assetId);
      if (options.attachJson) {
        await options.attachJson(
          `${options.context ?? "catalog-detail"}-diagnostics`,
          diagnostics,
        );
      }

      throw new Error(
        [
          "Catalog detail view did not render after opening asset details.",
          `Current URL: ${diagnostics.currentUrl}`,
          `Reached /catalog/datasets/view: ${diagnostics.reachedDetailRoute}`,
          `Detail marker count: ${diagnostics.detailMarkerCount}`,
          `Contract Offers tab count: ${diagnostics.contractOffersTabCount}`,
          `Visible headings: ${JSON.stringify(diagnostics.visibleHeadings)}`,
          `Visible buttons: ${JSON.stringify(diagnostics.visibleButtons)}`,
          `Original error: ${errorMessage(error)}`,
        ].join("\n"),
      );
    }
  }

  private async visibleTexts(selector: string, limit = 25): Promise<string[]> {
    const locator = this.page.locator(selector);
    const count = Math.min(await locator.count().catch(() => 0), limit);
    const texts: string[] = [];

    for (let index = 0; index < count; index += 1) {
      const item = locator.nth(index);
      if (!(await item.isVisible().catch(() => false))) {
        continue;
      }

      const text = normalizeText(await item.innerText({ timeout: 1_000 }).catch(() => ""));
      if (text) {
        texts.push(text.slice(0, 240));
      }
    }

    return texts;
  }

  private async textSample(locator: Locator): Promise<string> {
    const text = await locator.innerText({ timeout: 2_000 }).catch((error: unknown) => {
      return `<text unavailable: ${errorMessage(error)}>`;
    });
    return normalizeText(text).slice(0, 1_500);
  }
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
