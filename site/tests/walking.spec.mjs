import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.use({ trace: "on-first-retry" });
const remote = Boolean(process.env.SITE_URL);
const loadTimeout = remote ? 90_000 : 45_000;
const numeric = async (page, field) => Number(await page.locator("#walk-stats").getAttribute(`data-${field}`));
async function load(page, design = "C") {
  await page.goto(`walking.html?design=${design}#walking`);
  await page.locator("#walk-load").click();
  await expect(page.locator("#walk-status")).toContainText(`${design}案の連続歩行を読み込みました`, { timeout: loadTimeout });
}
async function scrub(page, degrees) {
  await page.locator("#walk-phase").evaluate((element, value) => {
    element.value = String(value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, degrees);
  await expect.poll(() => numeric(page, "phase")).toBeCloseTo(degrees, 4);
}

test("r7 walking opt-in loads each full walker; play pause phase speed and reset really change the scene", async ({ page }, testInfo) => {
  test.setTimeout(remote ? 300_000 : 150_000);
  const requests = [], errors = [];
  page.on("request", request => requests.push(request.url()));
  page.on("pageerror", error => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("index.html#ver3");
  await page.locator('#current-C a[href^="walking.html?"]').click();
  await expect(page).toHaveURL(/walking\.html\?design=C#walking$/);
  expect(requests.some(url => /walking-engine|r7-walk-[ABC]\.json|r7-[ABC]\.glb|\.mp4$/.test(url))).toBe(false);
  await page.locator("#walk-load").click();
  for (const design of ["C", "A", "B"]) {
    if (design !== "C") await page.locator("#walk-design").selectOption(design);
    await expect(page.locator("#walk-status")).toContainText(`${design}案の連続歩行を読み込みました`, { timeout: loadTimeout });
    await expect.poll(() => numeric(page, "drawn")).toBe(design === "B" ? 785 : 750);
    await expect(page.locator("#walk-play")).toHaveAttribute("aria-pressed", "false");
    const initial = await page.locator("#walk-stats").getAttribute("data-crank");
    await page.locator("#walk-play").click();
    await expect.poll(() => numeric(page, "seconds")).toBeGreaterThan(.3);
    await expect(page.locator("#walk-status")).toContainText("再生中");
    await page.locator("#walk-play").click();
    await expect(page.locator("#walk-play")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#walk-status")).toContainText("停止中");
    await expect.poll(() => page.locator("#walk-stats").getAttribute("data-playing")).toBe("false");
    const stopped = await numeric(page, "seconds");
    await page.waitForTimeout(250);
    expect(await numeric(page, "seconds")).toBe(stopped);
    expect(await page.locator("#walk-stats").getAttribute("data-crank")).not.toBe(initial);
    await page.locator("#walk-cycle").click();
    await page.locator("#walk-speed").selectOption("1");
    await expect(page.locator("#walk-timing")).toContainText("時間倍率1×");
    await scrub(page, 120);
    const input = Number(await page.locator("#walk-stats").getAttribute("data-input-angle"));
    expect(input).toBeCloseTo((design === "B" ? -1 : 1) * 720 * await numeric(page, "seconds"), 6);
    expect(Math.abs(input)).toBeGreaterThan(({ A: 144, B: 512, C: 156 })[design] * 360);
    await page.locator("#walk-reset").click();
    await expect.poll(() => numeric(page, "seconds")).toBe(0);
    await expect.poll(() => numeric(page, "forward")).toBe(0);
    await page.locator("#walk-speed").selectOption("16");
    await expect(page.locator("#walk-timing")).toContainText("時間圧縮16×");
    await page.locator("#walk-phase").focus();
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => numeric(page, "phase")).toBeCloseTo(.1, 5);
    await page.locator("#walk-canvas").screenshot({ path: testInfo.outputPath(`walking-${design}.png`) });
  }
  expect(requests.filter(url => /r7-[ABC]\.glb\.gz$/.test(url)).map(url => url.split("/").at(-1)))
    .toEqual(["r7-C.glb.gz", "r7-A.glb.gz", "r7-B.glb.gz"]);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("r7 walking keyboard camera overlays and four-cycle advance remain accessible on desktop and mobile", async ({ page }, testInfo) => {
  test.setTimeout(remote ? 180_000 : 90_000);
  await load(page);
  for (let i = 0; i < 4; i++) await page.locator("#walk-cycle").click();
  await expect.poll(() => numeric(page, "forward")).toBeGreaterThan(369);
  await expect(page.locator("#walk-seconds")).toContainText("312.0");
  await page.locator("#walk-forces").check();
  await page.locator("#walk-paths").check();
  await page.locator("#walk-guards").uncheck();
  const angled = await page.locator("#walk-stats").getAttribute("data-camera");
  await page.locator("#walk-side").click();
  await expect.poll(() => page.locator("#walk-stats").getAttribute("data-camera")).not.toBe(angled);
  await page.locator("#walk-guards").check();
  await page.locator("#walk-three-quarter").click();
  const canvas = page.locator("#walk-canvas canvas");
  await canvas.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("+");
  await page.keyboard.press("Home");
  if (testInfo.project.use.hasTouch) {
    await canvas.scrollIntoViewIfNeeded();
    const before = await page.locator("#walk-stats").getAttribute("data-camera");
    const rect = await canvas.boundingBox(), client = await page.context().newCDPSession(page);
    const point = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, id: 1 };
    await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point] });
    await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ ...point, x: point.x + 60 }] });
    await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await expect.poll(() => page.locator("#walk-stats").getAttribute("data-camera")).not.toBe(before);
    await client.detach();
    await canvas.focus();
  }
  await page.keyboard.press("Space");
  await expect(page.locator("#walk-play")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Space");
  await expect(page.locator("#walk-play")).toHaveAttribute("aria-pressed", "false");
  await page.locator("#walk-reset").click();
  await expect.poll(() => numeric(page, "forward")).toBe(0);
  await page.locator("#walk-phase").focus();
  await page.keyboard.press("End");
  await expect(page.locator("#walk-phase-label")).toHaveText("360.0°");
  await expect.poll(() => numeric(page, "forward")).toBeCloseTo(92.38813489623945, 5);
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => numeric(page, "phase")).toBeCloseTo(359.9, 5);
  expect(await numeric(page, "forward")).toBeLessThan(93);
  await page.keyboard.press("Home");
  await expect.poll(() => numeric(page, "forward")).toBe(0);
  await scrub(page, 240);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  await canvas.screenshot({ path: testInfo.outputPath("walking-C-contact-paths.png") });
});

