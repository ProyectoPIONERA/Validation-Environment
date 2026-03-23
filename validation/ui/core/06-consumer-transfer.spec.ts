import { test, expect } from "../shared/fixtures/dataspace.fixture";

import { KeycloakLoginPage } from "../components/auth/keycloak-login.page";
import { ConnectorShellPage } from "../components/shell/connector-shell.page";
import { CatalogPage } from "../components/consumer/catalog.page";
import { ContractOffersPage } from "../components/consumer/contract-offers.page";
import { ContractsPage } from "../components/consumer/contracts.page";
import { TransferHistoryPage } from "../components/consumer/transfer-history.page";
import { bootstrapProviderNegotiationArtifacts } from "../shared/utils/provider-bootstrap";

type TransferReport = {
  startedAt: string;
  providerConnector: string;
  consumerConnector: string;
  assetId: string;
  providerBootstrap?: {
    assetId: string;
    policyId: string;
    contractDefinitionId: string;
  };
  errorResponses: Array<{ url: string; status: number }>;
  negotiationMessage?: string;
  transferInitiatedMessage?: string;
  finalTransferState?: string;
  storageVerification: {
    status: "skipped";
    reason: string;
  };
};

test("06 consumer transfer: visible transfer from contracts and history", async ({
  page,
  request,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  const suffix = `${Date.now()}`;
  const assetId = `qa-ui-transfer-${suffix}`;
  const loginPage = new KeycloakLoginPage(page, {
    portalUser: dataspaceRuntime.consumer.username,
    portalPassword: dataspaceRuntime.consumer.password,
    skipLogin: false,
  });
  const shellPage = new ConnectorShellPage(page);
  const catalogPage = new CatalogPage(page);
  const contractOffersPage = new ContractOffersPage(page);
  const contractsPage = new ContractsPage(page);
  const transferHistoryPage = new TransferHistoryPage(page);
  const report: TransferReport = {
    startedAt: new Date().toISOString(),
    providerConnector: dataspaceRuntime.provider.connectorName,
    consumerConnector: dataspaceRuntime.consumer.connectorName,
    assetId,
    errorResponses: [],
    storageVerification: {
      status: "skipped",
      reason: "UI flow validates transfer initiation and successful completion in history; EDR/download remain API-level checks.",
    },
  };

  page.on("response", (response) => {
    const url = response.url();
    if (
      response.status() >= 400 &&
      (url.includes("/management/") ||
        url.includes("/federatedcatalog") ||
        url.includes("/contractnegotiations") ||
        url.includes("/transferprocess"))
    ) {
      report.errorResponses.push({ url, status: response.status() });
    }
  });

  try {
    report.providerBootstrap = await bootstrapProviderNegotiationArtifacts(
      request,
      dataspaceRuntime,
      assetId,
      suffix,
    );
    await attachJson("consumer-transfer-bootstrap", report.providerBootstrap);

    await loginPage.open(dataspaceRuntime.consumer.portalBaseUrl);
    await loginPage.loginIfNeeded();
    await shellPage.expectReady();
    await captureStep(page, "01-transfer-after-login");

    await expect(async () => {
      await catalogPage.goto(dataspaceRuntime.consumer.portalBaseUrl);
      await shellPage.assertNoGateway403("Catalog page");
      await shellPage.assertNoServerErrorBanner("Catalog page");
      await catalogPage.expectReady();

      let opened = await catalogPage.openDetailsForAsset(assetId);
      while (!opened && (await catalogPage.goToNextPage())) {
        opened = await catalogPage.openDetailsForAsset(assetId);
      }

      expect(opened, `Asset ${assetId} is not visible in the consumer catalog yet`).toBeTruthy();
    }).toPass({
      timeout: 90_000,
      intervals: [2_000, 5_000],
    });

    await contractOffersPage.expectReady();
    await captureStep(page, "02-transfer-catalog-detail");
    await contractOffersPage.openContractOffersTab();
    await captureStep(page, "03-transfer-contract-offers");

    await contractOffersPage.negotiateFirstOffer();
    report.negotiationMessage = await contractOffersPage.waitForNegotiationComplete(45_000);
    await captureStep(page, "04-transfer-negotiation-complete");

    await expect(async () => {
      await contractsPage.goto(dataspaceRuntime.consumer.portalBaseUrl);
      await shellPage.assertNoGateway403("Contracts page");
      await shellPage.assertNoServerErrorBanner("Contracts page");
      await contractsPage.expectReady();

      expect(
        await contractsPage.hasContractForAsset(assetId),
        `Contract for asset ${assetId} is not visible yet`,
      ).toBeTruthy();
    }).toPass({
      timeout: 90_000,
      intervals: [2_000, 5_000],
    });

    await captureStep(page, "05-transfer-contracts");
    report.transferInitiatedMessage = await contractsPage.startInesDataStoreTransfer(assetId);
    await captureStep(page, "06-transfer-started");

    await transferHistoryPage.goto(dataspaceRuntime.consumer.portalBaseUrl);
    await shellPage.assertNoGateway403("Transfer history page");
    await shellPage.assertNoServerErrorBanner("Transfer history page");
    await transferHistoryPage.expectReady();
    report.finalTransferState = await transferHistoryPage.waitForSuccessfulTransfer(assetId, 90_000);
    await captureStep(page, "07-transfer-history");

    expect(report.negotiationMessage, "No completed negotiation notification was detected").toMatch(
      /contract negotiation complete!/i,
    );
    expect(report.transferInitiatedMessage, "No transfer initiation notification was detected").toMatch(
      /transfer initiated successfully/i,
    );
    expect(report.finalTransferState, "No final transfer state was detected").toBeTruthy();
    expect(
      report.errorResponses,
      `API calls returned errors: ${JSON.stringify(report.errorResponses)}`,
    ).toHaveLength(0);
  } finally {
    await attachJson("consumer-transfer-report", {
      ...report,
      finishedAt: new Date().toISOString(),
    });
  }
});
