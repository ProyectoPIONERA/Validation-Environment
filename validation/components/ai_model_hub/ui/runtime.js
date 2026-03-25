const fs = require("fs");
const path = require("path");

function projectRoot() {
  return path.resolve(__dirname, "../../../..");
}

function parseKeyValueFile(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const values = {};
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const separator = trimmed.indexOf("=");
    if (separator <= 0) {
      continue;
    }
    values[trimmed.slice(0, separator).trim()] = trimmed.slice(separator + 1).trim();
  }
  return values;
}

function resolveAIModelHubRuntime() {
  const deployerConfig = parseKeyValueFile(path.join(projectRoot(), "deployer.config"));
  const dataspace = (process.env.UI_DATASPACE || deployerConfig.DS_1_NAME || "demo").trim();
  const dsDomain = (process.env.UI_DS_DOMAIN || deployerConfig.DS_DOMAIN_BASE || "dev.ds.dataspaceunit.upm").trim();

  return {
    dataspace,
    dsDomain,
    baseUrl:
      (process.env.AI_MODEL_HUB_BASE_URL || `http://ai-model-hub-${dataspace}.${dsDomain}`).replace(
        /\/$/,
        "",
      ),
    expectedAppTitle: process.env.AI_MODEL_HUB_EXPECTED_APP_TITLE || "EDC Dashboard",
    homePath: process.env.AI_MODEL_HUB_HOME_PATH || "/home",
    catalogPath: process.env.AI_MODEL_HUB_CATALOG_PATH || "/catalog",
    mlAssetsPath: process.env.AI_MODEL_HUB_ML_ASSETS_PATH || "/ml-assets",
    searchTerm: process.env.AI_MODEL_HUB_SEARCH_TERM || "model",
    requestButtonLabel: process.env.AI_MODEL_HUB_REQUEST_BUTTON_LABEL || "Request Manually",
  };
}

module.exports = {
  resolveAIModelHubRuntime,
};
