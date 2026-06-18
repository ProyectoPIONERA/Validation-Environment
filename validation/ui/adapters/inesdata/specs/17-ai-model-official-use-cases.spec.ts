import { Locator, Page } from "@playwright/test";

import { test, expect } from "../../../shared/fixtures/dataspace.fixture";

import { KeycloakLoginPage } from "../../../shared/components/auth/keycloak-login.page";
import { ConnectorShellPage } from "../components/shell/connector-shell.page";
import { collectBrowserDiagnostics } from "../../../shared/utils/browser-diagnostics";
import { clickMarked, fillMarked, selectOptionMarked } from "../../../shared/utils/live-marker";
import { EVENTUAL_UI_RETRY_INTERVALS, waitForUiTransition } from "../../../shared/utils/waiting";

type OfficialModel = {
  assetId: string;
  name: string;
};

const OFFICIAL_USE_CASES_ENV = "UI_AI_MODEL_HUB_USE_CASES_DEMO";

const FLARES_5W1H_MODEL: OfficialModel = {
  assetId: "city-flares-5w1h-albert",
  name: "FLARES 5W1H ALBERT - PIONERA Use Case",
};

const FLARES_RELIABILITY_MODELS: OfficialModel[] = [
  {
    assetId: "city-flares-reliability-albert",
    name: "FLARES Reliability ALBERT - PIONERA Use Case",
  },
  {
    assetId: "company-flares-reliability-bert",
    name: "FLARES Reliability BERT - PIONERA Use Case",
  },
  {
    assetId: "city-flares-reliability-distilbert",
    name: "FLARES Reliability DistilBERT - PIONERA Use Case",
  },
];

const MOBILITY_ACTUAL_TRAVEL_TIME_MODELS: OfficialModel[] = [
  {
    assetId: "city-mobility-lightgbm-actual-travel-time",
    name: "Mobility LightGBM Actual Travel Time - PIONERA Use Case",
  },
  {
    assetId: "city-mobility-randomforest-actual-travel-time",
    name: "Mobility Random Forest Actual Travel Time - PIONERA Use Case",
  },
  {
    assetId: "company-mobility-catboost-actual-travel-time",
    name: "Mobility CatBoost Actual Travel Time - PIONERA Use Case",
  },
];

const FLARES_5W1H_METRIC_MODELS: OfficialModel[] = [
  {
    assetId: "city-flares-5w1h-albert-metrics",
    name: "FLARES 5W1H ALBERT Metrics - PIONERA Use Case",
  },
  {
    assetId: "company-flares-5w1h-bert-metrics",
    name: "FLARES 5W1H BERT Metrics - PIONERA Use Case",
  },
  {
    assetId: "city-flares-5w1h-distilbert-metrics",
    name: "FLARES 5W1H DistilBERT Metrics - PIONERA Use Case",
  },
];

const MOBILITY_PREVIOUS_DELAY_MODELS: OfficialModel[] = [
  {
    assetId: "company-mobility-catboost-previous-delay",
    name: "Mobility CatBoost Previous Delay - PIONERA Use Case",
  },
  {
    assetId: "company-mobility-lightgbm-previous-delay",
    name: "Mobility LightGBM Previous Delay - PIONERA Use Case",
  },
  {
    assetId: "company-mobility-randomforest-previous-delay",
    name: "Mobility Random Forest Previous Delay - PIONERA Use Case",
  },
];

const FLARES_5W1H_PAYLOAD = [
  {
    Id: 840,
    Text: "El comité de medicamentos humanos espera concluir el análisis en marzo.",
  },
];

const FLARES_5W1H_INPUT_COLUMNS = ["Id", "Text"];

const FLARES_RELIABILITY_INPUT_COLUMNS = [
  "Id",
  "Text",
  "Tag_Start",
  "Tag_End",
  "5W1H_Label",
  "Tag_Text",
];

const MOBILITY_PREVIOUS_DELAY_INPUT_COLUMNS = [
  "trip_id",
  "from_stop_id",
  "to_stop_id",
  "route_id",
  "scheduled_travel_time",
  "shape_distance",
  "is_peak",
  "hour_sin",
  "hour_cos",
  "weekday_sin",
  "weekday_cos",
];

