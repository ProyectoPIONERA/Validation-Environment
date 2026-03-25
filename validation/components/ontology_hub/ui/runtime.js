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
    adminEmail: process.env.ONTOLOGY_HUB_ADMIN_EMAIL || "admin@gmail.com",
    adminPassword: process.env.ONTOLOGY_HUB_ADMIN_PASSWORD || "admin1234",
    expectedVocabularyPrefix: process.env.ONTOLOGY_HUB_EXPECTED_VOCAB || "s4grid",
    expectedVocabularyTitle: process.env.ONTOLOGY_HUB_EXPECTED_TITLE || "SAREF4GRID",
    expectedSearchTerm: process.env.ONTOLOGY_HUB_EXPECTED_QUERY || "Person",
    expectedClassPrefixedName:
      process.env.ONTOLOGY_HUB_EXPECTED_CLASS_PREFIXED_NAME || "s4grid:Person",
    expectedPrimaryTag: process.env.ONTOLOGY_HUB_EXPECTED_PRIMARY_TAG || "Catalogs",
    expectedSecondaryTag: process.env.ONTOLOGY_HUB_EXPECTED_SECONDARY_TAG || "Environment",
    previousVersionDate: process.env.ONTOLOGY_HUB_PREVIOUS_VERSION_DATE || "2025-01-15",
    latestVersionDate: process.env.ONTOLOGY_HUB_LATEST_VERSION_DATE || "2026-03-22",
    creationUri:
      process.env.ONTOLOGY_HUB_CREATION_URI || "https://saref.etsi.org/saref4grid/v2.1.1/",
    creationNamespace:
      process.env.ONTOLOGY_HUB_CREATION_NAMESPACE || "https://saref.etsi.org/saref4grid/",
    creationPrefix: process.env.ONTOLOGY_HUB_CREATION_PREFIX || "s4grid",
    creationTitle:
      process.env.ONTOLOGY_HUB_CREATION_TITLE || "SAREF4GRID Vocabulary",
    creationDescription:
      process.env.ONTOLOGY_HUB_CREATION_DESCRIPTION ||
      "Vocabulary created through the Ontology Hub Playwright validation flow.",
    creationTag: process.env.ONTOLOGY_HUB_CREATION_TAG || "Catalogs",
    creationReview:
      process.env.ONTOLOGY_HUB_CREATION_REVIEW || "Validated through the Playwright ontology flow.",
    listingSearchTerm: process.env.ONTOLOGY_HUB_LISTING_QUERY || "s4grid",
  };
}

module.exports = {
  resolveOntologyHubRuntime,
};
