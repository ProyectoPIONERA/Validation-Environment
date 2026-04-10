import { Locator } from "@playwright/test";

function isEnabled(): boolean {
  const raw = process.env.PLAYWRIGHT_INTERACTION_MARKERS;
  if (!raw) {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

function markerDelayMs(): number {
  const raw = process.env.PLAYWRIGHT_INTERACTION_MARKER_DELAY_MS;
  const value = Number(raw ?? "350");
  return Number.isFinite(value) && value >= 0 ? value : 350;
}

async function highlight(locator: Locator): Promise<void> {
  if (!isEnabled()) {
    return;
  }

  try {
    await locator.highlight();
  } catch {
    return;
  }

  const delayMs = markerDelayMs();
  if (delayMs > 0) {
    await locator.page().waitForTimeout(delayMs);
  }
}

export async function clickMarked(locator: Locator, options?: Parameters<Locator["click"]>[0]): Promise<void> {
  await highlight(locator);
  await locator.click(options);
}

export async function fillMarked(locator: Locator, value: string, options?: Parameters<Locator["fill"]>[1]): Promise<void> {
  await highlight(locator);
  await locator.fill(value, options);
}

export async function pressMarked(locator: Locator, key: string, options?: Parameters<Locator["press"]>[1]): Promise<void> {
  await highlight(locator);
  await locator.press(key, options);
}

export async function setInputFilesMarked(
  locator: Locator,
  files: Parameters<Locator["setInputFiles"]>[0],
  options?: Parameters<Locator["setInputFiles"]>[1],
): Promise<void> {
  await highlight(locator);
  await locator.setInputFiles(files, options);
}
