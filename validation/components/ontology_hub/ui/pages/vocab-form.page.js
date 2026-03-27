class OntologyHubVocabFormPage {
  constructor(page) {
    this.page = page;
    this.form = page.locator("#TheForm");
    this.formErrors = page.locator("#formErrors");
    this.saveButton = page.locator(".editionSaveButtonRight");
  }

  async gotoEdit(baseUrl, prefix) {
    await this.page.goto(`${baseUrl}/edition/vocabs/${encodeURIComponent(prefix)}`, {
      waitUntil: "domcontentloaded",
    });
  }

  async expectReady(prefix = "") {
    const prefixInput = this.page.locator("#inputVocabPrefix");
    await prefixInput.waitFor({ state: "visible", timeout: 20000 });
    await this.titleFields().first().waitFor({ state: "visible", timeout: 20000 });
    if (prefix) {
      const currentPrefix = ((await prefixInput.inputValue().catch(() => "")) || "").trim();
      if (currentPrefix && currentPrefix !== prefix) {
        throw new Error(
          `Se esperaba editar el vocabulario '${prefix}', pero el formulario cargo '${currentPrefix}'.`,
        );
      }
    }
  }

  titleFields() {
    return this.page.locator("textarea[name^='titles']");
  }

  descriptionFields() {
    return this.page.locator("textarea[name^='descriptions']");
  }

  titleLanguageSelects() {
    return this.page.locator("select[name^='titles']");
  }

  descriptionLanguageSelects() {
    return this.page.locator("select[name^='descriptions']");
  }

  async ensureMultilingualFields(fieldKind, primaryLanguage, secondaryLanguage) {
    const addButton =
      fieldKind === "titles"
        ? this.page.locator(".fieldWithLangAddActionTitle")
        : this.page.locator(".fieldWithLangAddActionDescription");
    const selects =
      fieldKind === "titles" ? this.titleLanguageSelects() : this.descriptionLanguageSelects();

    if ((await selects.count()) === 0) {
      await addButton.click();
    }
    if ((await selects.count()) < 2) {
      await addButton.click();
    }

    const primary = String(primaryLanguage || "").trim().toLowerCase();
    const secondary = String(secondaryLanguage || "").trim().toLowerCase();

    if (primary) {
      await selects.first().selectOption(primary);
    }
    if (secondary && (await selects.count()) > 1) {
      await selects.nth(1).selectOption(secondary);
    }
  }

  async ensureTitles(primaryLanguage, secondaryLanguage, primaryValue, secondaryValue) {
    await this.ensureMultilingualFields("titles", primaryLanguage, secondaryLanguage);
    await this.titleFields().first().fill(primaryValue);
    if ((await this.titleFields().count()) > 1 && secondaryValue) {
      await this.titleFields().nth(1).fill(secondaryValue);
    }
  }

  async ensureDescriptions(primaryLanguage, secondaryLanguage, primaryValue, secondaryValue) {
    await this.ensureMultilingualFields("descriptions", primaryLanguage, secondaryLanguage);
    await this.descriptionFields().first().fill(primaryValue);
    if ((await this.descriptionFields().count()) > 1 && secondaryValue) {
      await this.descriptionFields().nth(1).fill(secondaryValue);
    }
  }

  async setReview(reviewText) {
    const reviews = this.page.locator("textarea[name^='reviews']");
    if ((await reviews.count()) === 0) {
      await this.page.locator(".fieldReviewAddAction").click();
    }
    await this.page.locator("textarea[name^='reviews']").first().fill(reviewText);
  }

  async currentTitleLanguages() {
    return this.titleLanguageSelects().evaluateAll((nodes) =>
      nodes
        .map((node) => String(node.value || "").trim().toLowerCase())
        .filter(Boolean),
    );
  }

  async currentDescriptionLanguages() {
    return this.descriptionLanguageSelects().evaluateAll((nodes) =>
      nodes
        .map((node) => String(node.value || "").trim().toLowerCase())
        .filter(Boolean),
    );
  }

  async save() {
    const signalTimeoutMs = 12000;
    const responsePromise = this.page
      .waitForResponse(
        (response) =>
          ["POST", "PUT"].includes(response.request().method()) &&
          /\/edition\/vocabs\/[^/]+\/?$/.test(new URL(response.url()).pathname),
        { timeout: signalTimeoutMs },
      )
      .catch(() => null);
    const redirectPromise = this.page
      .waitForURL(/\/dataset\/vocabs\/[^/]+\/?$/, { timeout: signalTimeoutMs })
      .then(() => true)
      .catch(() => false);

    await this.saveButton.click();

    const response = await Promise.race([
      responsePromise,
      redirectPromise.then(() => null),
      this.page.waitForTimeout(2500).then(() => null),
    ]);
    const responseBody = response ? await response.text().catch(() => "") : "";
    let responsePayload = null;
    try {
      responsePayload = responseBody ? JSON.parse(responseBody) : null;
    } catch (error) {
      responsePayload = null;
    }

    let redirected = await Promise.race([
      redirectPromise,
      this.page.waitForTimeout(1500).then(() => false),
    ]);
    const redirectTarget =
      responsePayload && typeof responsePayload === "object"
        ? String(responsePayload.redirect || "").trim()
        : "";
    if (!redirected && redirectTarget && !/^500$/i.test(redirectTarget)) {
      await this.page.goto(new URL(redirectTarget, this.page.url()).toString(), {
        waitUntil: "domcontentloaded",
      });
      redirected = true;
    }

    return {
      redirected,
      responseStatus: response ? response.status() : 0,
      responseBody,
      redirectTarget,
      finalUrl: this.page.url(),
    };
  }

  async readFormErrors() {
    const content = await this.page
      .evaluate(() => document.querySelector("#formErrors")?.textContent || "")
      .catch(() => "");
    return String(content).replace(/\s+/g, " ").trim();
  }
}

module.exports = {
  OntologyHubVocabFormPage,
};
