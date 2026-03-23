import fs from "fs";
import path from "path";

type MinioUserCredentials = {
  username: string;
  password: string;
};

export type MinioBucketTarget = {
  role: "provider" | "consumer";
  connectorName: string;
  bucketName: string;
  bucketBrowserUrl: string;
  credentials: MinioUserCredentials;
  expectedObject?: string;
};

export type MinioConsoleRuntime = {
  consoleBaseUrl: string;
  dataspace: string;
  environment: string;
  targets: MinioBucketTarget[];
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

function resolveConnectorMinioCredentials(
  connectorName: string,
  dataspace: string,
  environment: string,
): MinioUserCredentials {
  const credentialsPath = path.join(
    projectRoot(),
    "inesdata-deployment",
    "deployments",
    environment,
    dataspace,
    `credentials-connector-${connectorName}.json`,
  );
  const credentials = readJson(credentialsPath);

  return {
    username: requiredString(credentials?.minio?.user, `${connectorName} MinIO username`),
    password: requiredString(credentials?.minio?.passwd, `${connectorName} MinIO password`),
  };
}

function withNoTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

function buildBucketTarget(opts: {
  role: "provider" | "consumer";
  connectorName: string;
  dataspace: string;
  environment: string;
  consoleBaseUrl: string;
  bucketOverride?: string;
  expectedObject?: string;
}): MinioBucketTarget {
  const bucketName = opts.bucketOverride || `${opts.dataspace}-${opts.connectorName}`;

  return {
    role: opts.role,
    connectorName: opts.connectorName,
    bucketName,
    bucketBrowserUrl: `${withNoTrailingSlash(opts.consoleBaseUrl)}/browser/${bucketName}`,
    credentials: resolveConnectorMinioCredentials(
      opts.connectorName,
      opts.dataspace,
      opts.environment,
    ),
    expectedObject: opts.expectedObject,
  };
}

export function resolveMinioConsoleRuntime(): MinioConsoleRuntime {
  const deployerConfigPath = path.join(projectRoot(), "inesdata-deployment", "deployer.config");
  const deployerConfig = parseKeyValueFile(deployerConfigPath);

  const dataspace = process.env.UI_DATASPACE || deployerConfig.DS_1_NAME || "demo";
  const environment = process.env.UI_ENVIRONMENT || deployerConfig.ENVIRONMENT || "DEV";
  const domainBase = process.env.UI_DOMAIN_BASE || deployerConfig.DOMAIN_BASE || "dev.ed.dataspaceunit.upm";
  const providerConnector = process.env.UI_PROVIDER_CONNECTOR || "conn-citycouncil-demo";
  const consumerConnector = process.env.UI_CONSUMER_CONNECTOR || "conn-company-demo";
  const consoleBaseUrl =
    process.env.UI_MINIO_CONSOLE_URL || `http://console.minio-s3.${domainBase}`;

  return {
    consoleBaseUrl,
    dataspace,
    environment,
    targets: [
      buildBucketTarget({
        role: "provider",
        connectorName: providerConnector,
        dataspace,
        environment,
        consoleBaseUrl,
        bucketOverride: process.env.UI_MINIO_PROVIDER_BUCKET,
        expectedObject: process.env.UI_MINIO_PROVIDER_EXPECT_OBJECT,
      }),
      buildBucketTarget({
        role: "consumer",
        connectorName: consumerConnector,
        dataspace,
        environment,
        consoleBaseUrl,
        bucketOverride: process.env.UI_MINIO_CONSUMER_BUCKET,
        expectedObject: process.env.UI_MINIO_CONSUMER_EXPECT_OBJECT,
      }),
    ],
  };
}
