import type { APIRequestContext } from "@playwright/test";

import type { DataspacePortalRuntime } from "./dataspace-runtime";

type BootstrapArtifacts = {
  assetId: string;
  policyId: string;
  contractDefinitionId: string;
};

type ConsumerNegotiationArtifacts = {
  negotiationId: string;
  agreementId: string;
  assetId: string;
  state?: string;
};

type ConsumerTransferArtifacts = {
  transferId: string;
  finalState: string;
  transferType: string;
  assetId: string;
};

async function ensureOk(response: { ok(): boolean; status(): number; text(): Promise<string> }, action: string) {
  if (response.ok()) {
    return;
  }

  const body = await response.text();
  throw new Error(`${action} failed with HTTP ${response.status()}: ${body.slice(0, 500)}`);
}

async function issueUserToken(request: APIRequestContext, runtime: DataspacePortalRuntime): Promise<string> {
  const response = await request.post(
    `${runtime.keycloakUrl}/realms/${runtime.dataspace}/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: runtime.keycloakClientId,
        username: runtime.provider.username,
        password: runtime.provider.password,
        scope: "openid profile email",
      },
    },
  );
  await ensureOk(response, "Provider token request");
  const body = await response.json();
  const token = body?.access_token;
  if (!token) {
    throw new Error("Provider token response does not contain access_token");
  }
  return token;
}

async function issueConsumerToken(request: APIRequestContext, runtime: DataspacePortalRuntime): Promise<string> {
  const response = await request.post(
    `${runtime.keycloakUrl}/realms/${runtime.dataspace}/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: runtime.keycloakClientId,
        username: runtime.consumer.username,
        password: runtime.consumer.password,
        scope: "openid profile email",
      },
    },
  );
  await ensureOk(response, "Consumer token request");
  const body = await response.json();
  const token = body?.access_token;
  if (!token) {
    throw new Error("Consumer token response does not contain access_token");
  }
  return token;
}

async function createPolicy(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  providerToken: string,
  policyId: string,
): Promise<void> {
  const response = await request.post(`${runtime.provider.managementBaseUrl}/policydefinitions`, {
    headers: {
      Authorization: `Bearer ${providerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
        odrl: "http://www.w3.org/ns/odrl/2/",
      },
      "@id": policyId,
      policy: {
        "@context": "http://www.w3.org/ns/odrl.jsonld",
        "@type": "Set",
        permission: [],
        prohibition: [],
        obligation: [],
      },
    },
  });
  await ensureOk(response, "Create policy");
}

async function createAsset(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  providerToken: string,
  assetId: string,
  sourceObjectName = "todos",
): Promise<void> {
  const response = await request.post(`${runtime.provider.managementBaseUrl}/assets`, {
    headers: {
      Authorization: `Bearer ${providerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
        dct: "http://purl.org/dc/terms/",
        dcat: "http://www.w3.org/ns/dcat#",
      },
      "@id": assetId,
      "@type": "Asset",
      properties: {
        name: `UI Negotiation Asset ${assetId}`,
        version: "1.0.0",
        shortDescription: "Asset bootstrap for UI negotiation validation",
        assetType: "dataset",
        "dct:description": "Asset bootstrap for UI negotiation validation",
        "dcat:keyword": ["validation", "ui", "negotiation"],
      },
      dataAddress: {
        type: "HttpData",
        baseUrl: "https://jsonplaceholder.typicode.com/todos",
        name: sourceObjectName,
      },
    },
  });
  await ensureOk(response, "Create asset");
}