const MOBILITY_ACTUAL_TRAVEL_TIME_INPUT_COLUMNS = [
  "trip_id",
  "from_stop_id",
  "to_stop_id",
  "route_id",
  "scheduled_travel_time",
  "shape_distance",
  "is_peak",
  "hour_sin",
  "hour_cos",
  "weekday_sin",
  "weekday_cos",
  "previous_delay_ratio",
  "previous_delay_delta",
];

test.skip(
  process.env[OFFICIAL_USE_CASES_ENV] === "0",
  `Set ${OFFICIAL_USE_CASES_ENV}=1 to force the official AI Model Hub use-case UI suite, or leave it enabled through use-cases model-server configuration.`,
);

function route(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function loginConnector(
  page: Page,
  connector: { portalBaseUrl: string; username: string; password: string },
): Promise<void> {
  const loginPage = new KeycloakLoginPage(page, {
    portalUser: connector.username,
    portalPassword: connector.password,
    skipLogin: false,
  });
  const shellPage = new ConnectorShellPage(page);
  await loginPage.open(connector.portalBaseUrl);
  await loginPage.loginIfNeeded();
  await shellPage.expectReady();
}

async function openConnectorModule(
  page: Page,
  connector: { portalBaseUrl: string },
  path: string,
  heading: RegExp,
): Promise<void> {
  await page.goto(route(connector.portalBaseUrl, path), { waitUntil: "domcontentloaded" });
  const shellPage = new ConnectorShellPage(page);
  await shellPage.assertNoGateway403(`${path} page`);
  await shellPage.assertNoServerErrorBanner(`${path} page`);
  await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible({ timeout: 30_000 });
}

function browserSearchInput(page: Page): Locator {
  return page.locator(".search-field input, input[placeholder*='regression'], input[placeholder*='CatBoost']").first();
}

function browserCard(page: Page, model: OfficialModel): Locator {
  return page.locator("mat-card.model-card").filter({ hasText: model.assetId }).filter({ hasText: model.name }).first();
}

function benchmarkModelCard(page: Page, model: OfficialModel): Locator {
  return page.locator(".model-item.selectable").filter({ hasText: model.name }).first();
}

function benchmarkDatasetCard(page: Page, datasetName: string): Locator {
  return page.locator(".dataspace-dataset-card").filter({ hasText: datasetName }).first();
}

function datasetRowsValue(page: Page): Locator {
  return page.locator(".stat-card").filter({ hasText: "Dataset rows" }).locator(".stat-value").first();
}

async function selectBenchmarkModels(page: Page, searchTerm: string, models: OfficialModel[]): Promise<void> {
  const searchInput = page.locator("input.search-input").first();
  await expect(searchInput).toBeVisible({ timeout: 30_000 });
  await fillMarked(searchInput, searchTerm);
  await waitForUiTransition(page);

  for (const model of models) {
    const card = benchmarkModelCard(page, model);
    await expect(card, `Official model ${model.assetId} must be visible in benchmarking`).toBeVisible({
      timeout: 60_000,
    });
    const statusText = ((await card.locator(".model-status").first().textContent().catch(() => "")) || "").trim();
    if (!/selected/i.test(statusText)) {
      await clickMarked(card, { force: true });
      await waitForUiTransition(page);
    }
    await expect(card.locator(".model-status").filter({ hasText: /Selected/i }).first()).toBeVisible({
      timeout: 15_000,
    });
  }
}

async function selectOfficialBenchmarkDataset(page: Page, searchTerm: string, datasetName: string): Promise<void> {
  await expect(async () => {
    const searchInput = page.locator(".dataset-search-bar input.search-input").first();
    await expect(searchInput).toBeVisible({ timeout: 15_000 });
    await fillMarked(searchInput, searchTerm);
    await waitForUiTransition(page);
    await expect(benchmarkDatasetCard(page, datasetName)).toBeVisible({ timeout: 20_000 });
  }).toPass({
    timeout: 120_000,
    intervals: EVENTUAL_UI_RETRY_INTERVALS,
  });

  await clickMarked(benchmarkDatasetCard(page, datasetName), { force: true });
  await waitForUiTransition(page);
}

async function loadSelectedDataset(
  page: Page,
  inputColumns: string[],
  labelColumn: string,
): Promise<void> {
  await fillMarked(page.locator(".dataset-mapping-textarea").first(), inputColumns.join(", "));
  await fillMarked(page.locator(".dataset-mapping-input").first(), labelColumn);
  await clickMarked(page.getByRole("button", { name: /^Load Dataset$/i }).first(), { force: true });

  await expect.poll(
    async () => {
      const rawValue = await datasetRowsValue(page).textContent().catch(() => "0");
      return Number((rawValue || "0").replace(/[^\d]/g, ""));
    },
    {
      message: "The selected official benchmark dataset must load at least one row.",
      timeout: 180_000,
      intervals: EVENTUAL_UI_RETRY_INTERVALS,
    },
  ).toBeGreaterThan(0);
}

async function runSampleRows(page: Page): Promise<void> {
  await clickMarked(page.getByRole("button", { name: /^Test Rows$/i }).first(), { force: true });
  await expect(page.getByText(/Row test complete\.\s*Success:\s*\d+,\s*partial:\s*0,\s*errors:\s*0/i).first()).toBeVisible({
    timeout: 180_000,
  });
}

async function runFullBenchmarkAndOpenObserverEvidence(
  page: Page,
  models: OfficialModel[],
  screenshotPrefix: string,
  captureStep: (page: Page, name: string, options?: { fullPage?: boolean }) => Promise<string>,
): Promise<string> {
  await clickMarked(page.getByRole("button", { name: /^Run Benchmark$/i }).first(), { force: true });
  await expect(page.getByText(/Benchmark completed/i).first()).toBeVisible({ timeout: 12 * 60 * 1000 });
  await expect(page.getByRole("heading", { name: /Ranking Results/i }).first()).toBeVisible({ timeout: 60_000 });
  for (const model of models) {
    await expect(page.getByText(model.name).first()).toBeVisible({ timeout: 30_000 });
  }
  await captureStep(page, `${screenshotPrefix}-ranking`);

  await clickMarked(page.getByRole("button", { name: /Benchmark Evidence/i }).first(), { force: true });
  await expect(page).toHaveURL(/\/ai-model-observer\/benchmarks\/benchmark-/i, { timeout: 30_000 });
  const benchmarkRunId = extractRouteTail(page.url());
  await expectObserverEvents(page, [/^BENCHMARK_STARTED$/i, /^MODEL_EXECUTION_COMPLETED$/i, /^BENCHMARK_COMPLETED$/i]);
  await captureStep(page, `${screenshotPrefix}-benchmark-observer`);
  return benchmarkRunId;
}

async function expectObserverEvents(page: Page, expectedEvents: RegExp[]): Promise<void> {
  await expect(page.getByRole("heading", { name: /Asset timeline|Benchmark evidence|Participant summary/i }).first()).toBeVisible({
    timeout: 30_000,
  });

  for (const expectedEvent of expectedEvents) {
    await expect(page.getByRole("heading", { name: expectedEvent }).first()).toBeVisible({
      timeout: 60_000,
    });
  }
}

function extractRouteTail(url: string): string {
  const pathname = new URL(url).pathname.replace(/\/+$/, "");
  return decodeURIComponent(pathname.split("/").pop() || "");
}

test("17.1 AI Model Browser: official PIONERA use-case assets are discoverable with DAIMO metadata", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(5 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-browser", /AI Model Browser/i);

    const expectedModels = [
      FLARES_5W1H_MODEL,
      FLARES_RELIABILITY_MODELS[1],
      MOBILITY_ACTUAL_TRAVEL_TIME_MODELS[0],
    ];

    await expect(async () => {
      await fillMarked(browserSearchInput(page), "PIONERA Use Case");
      await waitForUiTransition(page);
      for (const model of expectedModels) {
        await expect(browserCard(page, model), `Official browser card ${model.assetId} must exist`).toBeVisible({
          timeout: 20_000,
        });
      }
    }).toPass({
      timeout: 120_000,
      intervals: EVENTUAL_UI_RETRY_INTERVALS,
    });

    await expect(browserCard(page, FLARES_5W1H_MODEL).getByText(/Natural Language Processing/i).first()).toBeVisible();
    await expect(browserCard(page, FLARES_5W1H_MODEL).getByText(/token-classification/i).first()).toBeVisible();
    await expect(browserCard(page, FLARES_5W1H_MODEL).getByText(/Transformers/i).first()).toBeVisible();
    await expect(browserCard(page, MOBILITY_ACTUAL_TRAVEL_TIME_MODELS[0]).getByText(/Tabular/i).first()).toBeVisible();
    await expect(browserCard(page, MOBILITY_ACTUAL_TRAVEL_TIME_MODELS[0]).getByText(/regression/i).first()).toBeVisible();
    await captureStep(page, "17-01-official-use-cases-browser-catalog");

    await clickMarked(browserCard(page, FLARES_5W1H_MODEL).getByRole("button", { name: /View details/i }).first(), {
      force: true,
    });
    await expect(page.locator("body")).toContainText(/Asset information|Contract offer|JSON-LD/i, { timeout: 30_000 });
    await captureStep(page, "17-02-official-use-cases-browser-detail");

    await attachJson("official-ai-model-browser-use-case-assertions", {
      module: "AI Model Browser",
      expectedAssets: expectedModels,
      validatedMetadata: ["taskCategory", "taskType", "subtask", "libraryName", "source/local-or-federated"],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub steps 8-10 and AIModelHub-Use-Cases model catalog",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-browser-diagnostics", diagnostics);
  }
});

test("17.2 AI Model Execution: official FLARES 5W1H model exposes input schema and executes", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(6 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-execution", /AI Execution/i);

    const assetSelect = page.locator("#assetSelect").first();
    await expect(assetSelect).toBeVisible({ timeout: 60_000 });
    await selectOptionMarked(assetSelect, FLARES_5W1H_MODEL.assetId);
    await waitForUiTransition(page);

    await expect(page.getByRole("heading", { name: FLARES_5W1H_MODEL.name }).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Change Model/i }).first()).toBeVisible();
    await expect(page.locator(".input-schema-section").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Detected DAIMO input schema/i).first()).toBeVisible();
    await expect(page.getByText(/2 fields/i).first()).toBeVisible();
    await expect(page.locator(".form-section .form-label").filter({ hasText: /^Id\b/i }).first()).toBeVisible();
    await expect(page.locator(".form-section .form-label").filter({ hasText: /^Text\b/i }).first()).toBeVisible();
    await captureStep(page, "17-03-official-use-cases-execution-schema");

    await clickMarked(page.getByRole("button", { name: /JSON Payload/i }).first(), { force: true });
    await fillMarked(page.locator("#inputJson").first(), JSON.stringify(FLARES_5W1H_PAYLOAD, null, 2));
    await clickMarked(page.getByRole("button", { name: /Execute Model/i }).first(), { force: true });

    await expect(page.getByText(/Execution Result/i).first()).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText(/^SUCCESS$/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Status Code:\s*200/i).first()).toBeVisible({ timeout: 30_000 });
    await captureStep(page, "17-04-official-use-cases-execution-result");

    await clickMarked(page.getByRole("button", { name: /View Observer Timeline/i }).first(), { force: true });
    await expect(page).toHaveURL(/\/ai-model-observer\/assets\/city-flares-5w1h-albert/i, { timeout: 30_000 });
    await expectObserverEvents(page, [/^MODEL_EXECUTION_REQUESTED$/i, /^MODEL_EXECUTION_COMPLETED$/i]);
    await captureStep(page, "17-05-official-use-cases-execution-observer");

    await attachJson("official-ai-model-execution-use-case-assertions", {
      module: "AI Model Execution",
      model: FLARES_5W1H_MODEL,
      payload: FLARES_5W1H_PAYLOAD,
      validatedFeatures: ["DAIMO input schema detection", "Generated form", "JSON payload mode", "HTTP 200 execution", "Observer asset timeline"],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub seed_use_case_http_data_assets",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-execution-diagnostics", diagnostics);
  }
});

