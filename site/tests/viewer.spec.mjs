import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";

test.use({ trace: "on-first-retry" });

const guides = {};
for (const key of ["A", "B", "C"]) {
  guides[key] = JSON.parse(await readFile(path.resolve(import.meta.dirname, `../dist/TeoJansen_Rhinoceros/assets/assembly-${key}.json`), "utf8"));
}
const imageHash = (buffer) => createHash("sha256").update(buffer).digest("hex");
const drawn = (page) => page.locator("#camera-stats").getAttribute("data-drawn");
const diagnostic = (page, key) => page.locator("#camera-stats").getAttribute(`data-${key}`);

async function ready(page, design = "A") {
  await page.goto(`viewer.html?design=${design}`);
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText(`${design}案を表示しました`, { timeout: 30_000 });
  await expect(page.locator("#viewer-error")).toBeHidden();
  await expect.poll(() => drawn(page)).toBe(String(guides[design].model.instanceCount));
}

function expectedVisible(guide, position) {
  const step = guide.steps[position];
  const names = new Set(guide.steps.slice(0, position + 1).flatMap((s) => s.add));
  for (const name of step.hidden) names.delete(name);
  for (const name of step.preview) names.add(name);
  return names;
}

test("3D is opt-in and A/B/C load exact source-bound instances independently", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const requests = [];
  const errors = [];
  page.on("request", (request) => requests.push(request.url()));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("viewer.html");
  await expect(page.locator("#viewer-fallback")).toBeVisible();
  expect(requests.some((url) => /\.glb$|viewer-engine|viewer-index|assembly-[ABC]\.json/.test(url))).toBe(false);
  expect(requests.some((url) => /youtube|ytimg|fonts\.google|cdn\.jsdelivr/.test(url))).toBe(false);
  await page.locator("#load-viewer").click();
  for (const design of ["A", "B", "C"]) {
    if (design === "B") {
      let release;
      const gate = new Promise((resolve) => { release = resolve; });
      await page.route("**/assets/ver3-B.glb", async (route) => { await gate; await route.continue(); });
      await page.locator("#design-select").selectOption(design);
      await expect(page.locator("#viewer-workspace")).toHaveJSProperty("inert", true);
      await expect(page.locator("#viewer-workspace")).toHaveAttribute("aria-busy", "true");
      release();
    } else if (design !== "A") await page.locator("#design-select").selectOption(design);
    await expect(page.locator("#viewer-status")).toContainText(`${design}案を表示しました`, { timeout: 30_000 });
    await expect.poll(() => drawn(page)).toBe(String(guides[design].model.instanceCount));
    await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", String(guides[design].model.instanceCount));
    await expect(page.locator("#source-stats")).toContainText(guides[design].revision.revisionId);
    await expect(page.locator("#model-stats")).toContainText(`${Object.keys(guides[design].parts).length} 部品定義`);
    await expect(page.locator("#viewer-workspace")).toHaveJSProperty("inert", false);
    for (const view of ["isometric", "front", "left", "right", "back", "top", "bottom"]) {
      await page.locator(`[data-view="${view}"]`).click();
      let state;
      await expect.poll(async () => {
        state = await page.locator("#camera-stats").evaluate((element) => ({
          angle: Number(element.dataset.angle), polar: Number(element.dataset.polar),
          bounds: JSON.parse(element.dataset.bounds),
        }));
        const { angle, polar } = state;
        if (view === "top") return polar < 0.001;
        if (view === "bottom") return polar > Math.PI - 0.001;
        const expected = { isometric: Math.atan2(1.1, 1.3), front: 0, left: -Math.PI / 2, right: Math.PI / 2, back: Math.PI }[view];
        const expectedPolar = view === "isometric" ? Math.acos(0.75 / Math.hypot(1.1, 0.75, 1.3)) : Math.PI / 2;
        const delta = Math.atan2(Math.sin(angle - expected), Math.cos(angle - expected));
        return Math.abs(delta) < 0.001 && Math.abs(polar - expectedPolar) < 0.001;
      }).toBe(true);
      expect(state.bounds.every((value) => value >= -1 && value <= 1)).toBe(true);
    }
    const loaded = requests.filter((url) => /\.glb$/.test(url)).map((url) => url.split("/").at(-1));
    expect(loaded).toEqual(["A", "B", "C"].slice(0, "ABC".indexOf(design) + 1).map((id) => `ver3-${id}.glb`));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.locator("#reset-view").click();
    await expect.poll(async () => Number(await diagnostic(page, "angle"))).toBeCloseTo(Math.atan2(1.1, 1.3), 3);
    await page.locator("#canvas-host canvas").screenshot({ path: testInfo.outputPath(`published-${design}-model.png`) });
    await page.screenshot({ path: testInfo.outputPath(`published-${design}-viewport.png`) });
  }
  expect(errors).toEqual([]);
});

