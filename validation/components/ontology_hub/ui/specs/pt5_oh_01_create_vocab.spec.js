const { test, expect } = require("../fixtures");

test("PT5-OH-01: vocabulary can be created from URI and become visible in the catalog", async ({
  page,
  ontologyHubRuntime,
  captureStep,
  attachJson,
}) => {
  await page.goto(`${ontologyHubRuntime.baseUrl}/edition`, { waitUntil: "networkidle" });

  if (/\/edition\/login\/?$/.test(page.url())) {
    await page.getByPlaceholder("Email").fill(ontologyHubRuntime.adminEmail);
    await page.getByPlaceholder("Password").fill(ontologyHubRuntime.adminPassword);
    await page.getByRole("button", { name: "Log In it!", exact: true }).click();
  }

  if (!/\/edition\/?$/.test(page.url())) {
    await page.getByRole("link", { name: "Edition", exact: true }).click();
  }

  await expect(page).toHaveURL(new RegExp("/edition/?$"));

  await page.locator(".createVocab").click();
  await page.locator("#dialogCreateVocab").waitFor({ state: "visible" });
  await page.getByText("Create Vocabulary by URI", { exact: true }).waitFor({ state: "visible" });
  await page.locator("#formDialogCreateVocabFromURI input[name='uri']").fill(
    ontologyHubRuntime.creationUri,
  );
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.waitForLoadState("networkidle");

  const duplicateError = page.locator(".alert-error").filter({ hasText: "This vocabulary already exists" });
  const createHeader = page.getByRole("heading", { name: "Create a new Vocabulary", exact: true });

  if (await createHeader.isVisible()) {
    if (!(await page.locator("#inputVocabUri").inputValue()).trim()) {
      await page.locator("#inputVocabUri").fill(ontologyHubRuntime.creationUri);
    }
    if (!(await page.locator("#inputVocabNsp").inputValue()).trim()) {
      await page.locator("#inputVocabNsp").fill(ontologyHubRuntime.creationNamespace);
    }
    if (!(await page.locator("#inputVocabPrefix").inputValue()).trim()) {
      await page.locator("#inputVocabPrefix").fill(ontologyHubRuntime.creationPrefix);
    }

    if ((await page.locator("textarea[name^='titles']").count()) === 0) {
      await page.locator(".fieldWithLangAddActionTitle").click();
    }
    await page.locator("textarea[name^='titles']").first().fill(ontologyHubRuntime.creationTitle);

    if ((await page.locator("textarea[name^='descriptions']").count()) === 0) {
      await page.locator(".fieldWithLangAddActionDescription").click();
    }
    await page
      .locator("textarea[name^='descriptions']")
      .first()
      .fill(ontologyHubRuntime.creationDescription);

    if ((await page.locator("#tagsUl input[name='tags[]']").count()) === 0) {
      await page.locator(".fieldTagsAddAction").click();
      await page.locator("#listOfTags").waitFor({ state: "visible" });
      await page.locator("#tagsPickerList .tagFromList").filter({
        hasText: ontologyHubRuntime.creationTag,
      }).first().click();
      await page.keyboard.press("Escape");
    }

    if ((await page.locator("textarea[name^='reviews']").count()) === 0) {
      await page.locator(".fieldReviewAddAction").click();
    }
    await page.locator("textarea[name^='reviews']").first().fill(ontologyHubRuntime.creationReview);

    await captureStep(page, "01-create-vocabulary-form");
    await page.locator(".editionSaveButtonRight").click();
    let created = true;
    try {
      await expect(page).toHaveURL(new RegExp("/dataset/vocabs/[^/]+/?$"), { timeout: 15000 });
      await page.locator("section#posts").getByText("Metadata", { exact: true }).waitFor({
        state: "visible",
      });
      await captureStep(page, "02-created-vocabulary-detail");
    } catch (error) {
      created = false;
      await page.locator("#formErrors").filter({
        hasText: `Prefix ${ontologyHubRuntime.creationPrefix} is already used`,
      }).waitFor({ state: "visible" });
      await captureStep(page, "02-vocabulary-prefix-already-exists");
    }

    await attachJson("pt5-oh-01-create-outcome", {
      created,
      duplicateByPrefix: !created,
      intermediateUrl: page.url(),
    });
  } else {
    await duplicateError.waitFor({ state: "visible" });
    await captureStep(page, "01-vocabulary-already-exists");
  }

  await page.goto(
    `${ontologyHubRuntime.baseUrl}/dataset/vocabs?q=${encodeURIComponent(ontologyHubRuntime.creationPrefix)}`,
    { waitUntil: "networkidle" },
  );
  await page.locator("#SearchGrid").waitFor({ state: "visible" });
  await page.locator("#SearchGrid").getByText(ontologyHubRuntime.creationPrefix, {
    exact: false,
  }).first().waitFor({ state: "visible" });
  await captureStep(page, "03-created-vocabulary-listed");

  await attachJson("pt5-oh-01-report", {
    creationUri: ontologyHubRuntime.creationUri,
    creationPrefix: ontologyHubRuntime.creationPrefix,
    finalUrl: page.url(),
    duplicateHandled: await duplicateError.isVisible(),
  });
});
