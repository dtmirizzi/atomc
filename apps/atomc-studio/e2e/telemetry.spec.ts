import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Studio telemetry view", () => {
  test("renders clearly labeled matrix-scan and console telemetry", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Telemetry" }).click();
    await expect(page.getByRole("heading", { name: "Telemetry" })).toBeVisible();
    await expect(page.getByText("Simulated telemetry")).toBeVisible();
    await expect(page.getByText("DEMO DATA")).toBeVisible();
    await expect(page.getByText("Fixture capture")).toBeVisible();
    await expect(page.getByRole("img", { name: /matrix scan timing diagram/i })).toBeVisible();
    await expect(
      page.getByRole("table", { name: /matrix scan event data \(text alternative/i }),
    ).toBeVisible();
    await expect(page.getByRole("log", { name: "Console output" })).toBeVisible();
    await expect(page.getByText(/matrix scan only/i)).toBeVisible();
  });

  test("pause and clear controls are keyboard operable", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Telemetry" }).click();
    const pause = page.getByRole("button", { name: "Pause" });
    await pause.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Resume" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("log", { name: "Console output" })).toHaveAttribute(
      "aria-live",
      "off",
    );
    const clear = page.getByRole("button", { name: "Clear" });
    await clear.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText(/No console lines in this fixture capture/i)).toBeVisible();
  });

  test("has no serious or critical automated accessibility violations", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Telemetry" }).click();
    await expect(page.getByRole("img", { name: /matrix scan timing diagram/i })).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
