import { test, expect } from "../shared/fixtures/auth.fixture";
import { CatalogPage } from "../components/consumer/catalog.page";
import { collectBrowserDiagnostics } from "../shared/utils/browser-diagnostics";

test("04 consumer catalog: listing and detail without access errors", async ({
  page,
  portalBaseUrl,
  ensureLoggedIn,
  shellPage,
  captureStep,
  attachJson,
}) => {
  const catalogPage = new CatalogPage(page);
  const browserDiagnostics = collectBrowserDiagnostics(page);
  const errorResponses: { url: string; status: number }[] = [];
  const startedAt = new Date().toISOString();

  page.on("response", (response) => {
    const url = response.url();
    if (
      response.status() >= 400 &&
      (url.includes("/management/") || url.includes("/federatedcatalog"))
    ) {
      errorResponses.push({ url, status: response.status() });
    }
  });

  try {
    await ensureLoggedIn();
    await captureStep(page, "01-catalog-after-login");

    await catalogPage.goto(portalBaseUrl);
    await shellPage.assertNoGateway403("Catalog page");
    await shellPage.assertNoServerErrorBanner("Catalog page");
    await catalogPage.expectReady();
    await captureStep(page, "02-catalog-list");

    const detailOpened = await catalogPage.openFirstDetails();
    expect(detailOpened, "No catalog detail button found; catalog detail could not be validated").toBeTruthy();

    await catalogPage.expectDetailsVisible({
      attachJson,
      context: "consumer-catalog-detail",
    });
    await shellPage.assertNoServerErrorBanner("Catalog detail");
    await captureStep(page, "03-catalog-detail");

    expect(
      errorResponses,
      `API calls returned errors: ${JSON.stringify(errorResponses)}`,
    ).toHaveLength(0);
  } finally {
    const browserDiagnosticsSnapshot = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("consumer-catalog-browser-diagnostics", browserDiagnosticsSnapshot);
    await attachJson("consumer-catalog-report", {
      startedAt,
      finishedAt: new Date().toISOString(),
      errorResponses,
      browserDiagnostics: {
        eventCount: browserDiagnosticsSnapshot.eventCount,
        droppedEventCount: browserDiagnosticsSnapshot.droppedEventCount,
      },
    });
  }
});
