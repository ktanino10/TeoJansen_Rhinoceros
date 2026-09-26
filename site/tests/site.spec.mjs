import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import path from "node:path";

const canonical = JSON.parse(await readFile(
  path.resolve(import.meta.dirname, "../../docs/ver3/comparison.json"), "utf8",
));

test("versions, source-bound metrics and repository-subpath navigation", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto("./");
  expect(response.status()).toBe(200);
  await expect(page).toHaveTitle(/リノセウス/);
  await expect(page.locator("html")).toHaveAttribute("lang", "ja");
  await expect(page.locator("h1")).toContainText("歩く仕組み");
  for (const [name, hash] of [["Ver.1", "ver1"], ["Ver.2", "ver2"], ["Ver.3", "ver3"], ["資料・ダウンロード", "downloads"]]) {
    await page.getByRole("navigation", { name: "メインナビゲーション" }).getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`#${hash}$`));
    await expect(page.locator(`#${hash} h2`)).toBeInViewport();
  }
  for (const record of canonical.designs) {
    const row = record.comparison;
    const card = page.locator(`#prototype-${row.prototype}`);
    await expect(card).toContainText(`${row.rotor_diameter_mm} × ${row.rotor_span_mm} mm`);
    await expect(card).toContainText(`${row.reduction} : 1`);
    await expect(card).toContainText(`${row.maximum_single_episode_material_anchor_drift_mm.toFixed(2)} mm`);
    await expect(card).toContainText("3 mm目標未達");
    await expect(card).toContainText(`${row.time_scale}倍表示`);
  }
  await expect(page.locator("#prototype-B")).toContainText("名目トルク入力も不足");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  const sourceLinks = await page.locator("#downloads a[href*='github.com']").evaluateAll(
    (elements) => elements.map((element) => element.href),
  );
  expect(sourceLinks.length).toBeGreaterThan(20);
  expect(sourceLinks.every((url) => url.includes("ktanino10/TeoJansen_Rhinoceros/"))).toBe(true);
  expect(sourceLinks.filter((url) => url.includes("/raw/")).every((url) => /\/raw\/[a-f0-9]{40}\//.test(url))).toBe(true);
  expect(errors).toEqual([]);
});

test("images load, videos are opt-in and play after a user action", async ({ page }) => {
  const requested = [];
  page.on("request", (request) => requested.push(request.url()));
  await page.goto("./");
  await expect(page.locator(".hero img")).toBeVisible();
  expect(requested.some((url) => /\.(mp4|gif)(\?|$)/.test(url))).toBe(false);
  expect(requested.some((url) => /youtube|ytimg|fonts\.google/.test(url))).toBe(false);
  for (const image of await page.locator("img:visible").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0)).toBe(true);
  }
  await page.locator(".image-detail summary").click();
  const designImage = page.locator(".image-detail img");
  await designImage.scrollIntoViewIfNeeded();
  await expect.poll(() => designImage.evaluate((image) => image.complete && image.naturalWidth > 0)).toBe(true);
  for (const ident of ["A", "B", "C"]) {
    const video = page.locator(`#walking_${ident}`);
    await expect(video).toHaveAttribute("preload", "none");
    await expect(video).toHaveAttribute("playsinline", "");
    expect(await video.getAttribute("autoplay")).toBeNull();
    await page.getByRole("button", { name: `${ident}案の歩行を再生`, exact: true }).click();
    await expect.poll(() => video.evaluate((element) => !element.paused && element.currentTime > 0)).toBe(true);
    expect(await video.evaluate((element) => element.videoWidth)).toBe(960);
    await page.getByRole("button", { name: `${ident}案の歩行を一時停止`, exact: true }).click();
    await expect.poll(() => video.evaluate((element) => element.paused)).toBe(true);
  }
});

test("reduced motion, keyboard access and contrast", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("./");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "本文へ移動" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await expect(page.locator("#gif-preview")).toHaveAttribute("src", "assets/comparison.webp");
  await expect(page.locator("#motion-preference")).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  const gif = page.getByRole("button", { name: "歩行GIFを再生（33秒・約2.9 MB）", exact: true });
  await gif.focus();
  expect(await gif.evaluate((button) => getComputedStyle(button).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.locator("#gif-toggle")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#gif-preview")).toHaveAttribute("src", "assets/walk_preview.gif");
  await page.getByRole("button", { name: "GIFを停止して静止画に戻す" }).click();
  await expect(page.locator("#gif-preview")).toHaveAttribute("src", "assets/comparison.webp");
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
  await page.goto("./#top");
  await page.screenshot({ path: testInfo.outputPath("showcase.png") });
  await page.locator("#prototype-A").screenshot({ path: testInfo.outputPath("prototype-A.png") });
});

test("media failures expose a useful source link instead of silent success", async ({ page }) => {
  await page.route("**/assets/hero.webp", (route) => route.abort());
  await page.route("**/assets/walking_A.mp4", (route) => route.abort());
  await page.goto("./");
  await expect(page.locator(".hero-visual .media-error")).toBeVisible();
  await expect(page.locator(".hero-visual figcaption a")).toHaveAttribute("href", /github\.com/);
  await page.getByRole("button", { name: "A案の歩行を再生", exact: true }).click();
  await expect(page.locator("#prototype-A .video-card .media-error")).toBeVisible();
  await expect(page.locator("#prototype-A .video-card a")).toHaveAttribute("href", /walking_A\.mp4$/);
});

test("static content and downloads work without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto(baseURL);
  await expect(page.locator("#ver1 h2")).toBeVisible();
  await expect(page.locator("#ver2 h2")).toBeVisible();
  await expect(page.locator("#ver3-warning")).toBeVisible();
  await expect(page.getByRole("link", { name: "番号付き組立手順・ベンチ確認票", exact: true })).toHaveAttribute("href", /ASSEMBLY_ja\.md$/);
  await expect(page.locator("#walking_A")).toHaveAttribute("controls", "");
  await context.close();
});
