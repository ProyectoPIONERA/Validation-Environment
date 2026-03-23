import type { APIRequestContext } from "@playwright/test";

import type { DataspacePortalRuntime } from "./dataspace-runtime";

type BootstrapArtifacts = {
  assetId: string;
  policyId: string;
  contractDefinitionId: string;
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
        name: "todos",
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
): Promise<BootstrapArtifacts> {
  const providerToken = await issueUserToken(request, runtime);
  const policyId = `policy-ui-${suffix}`;
  const contractDefinitionId = `contract-ui-${suffix}`;

  await createAsset(request, runtime, providerToken, assetId);
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
