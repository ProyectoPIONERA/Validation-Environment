const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const { gotoEdition } = require("../../ui/support/bootstrap");
const { OntologyHubVocabFormPage } = require("../../ui/pages/vocab-form.page");
const { OntologyHubVocabDetailPage } = require("../../ui/pages/vocab-detail.page");

const DEFAULT_URI = "https://saref.etsi.org/saref4grid/v2.1.1/";
const DEFAULT_REPOSITORY_URI =
  "https://github.com/ProyectoPIONERA/Ontology-Development-Repository-Example";
const URI_VOCAB_STATE_KEY = "oh-app-03-uri-vocabulary";
const REPOSITORY_VOCAB_STATE_KEY = "oh-app-04-repository-vocabulary";
const VERSION_STATE_KEY = "oh-app-11-version-state";

function normalizeText(value) {
  return String(value || "").trim();
}

function runStateDir() {
  const runtimeFile = normalizeText(process.env.ONTOLOGY_HUB_RUNTIME_FILE);
  if (runtimeFile) {
    return path.resolve(process.cwd(), path.dirname(runtimeFile));
  }

  const explicitDir = normalizeText(
    process.env.ONTOLOGY_HUB_FUNCTIONAL_STATE_DIR ||
      process.env.ONTOLOGY_HUB_APP_FLOWS_STATE_DIR,
  );
  if (explicitDir) {
    return path.resolve(process.cwd(), explicitDir);
  }

  return path.resolve(__dirname, "../state");
}

function generatedArtifactsDir() {
  const explicitDir = normalizeText(
    process.env.ONTOLOGY_HUB_FUNCTIONAL_GENERATED_DIR ||
      process.env.ONTOLOGY_HUB_APP_FLOWS_GENERATED_DIR,
  );
  if (explicitDir) {
    return path.resolve(process.cwd(), explicitDir);
  }

  return path.resolve(__dirname, "../generated");
}

function runStatePath(key) {
  return path.join(runStateDir(), `${normalizeText(key)}.json`);
}

function persistGeneratedArtifact(sourcePath, targetName = "", subdir = "") {
  const source = path.resolve(sourcePath);
  if (!fs.existsSync(source)) {
    throw new Error(`Generated artifact source does not exist: ${source}`);
  }

  const directory = path.join(generatedArtifactsDir(), normalizeText(subdir));
  fs.mkdirSync(directory, { recursive: true });
  const fileName = normalizeText(targetName) || path.basename(source);
  const destination = path.join(directory, fileName);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(source, destination);
  return destination;
}

function saveRunState(key, payload) {
  const filePath = runStatePath(key);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf8");
  return filePath;
}

