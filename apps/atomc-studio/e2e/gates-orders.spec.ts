import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SERIOUS = ["serious", "critical"];

test.describe("Studio gate board", () => {
  test("renders every gate grouped by owning domain", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /good morning, engineer/i })).toBeVisible();
    await page.getByRole("button", { name: "Gate board" }).click();

    await expect(page.getByRole("heading", { name: "Gate board" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Electrical/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Firmware/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Mechanical/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Supply chain/ })).toBeVisible();
    await expect(page.getByText("Matrix scan pin map")).toBeVisible();
    await expect(page.getByRole("progressbar", { name: /Electrical pass rate/ })).toBeVisible();
  });

  test("filters gates and expands real GateResult detail", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Gate board" }).click();

    const resultGroup = page.getByRole("group", { name: "Result" });
    await resultGroup.getByRole("button", { name: /Failed/ }).click();
    await expect(page.getByText("Matrix scan pin map")).toBeVisible();
    await expect(page.getByText("Unconnected pins")).toHaveCount(0);

    const row = page.getByRole("row", { name: /Matrix scan pin map/ });
    await row.getByRole("button", { name: /Details/ }).click();
    await expect(page.getByText("Column pin C13 is absent from the IR")).toBeVisible();
    await expect(page.getByText("art:renode-matrix-scan")).toBeVisible();
    await expect(
      page.getByText("Add C13 to keyboard.matrix.col_pins and re-run the matrix scan."),
    ).toBeVisible();
    await expect(page.getByText("key:K0_12")).toBeVisible();
  });
});

test.describe("Studio sourcing tables", () => {
  test("shows labeled sample BOM rows and the honest unavailable notices", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "BOM & orders" }).click();

    await expect(page.getByRole("heading", { name: /BOM & orders/ })).toBeVisible();
    const bom = page.getByRole("table", { name: "Bill of materials lines" });
    await expect(bom.getByText("STM32F411CEU6")).toBeVisible();
    await expect(bom.getByText("QFN-48_7x7mm")).toBeVisible();

    // The real project has no quote/order data, and no plugin is implemented to produce it.
    await expect(
      page.getByText(
        "The fabrication plugin is not implemented; no PCB or assembly quote data exists.",
      ),
    ).toBeVisible();
    await expect(
      page.getByText("The orders plugin is not implemented; no order data exists."),
    ).toBeVisible();

    // Sample rows are clearly labeled as simulated, and no order action is offered.
    await expect(page.getByText(/simulated fixture data/)).toBeVisible();
    await expect(page.getByRole("button", { name: /place order|buy now|checkout/i })).toHaveCount(
      0,
    );
  });
});

test.describe("Studio gate and sourcing accessibility", () => {
  test("has no serious or critical axe violations on the gate board", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Gate board" }).click();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter((violation) =>
      SERIOUS.includes(violation.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });

  test("has no serious or critical axe violations on the sourcing view", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "BOM & orders" }).click();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter((violation) =>
      SERIOUS.includes(violation.impact ?? ""),
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
  });
});
