import { expect, Page } from "@playwright/test";

import { clickMarked, fillMarked } from "../../shared/utils/live-marker";

type KeycloakLoginConfig = {
  portalUser: string;
  portalPassword: string;
  skipLogin: boolean;
};

export class KeycloakLoginPage {
  constructor(
    private readonly page: Page,
    private readonly config: KeycloakLoginConfig,
  ) {}

  async open(baseUrl: string): Promise<void> {
    await this.page.goto(baseUrl, { waitUntil: "networkidle" });
  }

  async loginIfNeeded(): Promise<void> {
    if (this.config.skipLogin) {
      return;
    }

    if ((await this.page.locator("text=Log out").count()) > 0) {
      return;
    }

    const usernameInput = this.page
      .locator("#username, input[name='username'], input[autocomplete='username']")
      .first();
    const passwordInput = this.page
      .locator("#password, input[name='password'], input[type='password']")
      .first();

    if ((await usernameInput.count()) === 0 || (await passwordInput.count()) === 0) {
      throw new Error("Could not find Keycloak login inputs on the page");
    }

    if (!this.config.portalUser || !this.config.portalPassword) {
      throw new Error("Missing PORTAL_USER or PORTAL_PASSWORD for Keycloak login");
    }

    await fillMarked(usernameInput, this.config.portalUser);
    await fillMarked(passwordInput, this.config.portalPassword);

    const submitButton = this.page
      .locator("#kc-login, button[type='submit'], input[type='submit']")
      .first();

    await Promise.all([
      this.page.waitForLoadState("networkidle"),
      clickMarked(submitButton),
    ]);
  }

  async expectLoggedIn(): Promise<void> {
    await expect(this.page.locator("text=Log out").first()).toBeVisible({
      timeout: 60_000,
    });
  }
}
