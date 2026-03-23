import { test, expect } from "../shared/fixtures/dataspace.fixture";
import fs from "fs";
import os from "os";
import path from "path";

import { KeycloakLoginPage } from "../components/auth/keycloak-login.page";
import { ConnectorShellPage } from "../components/shell/connector-shell.page";
import { AssetCreatePage } from "../components/provider/asset-create.page";
import { PolicyCreatePage } from "../components/provider/policy-create.page";
import { ContractDefinitionCreatePage } from "../components/provider/contract-definition-create.page";

type UploadFileHandle = {
  path: string;
  cleanup: () => void;
};

type ProviderContractDefinitionReport = {
  startedAt: string;
  baseUrl: string;
  assetId: string;
  policyId: string;
  contractDefinitionId: string;
  filePath: string;
  assetMessage?: string;
  policyMessage?: string;
  contractDefinitionMessage?: string;
};

function createSmallUploadFile(): UploadFileHandle {
  const filePath = path.join(os.tmpdir(), `playwright-contract-definition-${Date.now()}.bin`);
  fs.writeFileSync(filePath, Buffer.alloc(1024 * 1024, "A"));
  return {
    path: filePath,
    cleanup: () => {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    },
  };
}

test("03c provider setup: contract definition creation from the UI", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  const suffix = `${Date.now()}`;
  const portalBaseUrl = dataspaceRuntime.provider.portalBaseUrl;
  const portalObjectPrefix = process.env.PORTAL_TEST_OBJECT_PREFIX ?? "playwright-e2e";
  const assetId = `qa-ui-contract-asset-${suffix}`;
  const policyId = `qa-ui-contract-policy-${suffix}`;
  const contractDefinitionId = `qa-ui-contract-definition-${suffix}`;
  const participantId = `participant-${suffix}`;
  const upload = createSmallUploadFile();
  const loginPage = new KeycloakLoginPage(page, {
    portalUser: dataspaceRuntime.provider.username,
    portalPassword: dataspaceRuntime.provider.password,
    skipLogin: false,
  });
  const shellPage = new ConnectorShellPage(page);
  const assetCreatePage = new AssetCreatePage(page);
  const policyCreatePage = new PolicyCreatePage(page);
  const contractDefinitionCreatePage = new ContractDefinitionCreatePage(page);
  const report: ProviderContractDefinitionReport = {
    startedAt: new Date().toISOString(),
    baseUrl: portalBaseUrl,
    assetId,
    policyId,
    contractDefinitionId,
    filePath: upload.path,
  };

  try {
    await loginPage.open(portalBaseUrl);
    await loginPage.loginIfNeeded();
    await shellPage.expectReady();
    await captureStep(page, "01-contract-definition-after-login");

    await assetCreatePage.goto(portalBaseUrl);
    await assetCreatePage.expectReady();
    await assetCreatePage.fillRequiredFields(assetId, `${portalObjectPrefix}/${assetId}`);
    await assetCreatePage.uploadFile(upload.path);
    await captureStep(page, "02-contract-definition-asset-form");

    await assetCreatePage.submit();
    report.assetMessage = await assetCreatePage.waitForSnackBarText(120_000);
    if (await assetCreatePage.isCreateButtonVisible()) {
      await assetCreatePage.submit();
      report.assetMessage = await assetCreatePage.waitForSnackBarText(60_000) ?? report.assetMessage;
    }
    await captureStep(page, "03-contract-definition-asset-created");

    await policyCreatePage.goto(portalBaseUrl);
    await policyCreatePage.expectReady();
    await policyCreatePage.fillPolicyId(policyId);
    await policyCreatePage.addParticipantIdConstraint(participantId);
    await captureStep(page, "04-contract-definition-policy-form");

    await policyCreatePage.submit();
    report.policyMessage = await policyCreatePage.waitForCreationSuccess();
    await policyCreatePage.expectPolicyListed(policyId);
    await captureStep(page, "05-contract-definition-policy-created");

    await contractDefinitionCreatePage.goto(portalBaseUrl);
    await contractDefinitionCreatePage.expectReady();
    await contractDefinitionCreatePage.fillContractDefinitionId(contractDefinitionId);
    await contractDefinitionCreatePage.selectAccessPolicy(policyId);
    await contractDefinitionCreatePage.selectContractPolicy(policyId);
    await contractDefinitionCreatePage.addAsset(assetId);
    await captureStep(page, "06-contract-definition-form-complete");

    await contractDefinitionCreatePage.submit();
    report.contractDefinitionMessage = await contractDefinitionCreatePage.waitForCreationSuccess();
    await contractDefinitionCreatePage.expectContractDefinitionListed(contractDefinitionId, {
      policyId,
      assetId,
    });
    await captureStep(page, "07-contract-definition-created");

    expect(report.assetMessage, "The prerequisite asset was not created successfully").toMatch(
      /asset created successfully/i,
    );
    expect(report.policyMessage, "The prerequisite policy was not created successfully").toMatch(
      /successfully created/i,
    );
    expect(
      report.contractDefinitionMessage,
      "No contract definition creation notification was detected",
    ).toMatch(/contract definition created/i);
  } finally {
    await attachJson("provider-contract-definition-report", report);
    upload.cleanup();
  }
});