test("17.3 AI Model Benchmarking and Observer: official FLARES Reliability comparison produces evidence", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(15 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-benchmarking", /Model Benchmarking/i);

    await selectBenchmarkModels(page, "FLARES Reliability", FLARES_RELIABILITY_MODELS);
    await expect(page.getByText(/3 selected/i).first()).toBeVisible({ timeout: 15_000 });
    await selectOfficialBenchmarkDataset(page, "Reliability", "FLARES Reliability Test Dataset");
    await loadSelectedDataset(page, FLARES_RELIABILITY_INPUT_COLUMNS, "Reliability_Label");
    await captureStep(page, "17-06-official-use-cases-flares-dataset-loaded");

    await runSampleRows(page);
    await captureStep(page, "17-07-official-use-cases-flares-row-test");

    await clickMarked(page.getByRole("button", { name: /^Run Benchmark$/i }).first(), { force: true });
    await expect(page.getByText(/Benchmark completed/i).first()).toBeVisible({ timeout: 12 * 60 * 1000 });
    await expect(page.getByRole("heading", { name: /Ranking Results/i }).first()).toBeVisible({ timeout: 60_000 });
    for (const model of FLARES_RELIABILITY_MODELS) {
      await expect(page.getByText(model.name).first()).toBeVisible({ timeout: 30_000 });
    }
    await captureStep(page, "17-08-official-use-cases-flares-ranking");

    await clickMarked(page.getByRole("button", { name: /Benchmark Evidence/i }).first(), { force: true });
    await expect(page).toHaveURL(/\/ai-model-observer\/benchmarks\/benchmark-/i, { timeout: 30_000 });
    const benchmarkRunId = extractRouteTail(page.url());
    await expectObserverEvents(page, [/^BENCHMARK_STARTED$/i, /^MODEL_EXECUTION_COMPLETED$/i, /^BENCHMARK_COMPLETED$/i]);
    await captureStep(page, "17-09-official-use-cases-flares-benchmark-observer");

    const participantSummaryUrl = route(
      dataspaceRuntime.provider.portalBaseUrl,
      `/ai-model-observer/participants/${encodeURIComponent(dataspaceRuntime.provider.connectorName)}`,
    );
    await expect(async () => {
      await page.goto(participantSummaryUrl, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Participant summary/i }).first()).toBeVisible({
        timeout: 20_000,
      });
      await expect(page.getByText(dataspaceRuntime.provider.connectorName).first()).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText(benchmarkRunId).first()).toBeVisible({ timeout: 20_000 });
    }).toPass({
      timeout: 120_000,
      intervals: EVENTUAL_UI_RETRY_INTERVALS,
    });
    await captureStep(page, "17-10-official-use-cases-flares-participant-summary");

    await attachJson("official-ai-model-benchmarking-flares-use-case-assertions", {
      modules: ["AI Model Benchmarking", "AI Model Observer"],
      models: FLARES_RELIABILITY_MODELS,
      dataset: {
        assetId: "company-flares-reliability-test",
        name: "FLARES Reliability Test Dataset",
        inputColumns: FLARES_RELIABILITY_INPUT_COLUMNS,
        labelColumn: "Reliability_Label",
      },
      benchmarkRunId,
      validatedFeatures: [
        "compatible model pool",
        "agreed federated dataset loading",
        "sample-row validation",
        "full benchmark ranking",
        "benchmark evidence timeline",
        "participant summary",
      ],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub steps 9-10 and AIModelHub-Use-Cases FLARES endpoints",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-benchmarking-flares-diagnostics", diagnostics);
  }
});

