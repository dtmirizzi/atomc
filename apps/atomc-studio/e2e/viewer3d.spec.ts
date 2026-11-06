import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Studio 3D viewer", () => {
  test("renders derived geometry with an honest data-source label", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "3D viewer" }).click();
    await expect(page.getByRole("heading", { name: "3D viewer" })).toBeVisible();
    await expect(page.getByText("Simulated geometry.")).toBeVisible();
    await expect(page.getByText(/no daemon, CAD export or build artifact was read/i)).toBeVisible();
    await expect(page.getByLabel("Derived geometry summary")).toBeVisible();
    await expect(page.getByText("80 × 80 × 1.60 mm")).toBeVisible();
    await expect(page.getByText("9 switches · 15 test pads")).toBeVisible();
    // Headless Chromium exposes software WebGL, so the canvas must be present,
    // not the no-WebGL fallback note.
    await expect(page.locator(".viewer3d__stage canvas")).toHaveCount(1);
    await expect(page.getByRole("note")).toHaveCount(0);
  });

  test("has no serious or critical accessibility violations on the 3D view", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "3D viewer" }).click();
    await expect(page.getByText("Simulated geometry.")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
