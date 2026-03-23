import { expect, Page } from "@playwright/test";

export class MinioBucketBrowserPage {
  constructor(private readonly page: Page) {}

  async expectReady(bucketName: string): Promise<void> {
    const escaped = bucketName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    await expect(this.page).toHaveURL(new RegExp(`/browser/${escaped}`), {
      timeout: 30_000,
    });
    await expect(this.page.getByText(bucketName, { exact: false }).first()).toBeVisible({
      timeout: 30_000,
    });
  }

  async assertNoBucketPermissionError(): Promise<void> {
    await expect(
      this.page.getByText(/You require additional permissions in order to view Objects in this bucket/i),
    ).not.toBeVisible({
      timeout: 2_000,
    });
  }

  async expectObjectVisible(objectName: string, timeoutMs = 15_000): Promise<void> {
    await expect(this.page.getByText(objectName, { exact: false }).first()).toBeVisible({
      timeout: timeoutMs,
    });
  }
}