for (const design of ["A", "B", "C"]) {
  test(`${design} assembly steps render exact mappings and return 0 to full to 0`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await ready(page, design);
    const guide = guides[design];
    await expect(page.locator("#step-select option")).toHaveCount(guide.steps.length);
    await page.locator("#step-first").click();
    await expect.poll(() => drawn(page)).toBe("0");
    await expect(page.locator("#instance-count")).toHaveAttribute("data-coupons", "0");
    await page.locator("#step-next").click();
    await expect.poll(() => drawn(page)).toBe("2");
    await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", "0");
    await expect(page.locator("#stage-title")).toContainText("二つの試験片");
    await page.locator("#part-select").selectOption("Q_BEARING_FIT");
    await expect(page.locator("#part-description")).toContainText("正規組立数量 0 点");
    for (let position = 2; position < guide.steps.length; position += 1) {
      const step = guide.steps[position];
      const visible = expectedVisible(guide, position);
      await page.locator("#step-select").selectOption(String(position));
      await expect(page.locator("#stage-title")).toContainText(step.title);
      await expect.poll(() => drawn(page)).toBe(String(visible.size + step.coupons.length));
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", String(visible.size));
      const targetParts = new Set((step.add.length ? step.add : step.preview).map((name) => guide.instances[name].partId));
      await expect(page.locator("#stage-parts tbody tr")).toHaveCount(targetParts.size);
    }
    await page.locator("#step-complete").click();
    await expect.poll(() => drawn(page)).toBe(String(guide.model.instanceCount));
    for (const inspection of guide.inspections) {
      await page.locator("#access-select").selectOption(inspection.id);
      await expect(page.locator("#stage-title")).toContainText(inspection.title);
      await expect.poll(() => drawn(page)).toBe(String(guide.model.instanceCount - inspection.hidden.length));
      await expect(page.locator("#temporary-note")).toContainText(`${inspection.hidden.length} 点`);
    }
    await page.locator("#step-complete").click();
    await expect.poll(() => drawn(page)).toBe(String(guide.model.instanceCount));
    await page.locator("#step-first").click();
    await expect.poll(() => drawn(page)).toBe("0");
    await expect(page.locator("#step-previous")).toBeDisabled();
  });
}

