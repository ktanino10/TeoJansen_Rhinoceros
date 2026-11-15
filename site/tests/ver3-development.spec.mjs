import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const locale of ["ja", "en"]) {
  const prefix = locale === "en" ? "en/" : "";
  test(`Ver3 development ${locale}: complete A, changed parts and retained trial`, async ({ page }, testInfo) => {
    const errors = [];
    const requests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => requests.push(request.url()));
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${prefix}development.html`);
    await expect(page.locator('a[href="production.html"]').first()).toBeVisible();
    await page.locator('a[href="ver3-4.html"]').click();
    await expect(page.locator("main")).toHaveAttribute("data-public-version", "3.4");
    await expect(page.locator("body")).toHaveAttribute("data-viewer-catalog", "assets/a34-viewer-index.json");
    expect(requests.some(url => /a34-A\.glb/.test(url))).toBe(false);
    await expect(page.locator('a[href$="/m3_a34/print-list.csv"]').first()).toBeVisible();
    await page.locator("#load-viewer").click();
    await expect(page.locator("#canvas-host canvas")).toBeVisible();
    await expect(page.locator("#instance-count")).toContainText("754 / 754");
    await expect(page.locator("#source-stats")).toContainText("v3.4-a-m3-r1");
    const before = await page.locator("#camera-stats").textContent();
    await page.locator("#canvas-host canvas").press("ArrowRight");
    await expect.poll(() => page.locator("#camera-stats").textContent()).not.toBe(before);
    await page.locator("#step-select").selectOption("3");
    await page.locator("#part-select").selectOption("P_M34_SYNC_DRIVE");
    await expect(page.locator("#part-description")).toContainText("P_M34_SYNC_DRIVE");
    await page.locator("#fit-selection").click();
    await page.locator("#step-first").click();
    await expect(page.locator("#instance-count")).toContainText("0 / 754");
    await page.locator("#step-next").click();
    await expect(page.locator("#stage-parts")).toContainText("Q_SLEEVE_FIT");
    await page.locator("#step-complete").click();
    await expect(page.locator("#instance-count")).toContainText("754 / 754");
    if (locale === "en") {
      expect((await page.locator("body").innerText()).replaceAll("日本語", "")).not.toMatch(/[ぁ-ヿ㐀-鿿]/);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.locator("#viewer").screenshot({ path: testInfo.outputPath(`ver3-4-${locale}.png`) });
    await page.goto(`${prefix}ver3-2.html#viewer`);
    await page.locator("#load-viewer").click();
    await expect(page.locator("#instance-count")).toContainText("22 / 22");
    await expect(page.locator("#source-stats")).toContainText("v3.2-m3-r1-bench");
    expect(errors).toEqual([]);
  });
}

test("Ver3 development: failed model retains real sections and source files", async ({ page }) => {
  await page.route("**/assets/a34-A.glb.gz", route => route.abort());
  await page.goto("ver3-4.html?design=C#viewer");
  await expect(page.locator("#design-select")).toHaveValue("A");
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-error")).toBeVisible();
  await expect(page.locator("#viewer-workspace")).toBeHidden();
  await expect(page.locator("#viewer-fallback img")).toBeVisible();
  await expect(page.locator('a[href$="/Walker_A_3_4.FCStd"]').first()).toHaveAttribute("href", /^https:\/\/github\.com\//);
});

test("Ver3 development: print and purchase sources work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  try {
    await page.goto((process.env.SITE_URL || "http://127.0.0.1:4173/TeoJansen_Rhinoceros/") + "en/ver3-4.html");
    await expect(page.locator("h1")).toContainText("Ver.3.4");
    await expect(page.locator('a[href$="/m3_a34/print-list.csv"]').first()).toBeVisible();
    await expect(page.locator('a[href$="/m3_a34/purchase-list.csv"]').first()).toBeVisible();
    await expect(page.locator("#assembly h3")).toHaveCount(9);
  } finally {
    await context.close();
  }
});
