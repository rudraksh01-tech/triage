import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("listbox", { name: "Tickets" })).toBeVisible();
});

test("falls back to sample data when no gateway is configured", async ({ page }) => {
  await expect(page.getByRole("status").filter({ hasText: "Sample data" })).toBeVisible();
  expect(await page.getByRole("option").count()).toBeGreaterThan(10);
});

test("j/k moves the selection and the detail follows", async ({ page }) => {
  const options = page.getByRole("option");
  await expect(options.first()).toHaveAttribute("aria-selected", "true");

  await page.keyboard.press("j");
  await page.keyboard.press("j");
  await expect(options.nth(2)).toHaveAttribute("aria-selected", "true");

  const handle = await options.nth(2).locator(".font-mono").first().textContent();
  await expect(page.locator("article header")).toContainText(handle!);

  await page.keyboard.press("k");
  await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
});

test("queue filters match their counts", async ({ page }) => {
  const nav = page.getByRole("navigation", { name: "Queues" });
  const high = nav.getByRole("button", { name: /High priority/ });
  const expected = Number(await high.locator(".font-mono").textContent());

  await high.click();
  await expect(high).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("option")).toHaveCount(expected);
  for (const bar of await page.getByLabel("high priority").all()) await expect(bar).toBeVisible();
});

test("routing panel explains the decision", async ({ page }) => {
  await expect(page.getByRole("meter", { name: "Model confidence" })).toBeVisible();
  await expect(page.locator("article")).toContainText(/accepted without calling the LLM|passed on|budget/);
});

test("theme toggle cycles and survives a reload", async ({ page }) => {
  const toggle = page.getByRole("button", { name: /^Theme:/ });
  await toggle.click(); // system -> light
  await toggle.click(); // light -> dark
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("results page renders charts with a keyboard-reachable readout", async ({ page }) => {
  await page.getByRole("link", { name: /How it was measured/ }).click();
  await expect(page.getByRole("heading", { name: "How the cascade was measured" })).toBeVisible();

  const chart = page.getByRole("img", { name: /^Category:/ });
  test.skip((await chart.count()) === 0, "results.json has no cascade curve yet");
  await chart.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("status").filter({ hasText: "accuracy with cascade" }).first()).toBeVisible();
});