test("17.4 AI Model Benchmarking and Observer: official Mobility Actual Travel Time comparison produces evidence", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(15 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-benchmarking", /Model Benchmarking/i);

    await selectBenchmarkModels(page, "Actual Travel Time", MOBILITY_ACTUAL_TRAVEL_TIME_MODELS);
    await expect(page.getByText(/3 selected/i).first()).toBeVisible({ timeout: 15_000 });
    await fillMarked(page.locator("input.search-input").first(), "");
    await waitForUiTransition(page);
    const modelPoolText = await page.locator(".model-list").first().innerText();
    expect(modelPoolText).toContain("Actual Travel Time");
    expect(modelPoolText).not.toMatch(/Mobility .* Previous Delay - PIONERA Use Case|Mobility .* Delay - PIONERA Use Case/);
    await captureStep(page, "17-11-official-use-cases-mobility-compatible-pool");

    await selectOfficialBenchmarkDataset(page, "Mobility Segments", "Mobility Segments Test Dataset");
    await loadSelectedDataset(page, MOBILITY_ACTUAL_TRAVEL_TIME_INPUT_COLUMNS, "actual_travel_time");
    await captureStep(page, "17-12-official-use-cases-mobility-dataset-loaded");

    await runSampleRows(page);
    await captureStep(page, "17-13-official-use-cases-mobility-row-test");

    await clickMarked(page.getByRole("button", { name: /^Run Benchmark$/i }).first(), { force: true });
    await expect(page.getByText(/Benchmark completed/i).first()).toBeVisible({ timeout: 12 * 60 * 1000 });
    await expect(page.getByRole("heading", { name: /Ranking Results/i }).first()).toBeVisible({ timeout: 60_000 });
    for (const model of MOBILITY_ACTUAL_TRAVEL_TIME_MODELS) {
      await expect(page.getByText(model.name).first()).toBeVisible({ timeout: 30_000 });
    }
    await captureStep(page, "17-14-official-use-cases-mobility-ranking");

    await clickMarked(page.getByRole("button", { name: /Benchmark Evidence/i }).first(), { force: true });
    await expect(page).toHaveURL(/\/ai-model-observer\/benchmarks\/benchmark-/i, { timeout: 30_000 });
    const benchmarkRunId = extractRouteTail(page.url());
    await expectObserverEvents(page, [/^BENCHMARK_STARTED$/i, /^MODEL_EXECUTION_COMPLETED$/i, /^BENCHMARK_COMPLETED$/i]);
    await captureStep(page, "17-15-official-use-cases-mobility-benchmark-observer");

    await attachJson("official-ai-model-benchmarking-mobility-use-case-assertions", {
      modules: ["AI Model Benchmarking", "AI Model Observer"],
      models: MOBILITY_ACTUAL_TRAVEL_TIME_MODELS,
      dataset: {
        assetId: "company-mobility-segments-test",
        name: "Mobility Segments Test Dataset",
        inputColumns: MOBILITY_ACTUAL_TRAVEL_TIME_INPUT_COLUMNS,
        labelColumn: "actual_travel_time",
      },
      benchmarkRunId,
      validatedFeatures: [
        "local-first compatible model filtering",
        "federated compatible model selection",
        "official Mobility dataset loading",
        "sample-row validation against real model-server endpoints",
        "full Mobility benchmark ranking",
        "benchmark evidence timeline",
      ],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub use_case_input_columns_json and use_case_label_column",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-benchmarking-mobility-diagnostics", diagnostics);
  }
});

