import { test, expect } from "../shared/fixtures/auth.fixture";
import { CatalogPage } from "../components/consumer/catalog.page";

test("04 consumer catalog: listing and detail without access errors", async ({
  page,
  portalBaseUrl,
  ensureLoggedIn,
  shellPage,
  captureStep,
  attachJson,
}) => {
  const catalogPage = new CatalogPage(page);
  const errorResponses: { url: string; status: number }[] = [];

  page.on("response", (response) => {
    const url = response.url();
    if (
      response.status() >= 400 &&
      (url.includes("/management/") || url.includes("/federatedcatalog"))
    ) {
      errorResponses.push({ url, status: response.status() });
    }
  });

  await ensureLoggedIn();
  await captureStep(page, "01-catalog-after-login");

  await shellPage.navigateToSection(/catalog|catálogo|catalogo/i, `${portalBaseUrl}/#/catalog`);
  await shellPage.assertNoGateway403("Catalog page");
  await shellPage.assertNoServerErrorBanner("Catalog page");
  await catalogPage.expectReady();
  await captureStep(page, "02-catalog-list");

  const detailOpened = await catalogPage.openFirstDetails();
  if (detailOpened) {
    await catalogPage.expectDetailsVisible();
    await shellPage.assertNoServerErrorBanner("Catalog detail");
    await captureStep(page, "03-catalog-detail");
  } else {
    await attachJson("catalog-detail-note", {
      note: "No catalog detail button found; detail-open check skipped.",
    });
  }

  expect(
    errorResponses,
    `API calls returned errors: ${JSON.stringify(errorResponses)}`,
  ).toHaveLength(0);
});
