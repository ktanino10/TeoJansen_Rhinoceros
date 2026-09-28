import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import path from "node:path";

test.use({ trace: "on-first-retry" });
const guides = {};
for (const d of ["A", "B", "C"]) guides[d] = JSON.parse(await readFile(
  path.resolve(import.meta.dirname, `../dist/TeoJansen_Rhinoceros/assets/r7-assembly-${d}.json`), "utf8",
));

test("r7 public corrected revision loads all three exact models and retains the prior pages", async ({ page }) => {
  test.setTimeout(120_000);
  const requests = [], errors = [];
  page.on("request", r => requests.push(r.url()));
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("r7.html");
  await expect(page.locator("#r7-status")).toContainText("床是正版");
  expect(requests.some(url => /r7-[ABC]\.glb\.gz|\.mp4$/.test(url))).toBe(false);
  await page.locator("#load-viewer").click();
  for (const d of ["A", "B", "C"]) {
    if (d !== "A") await page.locator("#design-select").selectOption(d);
    await expect(page.locator("#viewer-status")).toContainText(`${d}案を表示しました`, { timeout: 40_000 });
    await expect.poll(() => page.locator("#camera-stats").getAttribute("data-drawn")).toBe(String(guides[d].model.instanceCount));
    await expect(page.locator("#step-select option")).toHaveCount(13);
    await page.locator("#step-first").click();
    await expect.poll(() => page.locator("#camera-stats").getAttribute("data-drawn")).toBe("0");
    await page.locator("#step-complete").click();
    await expect.poll(() => page.locator("#camera-stats").getAttribute("data-drawn")).toBe(String(guides[d].model.instanceCount));
  }
  expect(requests.filter(url => /r7-[ABC]\.glb\.gz$/.test(url)).map(url => url.split("/").at(-1)))
    .toEqual(["r7-A.glb.gz", "r7-B.glb.gz", "r7-C.glb.gz"]);
  expect(errors).toEqual([]);
  await page.getByRole("navigation", { name: "表示版を選ぶ" }).getByRole("link", { name: "第一カット・360°／組立履歴" }).click();
  await expect(page).toHaveURL(/viewer\.html$/);
  await expect(page.locator("main")).toContainText("全案で接地残差3 mm目標は未達");
});

test("r7 public corrected bench order and stable IDs do not reintroduce old foot hardware", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("r7.html?design=A");
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText("A案を表示しました");
  await page.locator("#step-select").selectOption("11");
  const stage = guides.A.steps[11];
  const bench = stage.frames.findIndex(f => f.kind === "foot-bench");
  await page.locator("#r7-operation-select").selectOption(String(bench));
  await expect(page.locator("#stage-tools")).toContainText("DN-03");
  const state = JSON.parse(await page.locator("#r7-inventory").textContent());
  expect(state.scene).toBe("isolated_preassembly");
  expect(state.displayedIds).toEqual(stage.footFirstBenchSubassemblies[0].instances.slice().sort());
  expect(state.displayedIds.some(id => state.installedOnMachineIds.includes(id))).toBe(false);
  await page.locator("#part-select").selectOption("H_LOCK_NUT_M2");
  await expect(page.locator("#part-description")).toContainText("M2ナイロン");
  await page.locator("#step-select").selectOption("7");
  await page.locator("#r7-path-select").selectOption("front_basket_and_rotor_lower");
  const end = guides.A.steps[7].frames.findIndex(f => f.pathId === "front_basket_and_rotor_lower" && f.distanceMm === 0);
  await page.locator("#r7-operation-select").selectOption(String(end));
  const first = JSON.parse(await page.locator("#r7-inventory").textContent());
  await page.locator("#r7-operation-next").click();
  const next = JSON.parse(await page.locator("#r7-inventory").textContent());
  expect(next.temporaryOffsetsMm).toEqual(first.temporaryOffsetsMm);
  expect(next.fixedIds).toEqual(first.fixedIds);
  await page.locator("#step-complete").click();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.locator("#canvas-host canvas").screenshot({ path: testInfo.outputPath("r7-corrected-A.png") });
});

test("r7 public media is source-bound opt-in assembly, with nine limited diagnostic images", async ({ page }, testInfo) => {
  await page.goto("r7.html#r7-media");
  await expect(page.locator("video")).toHaveCount(6);
  await expect(page.getByRole("button", { name: /歩行.*再生/ })).toHaveCount(0);
  const video = page.locator("#r7-assembly-B");
  await expect(video).toHaveAttribute("preload", "none");
  await page.getByRole("button", { name: "B案の組立を再生", exact: true }).click();
  await expect.poll(() => video.evaluate(v => !v.paused && v.currentTime > 0)).toBe(true);
  await page.getByRole("button", { name: "B案の組立を一時停止", exact: true }).click();
  for (const d of ["A", "B", "C"]) {
    await page.locator(`#diagnostic-${d} > summary`).click();
    for (const image of await page.locator(`#diagnostic-${d} img`).all()) {
      await image.scrollIntoViewIfNeeded();
      await expect.poll(() => image.evaluate(i => i.complete && i.naturalWidth > 0)).toBe(true);
    }
  }
  await expect(page.locator("#r7-diagnostics")).toContainText("未計算の足部品は省略");
  await expect(page.locator("#r7-diagnostics img")).toHaveCount(9);
  await page.locator("#diagnostic-C").screenshot({ path: testInfo.outputPath("r7-corrected-diagnostics-C.png"), style: ".site-header,.skip-link{visibility:hidden}" });
});

test("r7 public loader accepts HTTP-decoded gzip only when the canonical GLB hash matches", async ({ page }) => {
  const body = await readFile(path.resolve(import.meta.dirname, "../dist/TeoJansen_Rhinoceros/assets/r7-A.glb.gz"));
  await page.route("**/assets/r7-A.glb.gz", route => route.fulfill({
    status: 200, headers: { "content-type": "model/gltf-binary", "content-encoding": "gzip" }, body,
  }));
  await page.goto("r7.html?design=A");
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText("A案を表示しました", { timeout: 40_000 });
  await expect(page.locator("#viewer-error")).toBeHidden();
  await expect.poll(() => page.locator("#camera-stats").getAttribute("data-drawn")).toBe("750");
});