async function createContractDefinition(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  providerToken: string,
  contractDefinitionId: string,
  policyId: string,
  assetId: string,
): Promise<void> {
  const response = await request.post(`${runtime.provider.managementBaseUrl}/contractdefinitions`, {
    headers: {
      Authorization: `Bearer ${providerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
      },
      "@id": contractDefinitionId,
      accessPolicyId: policyId,
      contractPolicyId: policyId,
      assetsSelector: [
        {
          operandLeft: "https://w3id.org/edc/v0.0.1/ns/id",
          operator: "=",
          operandRight: assetId,
        },
      ],
    },
  });
  await ensureOk(response, "Create contract definition");
}

export async function bootstrapProviderContractArtifacts(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  assetId: string,
  suffix: string,
): Promise<BootstrapArtifacts> {
  const providerToken = await issueUserToken(request, runtime);
  const policyId = `policy-ui-${suffix}`;
  const contractDefinitionId = `contract-ui-${suffix}`;

  await createPolicy(request, runtime, providerToken, policyId);
  await createContractDefinition(
    request,
    runtime,
    providerToken,
    contractDefinitionId,
    policyId,
    assetId,
  );

  return {
    assetId,
    policyId,
    contractDefinitionId,
  };
}

export async function bootstrapProviderNegotiationArtifacts(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  assetId: string,
  suffix: string,
  sourceObjectName?: string,
): Promise<BootstrapArtifacts> {
  const providerToken = await issueUserToken(request, runtime);
  const policyId = `policy-ui-${suffix}`;
  const contractDefinitionId = `contract-ui-${suffix}`;

  await createAsset(request, runtime, providerToken, assetId, sourceObjectName);
  await createPolicy(request, runtime, providerToken, policyId);
  await createContractDefinition(
    request,
    runtime,
    providerToken,
    contractDefinitionId,
    policyId,
    assetId,
  );

  return {
    assetId,
    policyId,
    contractDefinitionId,
  };
}

export async function fetchConsumerCatalogResponse(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  counterPartyAddress: string,
  counterPartyId?: string,
): Promise<unknown> {
  const consumerToken = await issueConsumerToken(request, runtime);
  const response = await request.post(`${runtime.consumer.managementBaseUrl}/catalog/request`, {
    headers: {
      Authorization: `Bearer ${consumerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
      },
      "@type": "CatalogRequest",
      counterPartyAddress,
      counterPartyId,
      protocol: "dataspace-protocol-http",
      querySpec: {
        offset: 0,
        limit: 100,
        filterExpression: [],
      },
    },
  });
  await ensureOk(response, "Consumer catalog request");
  return await response.json();
}

function findCatalogDataset(catalogResponse: any, assetId: string): any {
  const datasets = Array.isArray(catalogResponse?.["dcat:dataset"])
    ? catalogResponse["dcat:dataset"]
    : Array.isArray(catalogResponse?.datasets)
      ? catalogResponse.datasets
      : [];
  return datasets.find((dataset: any) => dataset?.["@id"] === assetId || dataset?.id === assetId);
}

function catalogDatasetOffer(dataset: any): any {
  const offer = dataset?.["odrl:hasPolicy"] || dataset?.policy;
  return Array.isArray(offer) ? offer[0] : offer;
}

function resolveCatalogParticipantId(catalogResponse: any, fallback: string): string {
  const participant = catalogResponse?.["https://w3id.org/dspace/v0.8/participantId"];
  if (Array.isArray(participant) && participant.length > 0) {
    const first = participant[0];
    if (typeof first?.["@value"] === "string" && first["@value"].trim().length > 0) {
      return first["@value"].trim();
    }
  }
  return fallback;
}

function buildNegotiationPolicy(catalogResponse: any, dataset: any, fallbackParticipantId: string) {
  const offer = catalogDatasetOffer(dataset);
  if (!offer?.["@id"]) {
    throw new Error(`Catalog dataset '${dataset?.["@id"] || "unknown"}' does not expose an offer policy`);
  }

  return {
    "@context": "http://www.w3.org/ns/odrl.jsonld",
    "@type": offer["@type"] || "odrl:Offer",
    "@id": offer["@id"],
    assigner: resolveCatalogParticipantId(catalogResponse, fallbackParticipantId),
    target: dataset?.["@id"] || dataset?.id,
    permission: offer["odrl:permission"] || offer.permission || [],
    prohibition: offer["odrl:prohibition"] || offer.prohibition || [],
    obligation: offer["odrl:obligation"] || offer.obligation || [],
  };
}

