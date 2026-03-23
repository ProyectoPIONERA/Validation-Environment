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

function resolveOntologyHubRuntime() {
  const deployerConfig = parseKeyValueFile(path.join(projectRoot(), "deployer.config"));
  const dataspace = (process.env.UI_DATASPACE || deployerConfig.DS_1_NAME || "demo").trim();
  const dsDomain = (process.env.UI_DS_DOMAIN || deployerConfig.DS_DOMAIN_BASE || "dev.ds.dataspaceunit.upm").trim();

  return {
    dataspace,
    dsDomain,
    baseUrl:
      (process.env.ONTOLOGY_HUB_BASE_URL || `http://ontology-hub-${dataspace}.${dsDomain}`).replace(
        /\/$/,
        "",
      ),
    expectedVocabularyPrefix: process.env.ONTOLOGY_HUB_EXPECTED_VOCAB || "demohub",
    expectedVocabularyTitle: process.env.ONTOLOGY_HUB_EXPECTED_TITLE || "Demo Hub Vocabulary",
    expectedSearchTerm: process.env.ONTOLOGY_HUB_EXPECTED_QUERY || "Person",
    expectedClassPrefixedName:
      process.env.ONTOLOGY_HUB_EXPECTED_CLASS_PREFIXED_NAME || "demohub:Person",
    expectedPrimaryTag: process.env.ONTOLOGY_HUB_EXPECTED_PRIMARY_TAG || "validationdemo",
    expectedSecondaryTag: process.env.ONTOLOGY_HUB_EXPECTED_SECONDARY_TAG || "people",
    previousVersionDate: process.env.ONTOLOGY_HUB_PREVIOUS_VERSION_DATE || "2025-01-15",
    latestVersionDate: process.env.ONTOLOGY_HUB_LATEST_VERSION_DATE || "2026-03-22",
  };
}

module.exports = {
  resolveOntologyHubRuntime,
};