test("17.5 AI Model Benchmarking and Observer: official FLARES 5W1H Metrics comparison produces evidence", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(15 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-benchmarking", /Model Benchmarking/i);

    await selectBenchmarkModels(page, "5W1H Metrics", FLARES_5W1H_METRIC_MODELS);
    await expect(page.getByText(/3 selected/i).first()).toBeVisible({ timeout: 15_000 });
    await selectOfficialBenchmarkDataset(page, "5W1H", "FLARES 5W1H Test Dataset");
    await loadSelectedDataset(page, FLARES_5W1H_INPUT_COLUMNS, "Tags");
    await captureStep(page, "17-16-official-use-cases-5w1h-metrics-dataset-loaded");

    await runSampleRows(page);
    await captureStep(page, "17-17-official-use-cases-5w1h-metrics-row-test");

    const benchmarkRunId = await runFullBenchmarkAndOpenObserverEvidence(
      page,
      FLARES_5W1H_METRIC_MODELS,
      "17-18-official-use-cases-5w1h-metrics",
      captureStep,
    );

    await attachJson("official-ai-model-benchmarking-5w1h-metrics-use-case-assertions", {
      modules: ["AI Model Benchmarking", "AI Model Observer"],
      models: FLARES_5W1H_METRIC_MODELS,
      dataset: {
        assetId: "company-flares-5w1h-test",
        name: "FLARES 5W1H Test Dataset",
        inputColumns: FLARES_5W1H_INPUT_COLUMNS,
        labelColumn: "Tags",
      },
      benchmarkRunId,
      validatedFeatures: [
        "official FLARES 5W1H metric model selection",
        "official FLARES 5W1H dataset loading",
        "sample-row validation against metric endpoints",
        "full FLARES 5W1H metric benchmark ranking",
        "benchmark evidence timeline",
      ],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub flares_metric_input_columns_json and flares_metric_label_column",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-benchmarking-5w1h-metrics-diagnostics", diagnostics);
  }
});