function loadRunState(key) {
  const filePath = runStatePath(key);
  if (!fs.existsSync(filePath)) {
    throw new Error(
      `Required Ontology Hub shared state is missing for '${key}'. Expected file: ${filePath}`,
    );
  }

  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function deleteRunState(key) {
  const filePath = runStatePath(key);
  if (fs.existsSync(filePath)) {
    fs.unlinkSync(filePath);
  }
}

async function safeTextContent(locator) {
  try {
    if ((await locator.count()) === 0) {
      return "";
    }
    return (await locator.first().textContent()) || "";
  } catch (error) {
    return "";
  }
}

function escapeRegExp(value) {
  return normalizeText(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function caseSlug(caseId) {
  return normalizeText(caseId)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function uniqueSuffix(testInfo) {
  const now = Date.now().toString(36);
  const retry = String(testInfo.retry || 0);
  const worker = String(testInfo.parallelIndex || 0);
  return `${now}-${worker}-${retry}`.slice(-18);
}

function buildVocabularyRuntime(runtime, caseId, testInfo, overrides = {}) {
  const suffix = uniqueSuffix(testInfo).replace(/[^a-z0-9-]/g, "");
  const prefix = normalizeText(
    overrides.creationPrefix || `oh-${caseSlug(caseId)}-${suffix}`.slice(0, 40),
  )
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");

  return {
    ...runtime,
    ...overrides,
    creationUri: normalizeText(overrides.creationUri || runtime.creationUri || DEFAULT_URI),
    creationRepositoryUri: normalizeText(
      overrides.creationRepositoryUri || runtime.creationRepositoryUri || DEFAULT_REPOSITORY_URI,
    ),
    creationPrefix: prefix,
    expectedVocabularyPrefix: prefix,
    listingSearchTerm: prefix,
    creationTitle:
      normalizeText(overrides.creationTitle) || `Ontology Hub ${caseId} ${suffix}`.slice(0, 70),
    expectedVocabularyTitle:
      normalizeText(overrides.creationTitle) || `Ontology Hub ${caseId} ${suffix}`.slice(0, 70),
    creationDescription:
      normalizeText(overrides.creationDescription) ||
      `Vocabulary created for automated Excel case ${caseId}.`,
    creationTag: normalizeText(overrides.creationTag || "Services"),
    creationReview:
      normalizeText(overrides.creationReview) ||
      `Automated validation evidence for Excel case ${caseId}.`,
  };
}

function buildExcelUriVocabularyRuntime(runtime, overrides = {}) {
  return {
    ...runtime,
    ...overrides,
    creationUri: normalizeText(overrides.creationUri || runtime.creationUri || DEFAULT_URI),
    creationNamespace: normalizeText(
      overrides.creationNamespace || runtime.creationNamespace || "https://saref.etsi.org/saref4grid/",
    ),
    creationPrefix: normalizeText(overrides.creationPrefix || "saref4grid"),
    expectedVocabularyPrefix: normalizeText(overrides.expectedVocabularyPrefix || "saref4grid"),
    listingSearchTerm: normalizeText(overrides.listingSearchTerm || "saref4grid"),
    creationTitle: normalizeText(overrides.creationTitle || "saref4grid"),
    expectedVocabularyTitle: normalizeText(overrides.expectedVocabularyTitle || "saref4grid"),
    creationDescription:
      normalizeText(overrides.creationDescription) ||
      "Ontology registered from the ETSI SAREF4GRID URI for Excel validation.",
    creationTag: normalizeText(overrides.creationTag || "Services"),
    creationReview: normalizeText(overrides.creationReview || "Admin"),
    expectedPrimaryTag: normalizeText(overrides.expectedPrimaryTag || "Services"),
  };
}

function buildExcelRepositoryVocabularyRuntime(runtime, overrides = {}) {
  return {
    ...runtime,
    ...overrides,
    creationRepositoryUri: normalizeText(
      overrides.creationRepositoryUri || runtime.creationRepositoryUri || DEFAULT_REPOSITORY_URI,
    ),
    creationPrefix: normalizeText(overrides.creationPrefix || "ontology-development-repository-example"),
    expectedVocabularyPrefix: normalizeText(
      overrides.expectedVocabularyPrefix || "ontology-development-repository-example",
    ),
    listingSearchTerm: normalizeText(
      overrides.listingSearchTerm || "Ontology-Development-Repository-Example",
    ),
    creationTitle: normalizeText(overrides.creationTitle || "Ontology-Development-Repository-Example"),
    expectedVocabularyTitle: normalizeText(
      overrides.expectedVocabularyTitle || "Ontology-Development-Repository-Example",
    ),
    creationDescription:
      normalizeText(overrides.creationDescription) ||
      "Ontology registered from the public repository for Excel validation.",
    creationTag: normalizeText(overrides.creationTag || "Services"),
    creationReview: normalizeText(overrides.creationReview || "Admin"),
    expectedPrimaryTag: normalizeText(overrides.expectedPrimaryTag || "Services"),
  };
}

function runtimeFromCreatedVocabulary(runtime, created = {}, overrides = {}) {
  const prefix = normalizeText(overrides.expectedVocabularyPrefix || created.prefix || runtime.expectedVocabularyPrefix);
  const title = normalizeText(overrides.expectedVocabularyTitle || created.title || runtime.expectedVocabularyTitle);
  return {
    ...runtime,
    ...created,
    ...overrides,
    expectedVocabularyPrefix: prefix,
    expectedVocabularyTitle: title,
    listingSearchTerm: normalizeText(overrides.listingSearchTerm || created.catalogLabel || title || prefix),
    expectedPrimaryTag: normalizeText(overrides.expectedPrimaryTag || created.creationTag || created.tag || runtime.expectedPrimaryTag || "Services"),
  };
}

async function expectHealthyPage(page, label) {
  const heading = normalizeText(await safeTextContent(page.locator("h1").first()));
  if (/404|500|oops!/i.test(heading)) {
    throw new Error(`${label} page failed to load: ${heading}`);
  }
}

async function signInToEdition(page, runtime, credentials = {}) {
  const email = normalizeText(credentials.email || runtime.adminEmail);
  const password = normalizeText(credentials.password || runtime.adminPassword);

  await page.goto(`${runtime.baseUrl}/edition`, { waitUntil: "commit", timeout: 5000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 5000 }).catch(() => {});
  if (/\/edition\/login\/?$/i.test(page.url())) {
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Password").fill(password);
    await page.getByRole("button", { name: /log in it!?/i }).click();
    await page.waitForLoadState("domcontentloaded", { timeout: 5000 }).catch(() => {});
  }

  const invalidCredentials = normalizeText(await safeTextContent(page.locator("#formErrors")));
  if (/invalid email or password/i.test(invalidCredentials)) {
    throw new Error(`Ontology Hub rejected the credentials for '${email}'.`);
  }

  await page
    .locator("a[href='/edition/logout'], a[href='/edition/'], a[href^='/edition/users/']")
    .first()
    .waitFor({ state: "visible", timeout: 5000 });

  return page.url();
}

async function signOut(page, runtime) {
  const logoutLink = page.getByRole("link", { name: /logout/i }).first();
  if ((await logoutLink.count()) > 0 && (await logoutLink.isVisible().catch(() => false))) {
    await logoutLink.click();
    await page.waitForLoadState("domcontentloaded");
    return;
  }

  await page.goto(`${runtime.baseUrl}/edition/logout`, { waitUntil: "domcontentloaded" });
}

async function ensureTagSelected(page, tagLabel) {
  const normalized = normalizeText(tagLabel);
  if (!normalized) {
    return;
  }

  const currentTags = await page
    .locator("#tagsUl input[name='tags[]']")
    .evaluateAll((nodes) => nodes.map((node) => String(node.value || "").trim()))
    .catch(() => []);
  if (currentTags.some((value) => value.toLowerCase() === normalized.toLowerCase())) {
    return;
  }

  await page.locator(".fieldTagsAddAction").click();
  await page.locator("#listOfTags").waitFor({ state: "visible", timeout: 5000 });

  const tagPattern = new RegExp(`^\\s*${escapeRegExp(normalized)}\\s*$`, "i");
  let tagOption = page.locator("#tagsPickerList .tagFromList").filter({ hasText: tagPattern }).first();

  if ((await tagOption.count()) === 0) {
    await page.locator("#toggleCreateTag").click();
    await page.locator("#newTagLabel").fill(normalized);
    await page.locator("#btnCreateTag").click();
    tagOption = page.locator("#tagsPickerList .tagFromList").filter({ hasText: tagPattern }).first();
    await tagOption.waitFor({ state: "visible", timeout: 5000 });
  }

  await tagOption.click();
  await page.waitForFunction(
    (expectedTag) =>
      Array.from(document.querySelectorAll('#tagsUl input[name="tags[]"]')).some(
        (node) => String(node.value || "").trim().toLowerCase() === expectedTag.toLowerCase(),
      ),
    normalized,
    { timeout: 5000 },
  );

  await page.keyboard.press("Escape").catch(() => {});
}

async function ensureMultilingualTextareas(page, fieldKind, primaryLanguage, secondaryLanguage) {
  const addButton =
    fieldKind === "titles"
      ? page.locator(".fieldWithLangAddActionTitle")
      : page.locator(".fieldWithLangAddActionDescription");
  const selects = page.locator(`select[name^='${fieldKind}']`);

  if ((await selects.count()) === 0) {
    await addButton.click();
  }
  if ((await selects.count()) < 2) {
    await addButton.click();
  }

  const primary = normalizeText(primaryLanguage).toLowerCase();
  const secondary = normalizeText(secondaryLanguage).toLowerCase();

  if (primary) {
    await selects.first().selectOption(primary);
  }
  if (secondary && (await selects.count()) > 1) {
    await selects.nth(1).selectOption(secondary);
  }
}

async function fillVocabularyMetadata(page, runtime) {
  const createHeader = page.getByRole("heading", { name: "Create a new Vocabulary", exact: true });
  await createHeader.waitFor({ state: "visible", timeout: 5000 });

  await page.locator("#inputVocabPrefix").fill(runtime.creationPrefix);
  if ((await page.locator("#inputVocabUri").count()) > 0 && normalizeText(runtime.creationUri)) {
    await page.locator("#inputVocabUri").fill(runtime.creationUri);
  }
  if ((await page.locator("#inputVocabNsp").count()) > 0 && normalizeText(runtime.creationNamespace)) {
    await page.locator("#inputVocabNsp").fill(runtime.creationNamespace);
  }

  await ensureMultilingualTextareas(
    page,
    "titles",
    runtime.creationPrimaryLanguage || "en",
    runtime.creationSecondaryLanguage || "es",
  );
  await page.locator("textarea[name^='titles']").first().fill(runtime.creationTitle);
  if ((await page.locator("textarea[name^='titles']").count()) > 1) {
    await page
      .locator("textarea[name^='titles']")
      .nth(1)
      .fill(`${runtime.creationTitle} ES`);
  }

  await ensureMultilingualTextareas(
    page,
    "descriptions",
    runtime.creationPrimaryLanguage || "en",
    runtime.creationSecondaryLanguage || "es",
  );
  await page.locator("textarea[name^='descriptions']").first().fill(runtime.creationDescription);
  if ((await page.locator("textarea[name^='descriptions']").count()) > 1) {
    await page
      .locator("textarea[name^='descriptions']")
      .nth(1)
      .fill(`${runtime.creationDescription} ES`);
  }

  await ensureTagSelected(page, runtime.creationTag || "Services");

  const reviews = page.locator("textarea[name^='reviews']");
  if ((await reviews.count()) === 0) {
    await page.locator(".fieldReviewAddAction").click();
  }
  await page.locator("textarea[name^='reviews']").first().fill(runtime.creationReview);
}

async function saveVocabulary(page) {
  const formPage = new OntologyHubVocabFormPage(page);
  const outcome = await formPage.save();
  const formErrors = await formPage.readFormErrors();

  if (formErrors) {
    throw new Error(`Ontology Hub reported vocabulary form errors: ${formErrors}`);
  }

  const landedOnVocabularyDetail = /\/dataset\/vocabs\/[^/]+\/?$/i.test(outcome.finalUrl || "");
  if (!landedOnVocabularyDetail) {
    throw new Error(
      `Ontology Hub did not publish the vocabulary after save. Final URL: ${
        outcome.finalUrl || "unknown"
      }`,
    );
  }

  return outcome;
}

async function createVocabularyByUri(page, runtime) {
  await gotoEdition(page, runtime);
  await page.locator(".createVocab").click();
  await page.locator("#dialogCreateVocab").waitFor({ state: "visible", timeout: 5000 });
  await page.locator("#formDialogCreateVocabFromURI input[name='uri']").fill(runtime.creationUri);
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");

  const duplicateError = normalizeText(
    await page
      .locator(".alert-error, #dialogCreateVocabError, #formErrors")
      .first()
      .textContent()
      .catch(() => ""),
  );
  if (/already exists/i.test(duplicateError)) {
    throw new Error(`Ontology Hub rejected the URI registration because it already exists: ${duplicateError}`);
  }

  await fillVocabularyMetadata(page, runtime);
  await saveVocabulary(page);

  return {
    prefix: runtime.creationPrefix,
    title: runtime.creationTitle,
    url: page.url(),
    method: "uri",
  };
}

async function createVocabularyFromRepository(page, runtime) {
  await gotoEdition(page, runtime);
  await page.locator(".createVocab").click();
  await page.locator("#dialogCreateVocab").waitFor({ state: "visible", timeout: 5000 });
  await page
    .locator("#formDialogCreateVocabFromOntologyDevelopmentRepository input[name='repositoryUri']")
    .fill(runtime.creationRepositoryUri);
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");

  const visibleError = normalizeText(
    await page
      .locator(".alert-error, #dialogCreateVocabError, #formErrors")
      .first()
      .textContent()
      .catch(() => ""),
  );
  if (visibleError && !/create a new vocabulary/i.test((await page.content()).toLowerCase())) {
    throw new Error(`Ontology Hub rejected the repository registration: ${visibleError}`);
  }

  await fillVocabularyMetadata(page, runtime);
  await saveVocabulary(page);

  return {
    prefix: runtime.creationPrefix,
    title: runtime.creationTitle,
    url: page.url(),
    method: "repository",
  };
}

async function createAgent(page, runtime, agent) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/agents/new`, { waitUntil: "domcontentloaded" });
  await expectHealthyPage(page, "Create agent");

  await page.locator("input[name='name']").fill(agent.name);
  await page.locator("select[name='type']").selectOption(agent.type || "person");
  await page.locator("input[name='prefUri']").fill(agent.prefUri);
  await page.locator("input[type='submit'][value='Save']").click();
  await page.waitForLoadState("domcontentloaded");

  const agentDetailUrl = `${runtime.baseUrl}/dataset/agents/${encodeURIComponent(agent.name)}`;
  await page.goto(agentDetailUrl, { waitUntil: "domcontentloaded" });
  await expectHealthyPage(page, "Agent detail");
  await page.getByRole("heading", { level: 1, name: new RegExp(escapeRegExp(agent.name), "i") }).waitFor({
    state: "visible",
    timeout: 5000,
  });

  return {
    ...agent,
    detailUrl: page.url(),
  };
}

async function createUserForAgent(page, runtime, user) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/signup`, { waitUntil: "domcontentloaded" });
  await expectHealthyPage(page, "Signup");

  await page.locator("#userNameAgent").fill(user.agentName);
  const suggestions = page.locator("ul.ui-autocomplete li");
  await suggestions.first().waitFor({ state: "visible", timeout: 5000 });
  await suggestions.filter({ hasText: new RegExp(`^\\s*${escapeRegExp(user.agentName)}\\s*$`, "i") }).first().click();
  await page.locator("#next:not([disabled])").click();

  await page.locator("#email").fill(user.email);
  await page.locator("input[name='password']").fill(user.password);
  await page.locator("input[name='password_confirm']").fill(user.password);
  await page.locator("input[type='submit'][value='Submit']").click();
  await page.waitForLoadState("domcontentloaded");

  const formErrors = normalizeText(await safeTextContent(page.locator("#formErrors")));
  if (formErrors) {
    throw new Error(`Ontology Hub rejected the user signup flow: ${formErrors}`);
  }

  await page.goto(`${runtime.baseUrl}/edition/users`, { waitUntil: "domcontentloaded" });
  const usersRow = page.locator(".SearchBoxperson").filter({ hasText: user.email }).first();
  if (await usersRow.isVisible().catch(() => false)) {
    return user;
  }

  const editionEmail = page.getByText(user.email, { exact: false }).first();
  if (await editionEmail.isVisible().catch(() => false)) {
    return user;
  }

  await page.goto(`${runtime.baseUrl}/edition`, { waitUntil: "domcontentloaded" });
  await page.getByText(user.email, { exact: false }).first().waitFor({ state: "visible", timeout: 5000 });

  return user;
}

async function promoteUserToAdmin(page, runtime, user) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/users`, { waitUntil: "domcontentloaded" });
  const row = page
    .locator(".SearchBoxperson, li, article, .editionBoxSugg")
    .filter({ hasText: user.email })
    .first();
  await row.waitFor({ state: "visible", timeout: 5000 });
  const promoteButton = row
    .locator("input.statusSubmit, .statusButton, button, a")
    .filter({ hasText: /admin/i })
    .first();
  if ((await promoteButton.count()) === 0) {
    throw new Error(`Could not find the Admin promotion control for '${user.email}'.`);
  }
  await promoteButton.click();
  await page.waitForLoadState("domcontentloaded");
  await page
    .locator(".SearchBoxperson, li, article, .editionBoxSugg")
    .filter({ hasText: user.email })
    .first()
    .getByText(/admin/i)
    .waitFor({ state: "visible", timeout: 5000 });
}

async function assertCreateUserControl(page, visible) {
  const createUserLink = page.locator("a[href='/edition/signup'], a[href='/edition/signup/']").first();
  if (visible) {
    await createUserLink.waitFor({ state: "visible", timeout: 5000 });
    return;
  }

  if ((await createUserLink.count()) > 0 && (await createUserLink.isVisible().catch(() => false))) {
    throw new Error("The + USER control is visible, but the current case expected it to be hidden.");
  }
}

async function editAgentFromPublicDetail(page, runtime, agentName, newAgentName) {
  await page.goto(`${runtime.baseUrl}/dataset/agents/${encodeURIComponent(agentName)}`, {
    waitUntil: "domcontentloaded",
  });
  await expectHealthyPage(page, "Agent detail");
  await page.locator("a[href*='/edition/agents/'] img[src*='edit_grey']").click();
  await page.waitForLoadState("domcontentloaded");
  await page.locator("input[name='name']").fill(newAgentName);
  await page.locator("input[type='submit'][value='Save']").click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(`${runtime.baseUrl}/dataset/agents/${encodeURIComponent(newAgentName)}`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("heading", { level: 1, name: new RegExp(escapeRegExp(newAgentName), "i") }).waitFor({
    state: "visible",
    timeout: 5000,
  });
}

async function deleteAgentFromPublicDetail(page, runtime, agentName) {
  await page.goto(`${runtime.baseUrl}/dataset/agents/${encodeURIComponent(agentName)}`, {
    waitUntil: "domcontentloaded",
  });
  await expectHealthyPage(page, "Agent detail");
  await page.locator("#agentDelete").click();
  await page.getByRole("button", { name: "Confirm Deletion", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(`${runtime.baseUrl}/dataset/agents`, { waitUntil: "domcontentloaded" });
  await page.locator("#searchInput").fill(agentName);
  await page.waitForTimeout(1000);
  const suggestions = page.locator("ul.ui-autocomplete li").filter({ hasText: new RegExp(escapeRegExp(agentName), "i") });
  if ((await suggestions.count()) > 0) {
    throw new Error(`Agent '${agentName}' is still returned by the public agents search after deletion.`);
  }
}

async function createTag(page, runtime, label) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/tags/new`, { waitUntil: "domcontentloaded" });
  await expectHealthyPage(page, "Create tag");
  await page.locator("input[name='label']").fill(label);
  await page.locator("input[type='submit'][value='Save']").click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(`${runtime.baseUrl}/edition/tags`, { waitUntil: "domcontentloaded" });
  await page.locator("#SearchGrid .SearchBoxtag").filter({ hasText: label }).first().waitFor({
    state: "visible",
    timeout: 5000,
  });
}

