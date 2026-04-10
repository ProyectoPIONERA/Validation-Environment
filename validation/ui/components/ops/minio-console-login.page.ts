import { Page } from "@playwright/test";

import { clickMarked, fillMarked } from "../../shared/utils/live-marker";

type MinioConsoleCredentials = {
  username: string;
  password: string;
};

export class MinioConsoleLoginPage {
  constructor(private readonly page: Page) {}

  async open(bucketBrowserUrl: string): Promise<void> {
    await this.page.goto(bucketBrowserUrl, {
      waitUntil: "networkidle",
    });
  }

  async loginIfNeeded(credentials: MinioConsoleCredentials): Promise<void> {
    const usernameInput = this.page
      .locator(
        "#accessKey, input[name='accessKey'], input[placeholder*='Access Key'], input[autocomplete='username']",
      )
      .first();
    const passwordInput = this.page
      .locator("#secretKey, input[name='secretKey'], input[type='password']")
      .first();

    if ((await usernameInput.count()) === 0 || (await passwordInput.count()) === 0) {
      return;
    }

    await fillMarked(usernameInput, credentials.username);
    await fillMarked(passwordInput, credentials.password);

    const submitButton = this.page
      .locator("button[type='submit'], input[type='submit'], button")
      .filter({ hasText: /login|sign in|signin/i })
      .first();

    await Promise.all([
      this.page.waitForLoadState("networkidle"),
      clickMarked(submitButton),
    ]);
  }
}