test("17.6 AI Model Benchmarking and Observer: official Mobility Previous Delay comparison produces evidence", async ({
  page,
  dataspaceRuntime,
  captureStep,
  attachJson,
}) => {
  test.skip(dataspaceRuntime.adapter !== "inesdata", "Official use-case validation currently targets INESData Level 6.");
  test.setTimeout(15 * 60 * 1000);

  const browserDiagnostics = collectBrowserDiagnostics(page);
  try {
    await loginConnector(page, dataspaceRuntime.provider);
    await openConnectorModule(page, dataspaceRuntime.provider, "/ai-model-benchmarking", /Model Benchmarking/i);

    await selectBenchmarkModels(page, "Previous Delay", MOBILITY_PREVIOUS_DELAY_MODELS);
    await expect(page.getByText(/3 selected/i).first()).toBeVisible({ timeout: 15_000 });
    await fillMarked(page.locator("input.search-input").first(), "");
    await waitForUiTransition(page);
    const modelPoolText = await page.locator(".model-list").first().innerText();
    expect(modelPoolText).toContain("Previous Delay");
    expect(modelPoolText).not.toMatch(
      /Mobility .* Actual Travel Time - PIONERA Use Case|Mobility (CatBoost|LightGBM|Random Forest) Delay - PIONERA Use Case/,
    );
    await captureStep(page, "17-19-official-use-cases-previous-delay-compatible-pool");

    await selectOfficialBenchmarkDataset(page, "Mobility Segments", "Mobility Segments Test Dataset");
    await loadSelectedDataset(page, MOBILITY_PREVIOUS_DELAY_INPUT_COLUMNS, "previous_delay");
    await captureStep(page, "17-20-official-use-cases-previous-delay-dataset-loaded");

    await runSampleRows(page);
    await captureStep(page, "17-21-official-use-cases-previous-delay-row-test");

    const benchmarkRunId = await runFullBenchmarkAndOpenObserverEvidence(
      page,
      MOBILITY_PREVIOUS_DELAY_MODELS,
      "17-22-official-use-cases-previous-delay",
      captureStep,
    );

    await attachJson("official-ai-model-benchmarking-previous-delay-use-case-assertions", {
      modules: ["AI Model Benchmarking", "AI Model Observer"],
      models: MOBILITY_PREVIOUS_DELAY_MODELS,
      dataset: {
        assetId: "company-mobility-segments-test",
        name: "Mobility Segments Test Dataset",
        inputColumns: MOBILITY_PREVIOUS_DELAY_INPUT_COLUMNS,
        labelColumn: "previous_delay",
      },
      benchmarkRunId,
      validatedFeatures: [
        "official Mobility Previous Delay compatible model filtering",
        "official Mobility dataset loading",
        "sample-row validation against real model-server endpoints",
        "full Mobility Previous Delay benchmark ranking",
        "benchmark evidence timeline",
      ],
      sourceOfTruth: "ProyectoPIONERA/AIModelHub use_case_input_columns_json and use_case_label_column",
    });
  } finally {
    const diagnostics = browserDiagnostics.snapshot();
    browserDiagnostics.dispose();
    await attachJson("official-ai-model-benchmarking-previous-delay-diagnostics", diagnostics);
  }
});
