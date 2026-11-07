import { expect, test } from "@playwright/test";

test("list and detail are separate screens on a phone", async ({ page }) => {
  await page.goto("/");
  const list = page.getByRole("listbox", { name: "Tickets" });
  await expect(list).toBeVisible();
  await expect(page.locator("article")).toBeHidden();

  await page.getByRole("option").nth(3).getByRole("button").click();
  await expect(page.locator("article")).toBeVisible();
  await expect(list).toBeHidden();

  await page.getByRole("button", { name: "Back to list" }).click();
  await expect(list).toBeVisible();
});

test("no horizontal scroll", async ({ page }) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
