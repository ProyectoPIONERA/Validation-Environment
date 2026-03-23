import fs from "fs";
import path from "path";

export type ConnectorPortalRuntime = {
  connectorName: string;
  portalBaseUrl: string;
  managementBaseUrl: string;
  username: string;
  password: string;
};

export type DataspacePortalRuntime = {
  dataspace: string;
  dsDomain: string;
  keycloakUrl: string;
  keycloakClientId: string;
  provider: ConnectorPortalRuntime;
  consumer: ConnectorPortalRuntime;
};

type DataspaceDefaults = {
  dataspace: string;
  environment: string;
  dsDomain: string;
  keycloakUrl: string;
  keycloakClientId: string;
};

function projectRoot(): string {
  return path.resolve(__dirname, "../../../..");
}

function parseKeyValueFile(filePath: string): Record<string, string> {
  const content = fs.readFileSync(filePath, "utf8");
  const values: Record<string, string> = {};

  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separator = trimmed.indexOf("=");
    if (separator <= 0) {
      continue;
    }

    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    values[key] = value;
  }

  return values;
}

function readJson(filePath: string): any {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function requiredString(value: string | undefined, label: string): string {
  if (!value || value.trim().length === 0) {
    throw new Error(`Missing value for ${label}`);
  }
  return value.trim();
}

function resolveDataspaceDefaults(): DataspaceDefaults {
  const deployerConfigPath = path.join(projectRoot(), "inesdata-deployment", "deployer.config");
  const deployerConfig = parseKeyValueFile(deployerConfigPath);

  return {
    dataspace: process.env.UI_DATASPACE || deployerConfig.DS_1_NAME || "demo",
    environment: process.env.UI_ENVIRONMENT || deployerConfig.ENVIRONMENT || "DEV",
    dsDomain: process.env.UI_DS_DOMAIN || deployerConfig.DS_DOMAIN_BASE || "dev.ds.dataspaceunit.upm",
    keycloakUrl:
      process.env.UI_KEYCLOAK_URL ||
      deployerConfig.KC_INTERNAL_URL ||
      deployerConfig.KC_URL ||
      "http://keycloak.dev.ed.dataspaceunit.upm",
    keycloakClientId: process.env.UI_KEYCLOAK_CLIENT_ID || "dataspace-users",
  };
}

function resolveConnectorRuntime(
  connectorName: string,
  dataspace: string,
  environment: string,
  dsDomain: string,
): ConnectorPortalRuntime {
  const credentialsPath = path.join(
    projectRoot(),
    "inesdata-deployment",
    "deployments",
    environment,
    dataspace,
    `credentials-connector-${connectorName}.json`,
  );
  const credentials = readJson(credentialsPath);
  const username = requiredString(credentials?.connector_user?.user, `${connectorName} username`);
  const password = requiredString(credentials?.connector_user?.passwd, `${connectorName} password`);
  const host = `${connectorName}.${dsDomain}`;

  return {
    connectorName,
    portalBaseUrl: process.env[`UI_${connectorName.toUpperCase().replace(/-/g, "_")}_PORTAL_URL`] || `http://${host}/inesdata-connector-interface`,
    managementBaseUrl: `http://${host}/management/v3`,
    username,
    password,
  };
}

export function resolveConnectorPortalRuntime(connectorName: string): ConnectorPortalRuntime {
  const defaults = resolveDataspaceDefaults();
  return resolveConnectorRuntime(
    connectorName,
    defaults.dataspace,
    defaults.environment,
    defaults.dsDomain,
  );
}

export function resolveDataspacePortalRuntime(): DataspacePortalRuntime {
  const defaults = resolveDataspaceDefaults();
  const providerConnector = process.env.UI_PROVIDER_CONNECTOR || "conn-citycouncil-demo";
  const consumerConnector = process.env.UI_CONSUMER_CONNECTOR || "conn-company-demo";

  return {
    dataspace: defaults.dataspace,
    dsDomain: defaults.dsDomain,
    keycloakUrl: defaults.keycloakUrl,
    keycloakClientId: defaults.keycloakClientId,
    provider: resolveConnectorRuntime(
      providerConnector,
      defaults.dataspace,
      defaults.environment,
      defaults.dsDomain,
    ),
    consumer: resolveConnectorRuntime(
      consumerConnector,
      defaults.dataspace,
      defaults.environment,
      defaults.dsDomain,
    ),
  };
}
