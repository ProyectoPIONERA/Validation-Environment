import { test, expect } from "../shared/fixtures/auth.fixture";
import { AssetCreatePage } from "../components/provider/asset-create.page";

type ChunkEvent = {
  url: string;
  status: number;
  bodySnippet?: string;
};

type ProviderFlowReport = {
  startedAt: string;
  baseUrl: string;
  assetId: string;
  filePath: string;
  expectedFileSizeBytes: number;
  expectedObjectKey: string;
  firstAttemptMessage?: string;
  secondAttemptMessage?: string;
  chunkEvents: ChunkEvent[];
  maxRetriesDetected: boolean;
};

test("03 provider setup: asset creation with file upload", async ({
  page,
  portalBaseUrl,
  portalObjectPrefix,
  uniqueSuffix,
  createUploadFile,
  ensureLoggedIn,
  captureStep,
  attachJson,
}) => {
  const upload = await createUploadFile();
  const assetId = `qa-ui-asset-${uniqueSuffix}`;
  const assetCreatePage = new AssetCreatePage(page);
  const report: ProviderFlowReport = {
    startedAt: new Date().toISOString(),
    baseUrl: portalBaseUrl,
    assetId,
    filePath: upload.path,
    expectedFileSizeBytes: upload.sizeBytes,
    expectedObjectKey: `${portalObjectPrefix}/${assetId}/${upload.path.split("/").pop()}`,
    chunkEvents: [],
    maxRetriesDetected: false,
  };

  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/s3assets/upload-chunk")) {
      return;
    }

    const event: ChunkEvent = {
      url,
      status: response.status(),
    };
    if (response.status() >= 400) {
      try {
        event.bodySnippet = (await response.text()).slice(0, 300);
      } catch {
        event.bodySnippet = "<unreadable response body>";
      }
    }
    report.chunkEvents.push(event);
  });

  try {
    await ensureLoggedIn();
    await captureStep(page, "01-provider-after-login");

    await assetCreatePage.goto(portalBaseUrl);
    await assetCreatePage.expectReady();
    await assetCreatePage.fillRequiredFields(assetId, `${portalObjectPrefix}/${assetId}`);
    await assetCreatePage.uploadFile(upload.path);
    await captureStep(page, "02-provider-form-complete");

    await assetCreatePage.submit();
    report.firstAttemptMessage = await assetCreatePage.waitForSnackBarText(120_000);

    if (await assetCreatePage.isCreateButtonVisible()) {
      await assetCreatePage.submit();
      report.secondAttemptMessage = await assetCreatePage.waitForSnackBarText(60_000);
    }

    await captureStep(page, "03-provider-created");

    const firstMessage = (report.firstAttemptMessage ?? "").toLowerCase();
    const secondMessage = (report.secondAttemptMessage ?? "").toLowerCase();
    report.maxRetriesDetected =
      firstMessage.includes("maximum retries") || secondMessage.includes("maximum retries");

    const uploadSucceeded =
      firstMessage.includes("asset created successfully") ||
      secondMessage.includes("asset created successfully");
    const hasChunkErrors = report.chunkEvents.some((event) => event.status >= 400);

    expect(report.firstAttemptMessage, "No notification was detected after creating the asset").toBeTruthy();
    expect(report.chunkEvents.length, "No upload-chunk responses were captured").toBeGreaterThan(0);
    expect(hasChunkErrors, "HTTP >= 400 responses were detected in upload-chunk").toBeFalsy();
    expect(report.maxRetriesDetected, "The UI reported 'Maximum retries reached'").toBeFalsy();
    expect(uploadSucceeded, "The success message 'Asset created successfully' was not detected").toBeTruthy();
  } finally {
    await attachJson("provider-setup-report", report);
    upload.cleanup();
  }
});
