function isEnabled() {
  const raw = process.env.PLAYWRIGHT_INTERACTION_MARKERS;
  if (!raw) {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(String(raw).trim().toLowerCase());
}

function markerDelayMs() {
  const raw = process.env.PLAYWRIGHT_INTERACTION_MARKER_DELAY_MS;
  const value = Number(raw ?? "350");
  return Number.isFinite(value) && value >= 0 ? value : 350;
}

async function highlight(locator) {
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

async function clickMarked(locator, options) {
  await highlight(locator);
  await locator.click(options);
}

async function fillMarked(locator, value, options) {
  await highlight(locator);
  await locator.fill(value, options);
}

async function selectOptionMarked(locator, values, options) {
  await highlight(locator);
  await locator.selectOption(values, options);
}

async function setInputFilesMarked(locator, files, options) {
  await highlight(locator);
  await locator.setInputFiles(files, options);
}

async function checkMarked(locator, options) {
  await highlight(locator);
  await locator.check(options);
}

module.exports = {
  checkMarked,
  clickMarked,
  fillMarked,
  highlightMarked: highlight,
  selectOptionMarked,
  setInputFilesMarked,
};
