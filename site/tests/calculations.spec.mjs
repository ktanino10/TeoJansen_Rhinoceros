import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

const manifest = JSON.parse(await readFile(path.resolve(import.meta.dirname, "../../docs/ver3/commercial_basis_r3/manifest.json"), "utf8"));

test("calculation page separates revisions and loads only selected candidate diagrams", async ({ page }, testInfo) => {
  const requests = [];
  const errors = [];
  page.on("request", (r) => requests.push(r.url()));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("calculations.html");
  await expect(page).toHaveTitle(/材料・構造・流体の計算/);
  await expect(page.locator("#calculation-gate")).toContainText("qualifiedPrototypeCount = 0");
  await expect(page.locator(".version-boundary")).toContainText("ver3-first-cut-2026-09-26");
  await expect(page.locator(".version-boundary")).toContainText(manifest.revisionId);
  expect(requests.some((url) => /calculation-.*-[BC]\.svg/.test(url))).toBe(false);
  expect(requests.some((url) => /\.glb|viewer-engine|youtube|fonts\.google/.test(url))).toBe(false);
  for (const design of ["A", "B", "C"]) {
    await page.locator("#analysis-select").selectOption(design);
    await expect(page).toHaveURL(new RegExp(`#analysis-${design}$`));
    await expect(page.locator(`#analysis-${design}`)).toBeVisible();
    for (const other of ["A", "B", "C"].filter((id) => id !== design)) {
      await expect(page.locator(`#analysis-${other}`)).toBeHidden();
    }
    const images = page.locator(`#analysis-${design} img`);
    await expect(images).toHaveCount(design === "C" ? 5 : 4);
    for (const image of await images.all()) {
      await image.scrollIntoViewIfNeeded();
      await expect.poll(() => image.evaluate((e) => e.complete && e.naturalWidth > 0)).toBe(true);
    }
    await expect(page.locator(`[data-result="${design}"]`)).toContainText("0/27");
    await expect(page.locator(`[data-result="${design}"]`)).toContainText("UNKNOWN");
  }
  for (const image of await page.locator("#shared-linkage img, #shared-interface img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((e) => e.complete && e.naturalWidth > 0)).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(errors).toEqual([]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("calculations.html#analysis-C");
  await expect(page.locator("#analysis-C")).toBeVisible();
  await page.locator("#analysis-C > summary").scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("calculation-C.png") });
});

test("calculation figures enlarge at true pixels with keyboard focus and readable mobile labels", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("calculations.html");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "本文へ移動" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  const trigger = page.locator("#figure-deflection_A [data-enlarge]");
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "A案 · 支点・荷重と部材のたわみ" });
  await expect(dialog).toBeVisible();
  const image = dialog.locator("img");
  await expect.poll(() => image.evaluate((e) => e.complete && e.naturalWidth === 1200)).toBe(true);
  expect(await image.evaluate((e) => e.getBoundingClientRect().width)).toBe(1200);
  await dialog.getByRole("button", { name: "200%", exact: true }).click();
  expect(await image.evaluate((e) => e.getBoundingClientRect().width)).toBe(2400);
  await expect(page.locator("#figure-zoom-status")).toContainText("変形拡大倍率は変更していません");
  const viewport = page.locator("#figure-viewport");
  await viewport.focus();
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => viewport.evaluate((e) => e.scrollLeft)).toBeGreaterThan(0);
  await dialog.getByRole("button", { name: "全体表示", exact: true }).click();
  expect(await image.evaluate((e) => e.clientWidth <= e.parentElement.clientWidth + 1)).toBe(true);
  await dialog.getByRole("button", { name: "100%", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("calculation-enlarged.png") });
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
});

test("calculation original SVGs and data links have the exact frozen source hashes", async ({ page, request, baseURL }) => {
  await page.goto("calculations.html#sources");
  for (const figure of manifest.figures) {
    const filename = `assets/calculation-${path.basename(figure.file).replaceAll("_", "-")}`;
    const response = await request.get(new URL(filename, baseURL).href);
    expect(response.status()).toBe(200);
    expect(createHash("sha256").update(await response.body()).digest("hex")).toBe(manifest.artifactHashes[figure.file]);
  }
  for (const filename of ["comparison.json", "comparison.csv", "torque_decomposition.csv", "manifest.json"]) {
    const source = await readFile(path.resolve(import.meta.dirname, "../../docs/ver3/commercial_basis_r3", filename));
    const response = await request.get(new URL(`assets/calculation-${filename.replaceAll("_", "-")}`, baseURL).href);
    expect(response.status()).toBe(200);
    expect(createHash("sha256").update(await response.body()).digest("hex"))
      .toBe(createHash("sha256").update(source).digest("hex"));
  }
  const popupPromise = page.waitForEvent("popup");
  await page.locator("#figure-bearing_interface a[href$='.svg'][target='_blank']").click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup.locator("svg")).toBeVisible();
  await popup.close();
});

test("calculation data remains usable without scripts and figure failures expose sources", async ({ page, browser, baseURL }) => {
  await page.route("**/assets/calculation-deflection-A.svg", (route) => route.abort());
  await page.goto("calculations.html#analysis-A");
  await page.locator("#figure-deflection_A").scrollIntoViewIfNeeded();
  await expect(page.locator("#figure-deflection_A .media-error")).toBeVisible();
  await expect(page.locator("#figure-deflection_A a[href*='github.com'][href$='.svg']")).toHaveCount(1);
  const context = await browser.newContext({ javaScriptEnabled: false, reducedMotion: "reduce" });
  const staticPage = await context.newPage();
  await staticPage.goto(new URL("calculations.html", baseURL).href);
  await expect(staticPage.locator("#analysis-choice")).toBeHidden();
  await staticPage.locator("#analysis-B > summary").click();
  await expect(staticPage.locator("#analysis-B .analysis-design-body")).toBeVisible();
  await expect(staticPage.locator("#analysis-B")).toContainText("125:1");
  await expect(staticPage.locator("#analysis-B img")).toHaveCount(4);
  await expect(staticPage.locator("#analysis-B [data-enlarge]").first()).toBeHidden();
  await expect(staticPage.locator("#analysis-B a[target='_blank']")).toHaveCount(4);
  await context.close();
});