async function editTag(page, runtime, currentLabel, newLabel) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/tags`, { waitUntil: "domcontentloaded" });
  const row = page.locator("#SearchGrid .SearchBoxtag").filter({ hasText: currentLabel }).first();
  await row.waitFor({ state: "visible", timeout: 5000 });
  await row.locator("form[name='formEdit'] img").click();
  await page.waitForLoadState("domcontentloaded");
  await page.locator("input[name='label']").fill(newLabel);
  await page.locator("input[type='submit'][value='Save']").click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(`${runtime.baseUrl}/edition/tags`, { waitUntil: "domcontentloaded" });
  await page.locator("#SearchGrid .SearchBoxtag").filter({ hasText: newLabel }).first().waitFor({
    state: "visible",
    timeout: 5000,
  });
}

async function deleteTag(page, runtime, label) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/tags`, { waitUntil: "domcontentloaded" });
  const row = page.locator("#SearchGrid .SearchBoxtag").filter({ hasText: label }).first();
  await row.waitFor({ state: "visible", timeout: 5000 });
  await row.locator(".removeTag").click();
  await page.getByRole("button", { name: "Confirm Deletion", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");
  const remaining = page.locator("#SearchGrid .SearchBoxtag").filter({ hasText: label });
  if ((await remaining.count()) > 0 && (await remaining.first().isVisible().catch(() => false))) {
    throw new Error(`Tag '${label}' is still visible after deletion.`);
  }
}

async function downloadFirstN3(page, testInfo, baseName, options = {}) {
  const link = page.locator("a[href$='.n3']").first();
  await link.waitFor({ state: "visible", timeout: 5000 });
  const href = normalizeText(await link.getAttribute("href"));
  const filePath = testInfo.outputPath(`${baseName}.n3`);
  let suggestedFilename = path.basename(href || `${baseName}.n3`) || `${baseName}.n3`;
  const strategy = normalizeText(options.strategy || "browser").toLowerCase();

  const requestDownload = async () => {
    if (!href) {
      throw new Error("The vocabulary exposes an .n3 link without a usable href.");
    }

    const absoluteUrl = new URL(href, page.url()).toString();
    const response = await page.request.get(absoluteUrl, { timeout: 5000 });
    if (!response.ok()) {
      throw new Error(`The .n3 resource returned HTTP ${response.status()} for ${absoluteUrl}`);
    }

    const body = await response.text();
    fs.writeFileSync(filePath, body, "utf8");
    suggestedFilename = path.basename(new URL(absoluteUrl).pathname) || suggestedFilename;
  };

  try {
    if (strategy === "request") {
      await requestDownload();
    } else {
      const downloadPromise = page.waitForEvent("download", { timeout: 5000 });
      await link.click();
      const download = await downloadPromise;
      await download.saveAs(filePath);
      suggestedFilename = download.suggestedFilename();
    }
  } catch (error) {
    await requestDownload();
  }

  const stat = fs.statSync(filePath);
  const persistedPath = persistGeneratedArtifact(filePath, `${normalizeText(baseName)}.n3`, "n3");
  return {
    filePath,
    persistedPath,
    suggestedFilename,
    size: stat.size,
    href,
  };
}

async function openVocabularyDetail(page, runtime, prefix, title = "") {
  const detailPage = new OntologyHubVocabDetailPage(page);
  await detailPage.goto(runtime.baseUrl, prefix);
  await detailPage.expectReady(prefix, title);
  return detailPage;
}

async function openVersionsPage(page, runtime, prefix) {
  await gotoEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/edition/vocabs/${encodeURIComponent(prefix)}/versions`, {
    waitUntil: "domcontentloaded",
  });
  await expectHealthyPage(page, "Vocabulary versions");
  await page
    .locator(".editionIndexBoxHeader .title")
    .filter({ hasText: /versions/i })
    .first()
    .waitFor({ state: "visible", timeout: 5000 });
}

async function createVersion(page, version, filePath) {
  await page.locator(".editionIndexBoxHeader .fieldReviewAddAction").click();
  const dialog = page.locator("#dialogNewVersion");
  await dialog.waitFor({ state: "visible", timeout: 5000 });
  await dialog.locator("tr").filter({ hasText: /Version issued Date/i }).locator("input").first().fill(version.issued);
  await dialog.locator("tr").filter({ hasText: /Version Label/i }).locator("input, textarea").first().fill(version.name);
  await dialog.locator("input[type='file'], input[name='file']").first().setInputFiles(filePath);
  await dialog.locator("form#dialogNewVersionForm").evaluate((form) => form.submit());
  await page.waitForLoadState("domcontentloaded");

  const versionRow = page.locator(".editionBoxSugg").filter({
    hasText: new RegExp(`${escapeRegExp(version.issued)}|${escapeRegExp(version.name)}`, "i"),
  }).first();
  const unhealthyHeading = page.locator("h1").filter({ hasText: /50[0-9]|bad gateway|oops/i }).first();
  try {
    const outcome = await Promise.race([
      versionRow.waitFor({ state: "visible", timeout: 5000 }).then(() => "row"),
      unhealthyHeading.waitFor({ state: "visible", timeout: 5000 }).then(() => "error-page").catch(() => null),
    ]);
    if (outcome === "error-page") {
      const headingText = normalizeText(await safeTextContent(unhealthyHeading));
      throw new Error(`Ontology Hub returned an unhealthy page after version submit: ${headingText || "unknown error page"}`);
    }
  } catch (error) {
    const dialogText = normalizeText(await safeTextContent(dialog));
    const formErrors = normalizeText(await safeTextContent(page.locator("#formErrors, #dialogNewVersionFormErrors")));
    throw new Error(
      `${error.message || `Version creation did not complete within 15000ms for '${version.name}'.`} ` +
        `Dialog: ${dialogText || "no diagnostic text"}. ` +
        `Form errors: ${formErrors || "none"}`,
    );
  }
}

async function editVersion(page, currentVersionName, updatedVersion) {
  const versionRow = page.locator(".editionBoxSugg").filter({ hasText: currentVersionName }).first();
  await versionRow.waitFor({ state: "visible", timeout: 5000 });
  await versionRow.locator(".imageVersionActionEdit").click();
  const dialog = page.locator("#dialogEditVersion");
  await dialog.waitFor({ state: "visible", timeout: 5000 });
  await dialog.locator("input").first().fill(updatedVersion.issued);
  await dialog.locator("input").nth(1).fill(updatedVersion.name);
  await dialog.locator("form#dialogEditVersionForm").evaluate((form) => form.submit());
  await page.waitForLoadState("domcontentloaded");

  const updatedRow = page.locator(".editionBoxSugg").filter({
    hasText: new RegExp(`${escapeRegExp(updatedVersion.issued)}|${escapeRegExp(updatedVersion.name)}`, "i"),
  }).first();
  const unhealthyHeading = page.locator("h1").filter({ hasText: /50[0-9]|bad gateway|oops/i }).first();
  try {
    const outcome = await Promise.race([
      updatedRow.waitFor({ state: "visible", timeout: 5000 }).then(() => "row"),
      unhealthyHeading.waitFor({ state: "visible", timeout: 5000 }).then(() => "error-page").catch(() => null),
    ]);
    if (outcome === "error-page") {
      const headingText = normalizeText(await safeTextContent(unhealthyHeading));
      throw new Error(`Ontology Hub returned an unhealthy page after version edit submit: ${headingText || "unknown error page"}`);
    }
  } catch (error) {
    const dialogText = normalizeText(await safeTextContent(dialog));
    const formErrors = normalizeText(await safeTextContent(page.locator("#formErrors, #dialogEditVersionformErrors")));
    throw new Error(
      `${error.message || `Version edit did not complete within 15000ms for '${updatedVersion.name}'.`} ` +
        `Dialog: ${dialogText || "no diagnostic text"}. ` +
        `Form errors: ${formErrors || "none"}`,
    );
  }
}

async function deleteVersion(page, versionName) {
  const versionRow = page.locator(".editionBoxSugg").filter({ hasText: versionName }).first();
  await versionRow.waitFor({ state: "visible", timeout: 5000 });
  await versionRow.locator(".imageVersionActionRemove").click();
  await page.getByRole("button", { name: "Confirm Deletion", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");
  const remaining = page.locator(".editionBoxSugg").filter({ hasText: versionName });
  if ((await remaining.count()) > 0 && (await remaining.first().isVisible().catch(() => false))) {
    throw new Error(`Version '${versionName}' is still visible after deletion.`);
  }
}

async function deleteVocabulary(page, runtime, prefix) {
  await signInToEdition(page, runtime);
  await page.goto(`${runtime.baseUrl}/dataset/vocabs/${encodeURIComponent(prefix)}`, {
    waitUntil: "domcontentloaded",
  });
  await expectHealthyPage(page, "Vocabulary detail");
  await page.locator("#vocabDelete").click();
  await page.getByRole("button", { name: "Confirm Deletion", exact: true }).click();
  await page.waitForLoadState("domcontentloaded");
  await page.goto(`${runtime.baseUrl}/dataset/vocabs?q=${encodeURIComponent(prefix)}`, {
    waitUntil: "domcontentloaded",
  });
  const remaining = page.locator("#SearchGrid").getByText(prefix, { exact: false });
  if ((await remaining.count()) > 0 && (await remaining.first().isVisible().catch(() => false))) {
    throw new Error(`Vocabulary '${prefix}' is still visible in the catalog after deletion.`);
  }
}

async function updateVocabularyMetadata(page, runtime, prefix, patch) {
  await signInToEdition(page, runtime);
  const formPage = new OntologyHubVocabFormPage(page);
  await formPage.gotoEdit(runtime.baseUrl, prefix);
  await formPage.expectReady(prefix);

  if (patch.title) {
    await formPage.ensureTitles("en", "es", patch.title, `${patch.title} ES`);
  }
  if (patch.description) {
    await formPage.ensureDescriptions("en", "es", patch.description, `${patch.description} ES`);
  }
  if (patch.review) {
    await formPage.setReview(patch.review);
  }
  if (patch.tag) {
    await ensureTagSelected(page, patch.tag);
  }

  await saveVocabulary(page);
  await openVocabularyDetail(page, runtime, prefix, patch.title || "");
}

async function saveTextArtifact(testInfo, name, content) {
  const filePath = testInfo.outputPath(name);
  fs.writeFileSync(filePath, content, "utf8");
  return filePath;
}

async function resolveThemisSource(page) {
  return page.locator("#themisVocabContainer").evaluate((node) => ({
    uri: node.getAttribute("data-uri") || "",
    sourceUrl: node.getAttribute("data-source-url") || "",
    prefix: node.getAttribute("data-vocab-prefix") || "",
  }));
}

async function buildThemisExampleFile(page, runtime, sourceUrl, testInfo) {
  const response = await page.request.post(`${runtime.baseUrl}/dataset/api/v2/validators/themis/example`, {
    data: {
      sourceUrl,
    },
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/plain;q=0.9, */*;q=0.8",
    },
  });

  if (!response.ok()) {
    throw new Error(`Themis example generation failed with HTTP ${response.status()}.`);
  }

  const body = await response.text();
  if (!normalizeText(body)) {
    throw new Error("Themis example generation returned an empty payload.");
  }

  return saveTextArtifact(testInfo, "test_cases.txt", body);
}

function resolveThemisTestFile() {
  const explicitPath = normalizeText(process.env.ONTOLOGY_HUB_THEMIS_TEST_FILE);
  const candidates = [
    explicitPath,
    path.resolve(__dirname, "../fixtures/themis/test_cases.txt"),
    path.resolve(__dirname, "../fixtures/themis/test_cases_2_cases.txt"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    "Themis requires the agreed test case file with the two validation cases. " +
      "Set ONTOLOGY_HUB_THEMIS_TEST_FILE or place it at " +
      "'validation/components/ontology_hub/functional/fixtures/themis/test_cases.txt'.",
  );
}

function listZipEntries(filePath) {
  try {
    const output = execFileSync("unzip", ["-l", filePath], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return output
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => /\S/.test(line) && !/^Archive:/.test(line))
      .filter((line) => /[A-Za-z0-9_.-]+\.[A-Za-z0-9]+$/.test(line))
      .map((line) => line.split(/\s+/).pop());
  } catch (error) {
    return [];
  }
}

module.exports = {
  DEFAULT_REPOSITORY_URI,
  DEFAULT_URI,
  buildVocabularyRuntime,
  buildExcelRepositoryVocabularyRuntime,
  buildExcelUriVocabularyRuntime,
  buildThemisExampleFile,
  deleteRunState,
  createAgent,
  createTag,
  createUserForAgent,
  createVersion,
  createVocabularyByUri,
  createVocabularyFromRepository,
  deleteAgentFromPublicDetail,
  deleteTag,
  deleteVersion,
  deleteVocabulary,
  downloadFirstN3,
  editAgentFromPublicDetail,
  editTag,
  editVersion,
  expectHealthyPage,
  listZipEntries,
  loadRunState,
  normalizeText,
  openVocabularyDetail,
  openVersionsPage,
  promoteUserToAdmin,
  persistGeneratedArtifact,
  resolveThemisTestFile,
  REPOSITORY_VOCAB_STATE_KEY,
  resolveThemisSource,
  runtimeFromCreatedVocabulary,
  saveRunState,
  saveTextArtifact,
  signInToEdition,
  signOut,
  assertCreateUserControl,
  updateVocabularyMetadata,
  URI_VOCAB_STATE_KEY,
  VERSION_STATE_KEY,
};