async function fetchConsumerCatalogDatasetWithOffer(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  assetId: string,
  counterPartyAddress: string,
  counterPartyId: string,
  timeoutMs = 120_000,
): Promise<{ catalogResponse: any; dataset: any }> {
  const deadline = Date.now() + timeoutMs;
  let lastDatasetFound = false;

  while (Date.now() < deadline) {
    const catalogResponse = await fetchConsumerCatalogResponse(
      request,
      runtime,
      counterPartyAddress,
      counterPartyId,
    );
    const dataset = findCatalogDataset(catalogResponse, assetId);
    if (dataset) {
      lastDatasetFound = true;
      if (catalogDatasetOffer(dataset)?.["@id"]) {
        return { catalogResponse, dataset };
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(
    `Catalog dataset '${assetId}' did not expose an offer policy in time. ` +
      `Last catalog state: ${lastDatasetFound ? "dataset without offer policy" : "dataset not found"}`,
  );
}

function negotiationTimeoutMs(): number {
  const configured = Number.parseInt(process.env.UI_EDC_NEGOTIATION_TIMEOUT_MS || "", 10);
  if (Number.isFinite(configured) && configured > 0) {
    return configured;
  }
  return 180_000;
}

function negotiationState(entry: any): string {
  return String(entry?.state || entry?.["edc:state"] || "").trim().toUpperCase();
}

function negotiationAgreementId(entry: any): string {
  return String(entry?.contractAgreementId || entry?.["edc:contractAgreementId"] || "").trim();
}

function negotiationErrorDetail(entry: any): string {
  return String(entry?.errorDetail || entry?.["edc:errorDetail"] || entry?.errorMessage || "").trim();
}

function negotiationMatches(entry: any, negotiationId: string): boolean {
  return entry?.["@id"] === negotiationId || entry?.id === negotiationId;
}

async function lookupNegotiationById(
  request: APIRequestContext,
  managementBaseUrl: string,
  consumerToken: string,
  negotiationId: string,
): Promise<any | undefined> {
  const response = await request.get(`${managementBaseUrl}/contractnegotiations/${negotiationId}`, {
    headers: {
      Authorization: `Bearer ${consumerToken}`,
    },
  });

  if (response.ok()) {
    return await response.json();
  }

  if ([404, 405].includes(response.status())) {
    return undefined;
  }

  await ensureOk(response, "Consumer negotiation direct lookup");
  return undefined;
}

async function lookupNegotiationFromList(
  request: APIRequestContext,
  managementBaseUrl: string,
  consumerToken: string,
  negotiationId: string,
): Promise<any | undefined> {
  const pageSize = 100;
  for (let offset = 0; offset <= 500; offset += pageSize) {
    const lookupResponse = await request.post(`${managementBaseUrl}/contractnegotiations/request`, {
      headers: {
        Authorization: `Bearer ${consumerToken}`,
        "Content-Type": "application/json",
      },
      data: {
        "@context": {
          "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
        },
        offset,
        limit: pageSize,
      },
    });
    await ensureOk(lookupResponse, "Consumer negotiation lookup");
    const lookupBody = await lookupResponse.json();
    const negotiations = Array.isArray(lookupBody) ? lookupBody : [];
    const negotiation = negotiations.find((entry: any) => negotiationMatches(entry, negotiationId));
    if (negotiation) {
      return negotiation;
    }
    if (negotiations.length < pageSize) {
      break;
    }
  }
  return undefined;
}

async function lookupNegotiation(
  request: APIRequestContext,
  managementBaseUrl: string,
  consumerToken: string,
  negotiationId: string,
): Promise<any | undefined> {
  return (
    (await lookupNegotiationById(request, managementBaseUrl, consumerToken, negotiationId)) ||
    (await lookupNegotiationFromList(request, managementBaseUrl, consumerToken, negotiationId))
  );
}

export async function bootstrapConsumerNegotiation(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  assetId: string,
  counterPartyAddress: string,
  counterPartyId: string,
): Promise<ConsumerNegotiationArtifacts> {
  const consumerToken = await issueConsumerToken(request, runtime);
  const { catalogResponse, dataset } = await fetchConsumerCatalogDatasetWithOffer(
    request,
    runtime,
    assetId,
    counterPartyAddress,
    counterPartyId,
  );

  const response = await request.post(`${runtime.consumer.managementBaseUrl}/contractnegotiations`, {
    headers: {
      Authorization: `Bearer ${consumerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
      },
      "@type": "ContractRequest",
      counterPartyAddress,
      protocol: "dataspace-protocol-http",
      policy: buildNegotiationPolicy(catalogResponse, dataset, counterPartyId),
    },
  });
  await ensureOk(response, "Consumer contract negotiation request");
  const body = await response.json();
  const negotiationId = body?.["@id"] || body?.id;
  if (!negotiationId) {
    throw new Error("Contract negotiation response does not contain an identifier");
  }

  const deadline = Date.now() + negotiationTimeoutMs();
  let lastState = "UNKNOWN";
  let lastErrorDetail = "";
  while (Date.now() < deadline) {
    const negotiation = await lookupNegotiation(
      request,
      runtime.consumer.managementBaseUrl,
      consumerToken,
      negotiationId,
    );
    lastState = negotiationState(negotiation) || lastState;
    lastErrorDetail = negotiationErrorDetail(negotiation) || lastErrorDetail;
    const agreementId = negotiationAgreementId(negotiation);
    if (agreementId) {
      return {
        negotiationId,
        agreementId,
        assetId,
        state: lastState,
      };
    }
    if (["ERROR", "TERMINATED", "DECLINED"].includes(lastState)) {
      throw new Error(
        `Contract negotiation '${negotiationId}' reached state '${lastState}' without agreementId` +
          (lastErrorDetail ? `: ${lastErrorDetail}` : ""),
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  const finalNegotiation = await lookupNegotiation(
    request,
    runtime.consumer.managementBaseUrl,
    consumerToken,
    negotiationId,
  );
  const finalAgreementId = negotiationAgreementId(finalNegotiation);
  if (finalAgreementId) {
    return {
      negotiationId,
      agreementId: finalAgreementId,
      assetId,
      state: negotiationState(finalNegotiation) || lastState,
    };
  }

  throw new Error(
    `Contract negotiation '${negotiationId}' did not produce an agreement in time. ` +
      `Last observed state: ${negotiationState(finalNegotiation) || lastState}` +
      (negotiationErrorDetail(finalNegotiation) || lastErrorDetail
        ? `. Last error: ${negotiationErrorDetail(finalNegotiation) || lastErrorDetail}`
        : ""),
  );
}

export async function bootstrapConsumerTransfer(
  request: APIRequestContext,
  runtime: DataspacePortalRuntime,
  assetId: string,
  agreementId: string,
  counterPartyAddress: string,
): Promise<ConsumerTransferArtifacts> {
  const consumerToken = await issueConsumerToken(request, runtime);
  const transferStartPath = runtime.consumer.transferStartPath || "inesdatatransferprocesses";
  const transferDestinationType = runtime.consumer.transferDestinationType || "InesDataStore";
  const response = await request.post(`${runtime.consumer.managementBaseUrl}/${transferStartPath}`, {
    headers: {
      Authorization: `Bearer ${consumerToken}`,
      "Content-Type": "application/json",
    },
    data: {
      "@context": {
        "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
      },
      "@type": "TransferRequest",
      assetId,
      contractId: agreementId,
      counterPartyAddress,
      protocol: "dataspace-protocol-http",
      transferType: "AmazonS3-PUSH",
      dataDestination: {
        type: transferDestinationType,
      },
    },
  });
  await ensureOk(response, "Consumer transfer request");
  const body = await response.json();
  const transferId = body?.["@id"] || body?.id;
  if (!transferId) {
    throw new Error("Transfer response does not contain an identifier");
  }

  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const stateResponse = await request.get(`${runtime.consumer.managementBaseUrl}/transferprocesses/${transferId}`, {
      headers: {
        Authorization: `Bearer ${consumerToken}`,
      },
    });
    await ensureOk(stateResponse, "Consumer transfer status lookup");
    const stateBody = await stateResponse.json();
    const state = String(stateBody?.state || "").trim().toUpperCase();
    if (state === "COMPLETED" || state === "STARTED") {
      return {
        transferId,
        finalState: state,
        transferType: "AmazonS3-PUSH",
        assetId,
      };
    }
    if (state === "TERMINATED" || state === "DEPROVISIONED" || state === "SUSPENDED" || state === "ERROR") {
      throw new Error(`Transfer '${transferId}' reached failure state '${state}'`);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error(`Transfer '${transferId}' did not reach an active state in time`);
}
