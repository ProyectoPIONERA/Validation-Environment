const { test, expect } = require("../fixtures");

test("OH-LOGIN: admin can sign in and reach the edition area", async ({
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
  await page.locator(".createVocab").waitFor({ state: "visible" });
  await captureStep(page, "01-edition-login");

  await attachJson("oh-login-report", {
    user: ontologyHubRuntime.adminEmail,
    url: page.url(),
  });
});