test("r7 walking actual new movies have Japanese captions and decode only after a user action", async ({ page }, testInfo) => {
  const requested = [];
  page.on("request", request => requested.push(request.url()));
  await page.goto("walking.html#walking-films");
  await expect(page.locator("video")).toHaveCount(3);
  expect(requested.some(url => /\.mp4$/.test(url))).toBe(false);
  for (const design of ["C", "A", "B"]) {
    const video = page.locator(`#r7-walking-${design}`);
    await expect(video).toHaveAttribute("preload", "none");
    await expect(video.locator("track")).toHaveAttribute("srclang", "ja");
    await page.getByRole("button", { name: `${design}案の連続歩行を再生`, exact: true }).click();
    await expect.poll(() => video.evaluate(v => !v.paused && v.currentTime > .05)).toBe(true);
    expect(await video.evaluate(v => [v.videoWidth, v.videoHeight])).toEqual([960, 720]);
    await page.getByRole("button", { name: `${design}案の連続歩行を一時停止`, exact: true }).click();
    await expect.poll(() => video.evaluate(v => v.paused)).toBe(true);
  }
  await page.locator("#walking-film-C").screenshot({ path: testInfo.outputPath("walking-C-movie.png"), style: ".site-header,.skip-link{visibility:hidden}" });
});

test("r7 walking refuses corrupt motion and shows an explicit recoverable error", async ({ page }) => {
  await page.route("**/assets/r7-walk-C.json", route => route.fulfill({ status: 200, contentType: "application/json", body: '{"schemaVersion":1}' }));
  await page.goto("walking.html");
  await page.locator("#walk-load").click();
  await expect(page.locator("#walk-error")).toContainText("ハッシュ");
  await expect(page.locator("#walk-workspace")).toBeHidden();
  await expect(page.locator("#walk-load")).toBeEnabled();
  await expect(page.locator("#walk-scope")).toContainText("実機合格0");
});

test("r7 walking WebGL loss pauses instead of claiming continued playback", async ({ page }) => {
  await load(page);
  await page.locator("#walk-play").click();
  await expect.poll(() => numeric(page, "seconds")).toBeGreaterThan(.1);
  await page.locator("#walk-canvas canvas").evaluate(canvas => {
    const gl = canvas.getContext("webgl2");
    const extension = gl.getExtension("WEBGL_lose_context");
    if (!extension) throw new Error("WebGL context loss test extension unavailable");
    extension.loseContext();
  });
  await expect(page.locator("#walk-error")).toContainText("WebGLコンテキスト");
  await expect(page.locator("#walk-play")).toHaveAttribute("aria-pressed", "false");
});

test("r7 walking no-JavaScript page keeps source scope, native video controls and downloads", async ({ browser }, testInfo) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: testInfo.project.use.viewport });
  try {
    const page = await context.newPage();
    await page.goto(new URL("walking.html", testInfo.project.use.baseURL).href);
    await expect(page.locator("noscript p")).toBeVisible();
    await expect(page.locator("noscript p")).toContainText("MP4");
    await expect(page.locator("#walk-load")).toBeHidden();
    await expect(page.locator("#walking-method")).toContainText("表示専用の仮定");
    await expect(page.getByRole("link", { name: "歩行MP4をダウンロード" })).toHaveCount(3);
  } finally { await context.close(); }
});
