import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("production journey is discoverable and every stage anchor works", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("./");
  await page.locator("#ver1").getByRole("link", { name: "写真でたどるVer.1の製作工程 →" }).click();
  await expect(page).toHaveURL(/production\.html#ver1$/);
  await expect(page.locator("#ver1 h2")).toBeInViewport();
  for (const id of ["research", "design", "printing", "sanding", "cleaning", "painting", "decals", "assembly", "ver1-test"]) {
    await page.getByRole("navigation", { name: "Ver.1工程一覧" }).locator(`a[href="#${id}"]`).click();
    await expect(page.locator(`#${id} h3`).first()).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
  await page.getByRole("navigation", { name: "製作記録の目次" }).getByRole("link", { name: "02 · Ver.2へ直す" }).click();
  await expect(page.locator("#ver2 h2")).toBeInViewport();
  await expect(page.locator("#ver2")).toContainText("Ver.2専用の研磨・塗装の全工程");
  for (const version of [1, 2]) {
    await expect(page.locator(`#ver${version}-gallery img`)).toHaveCount(6);
  }
  await page.getByRole("link", { name: "Ver.3の三案と、現在の検証限界へ" }).click();
  await expect(page).toHaveURL(/index\.html#ver3$/);
  await expect(page.locator("#ver3-warning")).toBeVisible();
  expect(errors).toEqual([]);
});

test("authentic stage media loads without third-party requests or hidden layout overflow", async ({ page }, testInfo) => {
  const requested = [];
  const failed = [];
  page.on("request", (request) => requested.push(request.url()));
  page.on("requestfailed", (request) => failed.push(request.url()));
  const response = await page.goto("production.html");
  expect(response.status()).toBe(200);
  await expect(page).toHaveTitle(/Ver.1・Ver.2 製作記録/);
  expect(requested.some((url) => /youtube|ytimg|fonts\.google|\.(mp4|gif)(\?|$)/.test(url))).toBe(false);
  expect(await page.locator("iframe, video").count()).toBe(0);
  await page.getByText("風車を上から見た形状の違い", { exact: true }).click();
  for (const image of await page.locator("img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0)).toBe(true);
    await expect(image).toHaveAttribute("loading", "lazy");
    expect(await image.evaluate((element) => element.naturalWidth === Number(element.getAttribute("width"))
      && element.naturalHeight === Number(element.getAttribute("height")))).toBe(true);
  }
  const missing = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')]
    .map((link) => link.hash.slice(1)).filter((id) => !document.getElementById(id)));
  expect(missing).toEqual([]);
  expect(failed).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("production.html#top");
  await expect(page.locator("h1")).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath("production-intro.png") });
  for (const id of ["painting", "v2-gears", "ver2-gallery"]) {
    await page.locator(`#${id}`).screenshot({
      path: testInfo.outputPath(`${id}.png`),
      style: ".site-header { visibility: hidden; }",
    });
  }
});

test("production remains keyboard-accessible, reduced-motion and contrast-safe", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("production.html");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "本文へ移動" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  const link = page.getByRole("link", { name: "1 情報収集", exact: true });
  await link.focus();
  expect(await link.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#research$/);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
});

test("production photo failures expose sources and the record works without JavaScript", async ({ page, browser, baseURL }) => {
  await page.route("**/assets/making-printer.webp", (route) => route.abort());
  await page.goto("production.html#printing");
  await expect(page.locator("#printing .media-error")).toBeVisible();
  await expect(page.locator("#printing figcaption a")).toHaveAttribute("href", /88187\.jpg$/);
  const context = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await context.newPage();
  await staticPage.goto(new URL("production.html#resources", baseURL).href);
  await expect(staticPage.locator("#resources h2")).toBeVisible();
  await expect(staticPage.locator("#resources a[href*='.pdf']")).toHaveCount(2);
  await expect(staticPage.locator("#ver1-gallery img")).toHaveCount(6);
  await expect(staticPage.locator("#ver2-gallery img")).toHaveCount(6);
  await context.close();
});