test("360-degree rotation, pan, zoom and part selection are real", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await ready(page, "C");
  const canvas = page.locator("#canvas-host canvas");
  await page.locator("#reset-view").click();
  await canvas.scrollIntoViewIfNeeded();
  const before = imageHash(await canvas.screenshot());
  if (testInfo.project.name === "desktop") {
    const box = await canvas.boundingBox();
    const angle = await diagnostic(page, "angle");
    await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.45);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.60, box.y + box.height * 0.55, { steps: 5 });
    await page.mouse.up();
    await expect.poll(() => diagnostic(page, "angle")).not.toBe(angle);
    const target = await diagnostic(page, "target");
    await page.mouse.down({ button: "right" });
    await page.mouse.move(box.x + box.width * 0.65, box.y + box.height * 0.6, { steps: 3 });
    await page.mouse.up({ button: "right" });
    await expect.poll(() => diagnostic(page, "target")).not.toBe(target);
    const distance = Number(await diagnostic(page, "distance"));
    await page.mouse.wheel(0, -120);
    await expect.poll(async () => Number(await diagnostic(page, "distance"))).toBeLessThan(distance);
  }
  await page.locator("#reset-view").click();
  await expect.poll(async () => Number(await diagnostic(page, "angle"))).toBeCloseTo(Math.atan2(1.1, 1.3), 3);
  await canvas.focus();
  let angle = Number(await diagnostic(page, "angle"));
  let travelled = 0;
  for (let group = 0; group < 8; group += 1) {
    const previousAngle = angle;
    for (let key = 0; key < 6; key += 1) await page.keyboard.press("ArrowRight");
    await expect.poll(async () => {
      angle = Number(await diagnostic(page, "angle"));
      const delta = angle - (previousAngle + 6 * 0.14);
      return Math.abs(Math.atan2(Math.sin(delta), Math.cos(delta)));
    }).toBeLessThan(0.001);
    travelled += Math.atan2(Math.sin(angle - previousAngle), Math.cos(angle - previousAngle));
  }
  expect(travelled).toBeGreaterThan(2 * Math.PI);
  expect(imageHash(await canvas.screenshot())).not.toBe(before);
  const target = await diagnostic(page, "target");
  await page.keyboard.press("Shift+ArrowRight");
  await expect.poll(() => diagnostic(page, "target")).not.toBe(target);
  const distance = Number(await diagnostic(page, "distance"));
  await page.locator("#zoom-in").click();
  await expect.poll(async () => Number(await diagnostic(page, "distance"))).toBeLessThan(distance);
  await page.locator("#fit-view").click();
  await page.locator("#part-select").selectOption("H_REX_HUB");
  await expect(page.locator("#part-description")).toContainText("購入品");
  await expect(page.locator("#part-description")).toContainText("H_REX_HUB");
  await expect(page.locator("#part-description")).toContainText(`正規組立数量 ${guides.C.parts.H_REX_HUB.quantity} 点`);
  await page.locator("#fit-selection").click();
  await page.locator("#clip-section").check();
  await page.locator("#clip-section").uncheck();
  await page.locator("#clear-selection").click();
  await page.locator("#reset-view").click();
  await canvas.scrollIntoViewIfNeeded();
  const rectangle = await canvas.boundingBox();
  let picked = false;
  for (const [x, y] of [[0.5, 0.5], [0.5, 0.6], [0.4, 0.55], [0.6, 0.55]]) {
    await page.mouse.click(rectangle.x + rectangle.width * x, rectangle.y + rectangle.height * y);
    if ((await page.locator("#part-description").textContent()).includes("インスタンスID")) { picked = true; break; }
  }
  expect(picked).toBe(true);
  await page.locator("#clear-selection").click();
  await page.screenshot({ path: testInfo.outputPath("viewer-C.png") });
  await canvas.screenshot({ path: testInfo.outputPath("viewer-C-canvas.png") });
});

test("mobile touch rotates, pinches and pans the actual 3D camera", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Touch input is checked on the 375px touch project.");
  await ready(page, "B");
  const canvas = page.locator("#canvas-host canvas");
  await canvas.scrollIntoViewIfNeeded();
  const rectangle = await canvas.boundingBox();
  const x = rectangle.x + rectangle.width / 2;
  const y = rectangle.y + rectangle.height / 2;
  const session = await page.context().newCDPSession(page);
  const touch = (type, points) => session.send("Input.dispatchTouchEvent", { type, touchPoints: points });
  const angle = await diagnostic(page, "angle");
  await touch("touchStart", [{ x: x - 45, y, id: 1 }]);
  await touch("touchMove", [{ x, y: y + 10, id: 1 }]);
  await touch("touchMove", [{ x: x + 45, y: y + 20, id: 1 }]);
  await touch("touchEnd", []);
  await expect.poll(() => diagnostic(page, "angle")).not.toBe(angle);
  const distance = Number(await diagnostic(page, "distance"));
  await touch("touchStart", [{ x: x - 25, y, id: 1 }, { x: x + 25, y, id: 2 }]);
  await touch("touchMove", [{ x: x - 55, y, id: 1 }, { x: x + 55, y, id: 2 }]);
  await touch("touchEnd", []);
  await expect.poll(async () => Number(await diagnostic(page, "distance"))).toBeLessThan(distance);
  const target = await diagnostic(page, "target");
  await touch("touchStart", [{ x: x - 25, y, id: 1 }, { x: x + 25, y, id: 2 }]);
  await touch("touchMove", [{ x: x - 10, y: y + 20, id: 1 }, { x: x + 40, y: y + 20, id: 2 }]);
  await touch("touchEnd", []);
  await expect.poll(() => diagnostic(page, "target")).not.toBe(target);
  await session.detach();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("Matrix is complete, its assets load and it links to exact part-group views", async ({ page }, testInfo) => {
  await page.goto("comparison.html");
  await expect(page.locator(".improvement-matrix tbody > tr")).toHaveCount(8);
  await expect(page.locator(".matrix-summary article")).toHaveCount(3);
  await expect(page.locator("main")).toContainText("Bは名目トルク入力も不足");
  for (const image of await page.locator("img").all()) {
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0)).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const region = page.getByRole("region", { name: "Ver.2からVer.3への改良比較表" });
  await region.focus();
  if (testInfo.project.name === "mobile") {
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  }
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("published-matrix.png") });
  await page.getByRole("link", { name: "3Dで軸・金属ハブを見る →" }).click();
  await expect(page).toHaveURL(/viewer\.html\?design=C&focus=connection$/);
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText("C案を表示しました");
  await expect(page.locator("#stage-operation")).toContainText("Matrixの対象");
});

