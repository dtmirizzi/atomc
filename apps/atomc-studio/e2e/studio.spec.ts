import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Studio preview workspace", () => {
  test("renders a usable, keyboard-navigable workspace", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /good morning, engineer/i })).toBeVisible();
    await expect(page.getByText("Preview workspace")).toBeVisible();
    await expect(page.getByRole("button", { name: /run build/i })).toBeDisabled();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus-visible")).toHaveCount(1);
  });

  test("has no serious or critical automated accessibility violations", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Preview workspace")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });

  test("gate filters and details are operable in browser", async ({ page }) => {
    await page.goto("/");
    const gates = page.getByRole("table", { name: "Verification gates" }).first();
    await page
      .getByRole("tab", { name: /failed/i })
      .first()
      .click();
    await expect(gates.getByRole("button", { name: /matrix scan pin map/i })).toBeVisible();
    await gates.getByRole("button", { name: /matrix scan pin map/i }).click();
    await expect(page.getByRole("dialog", { name: "Matrix scan pin map" })).toBeVisible();
    await page.getByRole("button", { name: /close gate details/i }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("keeps the dashboard readable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /good morning, engineer/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Toggle navigation" })).toBeVisible();
    const bodyWidth = await page.locator("body").evaluate((element) => element.scrollWidth);
    expect(bodyWidth).toBeLessThanOrEqual(390);
  });
});