test("3D keyboard, reduced motion and accessibility preserve static instructions", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("viewer.html");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "本文へ移動" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText("A案を表示しました");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe("auto");
  const angle = await diagnostic(page, "angle");
  await page.locator("#canvas-host canvas").focus();
  await expect(page.locator("#canvas-host canvas")).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => diagnostic(page, "angle")).not.toBe(angle);
  await page.keyboard.press("Home");
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
  await page.locator("#canvas-host").screenshot({ path: testInfo.outputPath("viewer-A.png") });
});

test("missing or mismatched GLB is an explicit failure with static/CAD fallback", async ({ page }) => {
  for (const failure of ["missing", "wrong-hash"]) {
    await page.route("**/assets/ver3-A.glb", (route) => route.fulfill({
      status: failure === "missing" ? 503 : 200, contentType: "model/gltf-binary", body: "not the canonical GLB",
    }));
    await page.goto("viewer.html");
    await page.locator("#load-viewer").click();
    await expect(page.locator("#viewer-error")).toBeVisible();
    await expect(page.locator("#viewer-error")).toContainText(failure === "missing" ? "HTTP 503" : "ハッシュ");
    await expect(page.locator("#viewer-workspace")).toBeHidden();
    await expect(page.locator("#viewer-fallback")).toBeVisible();
    await expect(page.locator("#viewer-fallback a[href$='.step']")).toHaveCount(3);
    await expect(page.locator("#guide-A-5")).toContainText("風車");
    await page.unroute("**/assets/ver3-A.glb");
  }
});

test("no WebGL or a lost WebGL context exposes a useful fallback", async ({ page, browser, baseURL }) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return /^webgl/.test(type) ? null : getContext.call(this, type, ...args);
    };
  });
  const blocked = await context.newPage();
  await blocked.goto(new URL("viewer.html", baseURL).href);
  await blocked.locator("#load-viewer").click();
  await expect(blocked.locator("#viewer-error")).toContainText("WebGL");
  await expect(blocked.locator("#viewer-fallback")).toBeVisible();
  await context.close();
  await ready(page);
  await page.locator("canvas").evaluate((canvas) => {
    const context = canvas.getContext("webgl2");
    const extension = context.getExtension("WEBGL_lose_context");
    if (!extension) throw new Error("Missing context-loss test support");
    extension.loseContext();
  });
  await expect(page.locator("#viewer-error")).toContainText("コンテキストが失われました");
  await expect(page.locator("#viewer-fallback")).toBeVisible();
  await expect(page.locator("#viewer-workspace")).toBeHidden();
});

test("all three concrete guides and download links work without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(new URL("viewer.html#assembly-guides", baseURL).href);
  await expect(page.locator("#load-viewer")).toBeHidden();
  for (const design of ["A", "B", "C"]) {
    await expect(page.locator(`#guide-${design} h3`)).toContainText(`${design}案`);
    await expect(page.locator(`#guide-${design} a[href$='BOM_${design}.csv']`)).toHaveCount(1);
    const titles = await page.locator(`#guide-${design} > .static-step > h4`).allTextContents();
    expect(titles).toEqual([...guides[design].steps.slice(1).map((step) => `${step.id} · ${step.title}`),
      `14 · ${guides[design].disassembly.title}`]);
  }
  await page.locator("#guide-A-4").scrollIntoViewIfNeeded();
  await page.locator("#guide-A-4 .step-bom summary").click();
  await expect(page.locator("#guide-A-4 table")).toContainText("P_INPUT_CARRIAGE");
  await context.close();
});
