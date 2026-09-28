import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import path from "node:path";

const guides = {};
for (const key of ["A", "B", "C"]) {
  guides[key] = JSON.parse(await readFile(path.resolve(import.meta.dirname, `../dist/r7-preview/TeoJansen_Rhinoceros/assets/r7-assembly-${key}.json`), "utf8"));
}
test.use({ trace: "off" });
const counts = (page) => page.locator("#camera-stats").getAttribute("data-drawn");
async function frameState(page) {
  return JSON.parse(await page.locator("#r7-inventory").textContent());
}
async function ready(page, design) {
  await page.goto(`r7.html?design=${design}`);
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText(`${design}案を表示しました`, { timeout: 45_000 });
  await expect(page.locator("#viewer-error")).toBeHidden();
  await expect.poll(() => counts(page)).toBe(String(guides[design].model.instanceCount));
}

test("r7 is a separate lazy revision with exact A/B/C inventory and local download links", async ({ page, request, baseURL }) => {
  const requested = [];
  const errors = [];
  page.on("request", (r) => requested.push(r.url()));
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto("r7.html");
  await expect(page.locator("#r7-status")).toContainText("qualifiedWalkingPrototypeCount=0");
  await expect(page.locator("#r7-status")).toContainText("未公開");
  expect(requested.some((url) => /r7-[ABC]\.glb|viewer-engine|r7-assembly/.test(url))).toBe(false);
  expect(requested.some((url) => /walking_.*\.mp4/.test(url))).toBe(false);
  await page.locator("#load-viewer").click();
  for (const key of ["A", "B", "C"]) {
    if (key !== "A") await page.locator("#design-select").selectOption(key);
    await expect(page.locator("#viewer-status")).toContainText(`${key}案を表示しました`, { timeout: 45_000 });
    await expect.poll(() => counts(page)).toBe(String(guides[key].model.instanceCount));
    await expect(page.locator("#step-select option")).toHaveCount(13);
    await expect(page.locator("#instance-count")).toHaveAttribute("data-installed", String(guides[key].model.instanceCount));
    expect(requested.filter((url) => /r7-[ABC]\.glb\.gz$/.test(url)).map((url) => url.split("/").at(-1)))
      .toEqual(["A", "B", "C"].slice(0, "ABC".indexOf(key) + 1).map((id) => `r7-${id}.glb.gz`));
    for (const resource of ["bom", "canonical", "stages"]) {
      const response = await request.get(new URL(guides[key].links[resource], baseURL).href);
      expect(response.status()).toBe(200);
    }
  }
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.getByRole("navigation", { name: "表示版を選ぶ" }).getByRole("link", { name: "第一カット・360°／組立履歴" }).click();
  await expect(page).toHaveURL(/viewer\.html$/);
  await expect(page.locator("main")).toContainText("全案で接地残差3 mm目標は未達");
  await expect(page.locator(".r7-local-banner")).toContainText("公開履歴");
  await page.locator(".r7-local-banner a").click();
  await expect(page).toHaveURL(/r7\.html$/);
});

for (const design of ["A", "B", "C"]) {
  test(`r7 ${design} displays all twelve ordered stage inventories and canonical path sample poses`, async ({ page }, testInfo) => {
    test.setTimeout(180_000);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await ready(page, design);
    const guide = guides[design];
    await page.locator("#step-first").click();
    await expect.poll(() => counts(page)).toBe("0");
    for (let stageIndex = 1; stageIndex <= 12; stageIndex += 1) {
      const stage = guide.steps[stageIndex];
      await page.locator("#step-select").selectOption(String(stageIndex));
      await expect(page.locator("#stage-title")).toContainText(stage.title);
      const endIndex = stage.frames.length - 1;
      await page.locator("#r7-operation-select").selectOption(String(endIndex));
      await expect(page.locator("#instance-count")).toHaveAttribute("data-frame", stage.frames[endIndex].id);
      await expect.poll(() => counts(page)).toBe(String(guide.inventories[stage.frames[endIndex].inventory].length));
      expect((await frameState(page)).installedOnMachineIds).toEqual(guide.inventories[stage.frames[endIndex].installedInventory]);
      const significant = stage.frames.map((frame, i) => [frame, i]).filter(([frame, index]) => {
        if (["remove", "reinsert", "preparation", "temporary-pose", "temporary-pose-restored"].includes(frame.kind)) return true;
        if (frame.kind !== "path-sample") return false;
        const samples = guide.paths[frame.pathId].distancesMm;
        return frame.distanceMm === samples[0] || frame.distanceMm === samples.at(-1);
      });
      for (const [frame, index] of significant) {
        await page.locator("#r7-operation-select").selectOption(String(index));
        await expect(page.locator("#instance-count")).toHaveAttribute("data-frame", frame.id);
        await expect.poll(() => counts(page)).toBe(String(guide.inventories[frame.inventory].length));
        const state = await frameState(page);
        expect(state.displayedIds).toEqual(guide.inventories[frame.inventory]);
        expect(state.installedOnMachineIds).toEqual(guide.inventories[frame.installedInventory]);
        expect(state.temporaryOffsetsMm).toEqual(frame.offsets);
        expect(state.removedSameIds).toEqual(frame.removed);
        if (frame.kind === "path-sample") {
          expect(state.fixedIds).toEqual(frame.fixedIds);
          expect(state.movingIds).toEqual(frame.movingIds);
        }
      }
    }
    await page.locator("#step-complete").click();
    await expect.poll(() => counts(page)).toBe(String(guide.model.instanceCount));
    await page.locator("#canvas-host canvas").screenshot({ path: testInfo.outputPath(`r7-${design}-complete.png`) });
    await page.locator("#step-first").click();
    await expect.poll(() => counts(page)).toBe("0");
    await expect(page.locator("#step-previous")).toBeDisabled();
  });
}

test("r7 B preserves installed PET and fasteners during both connected insertion segments", async ({ page }, testInfo) => {
  await ready(page, "B");
  await page.locator("#step-select").selectOption("7");
  await page.locator("#r7-path-select").selectOption("front_basket_and_rotor_lower");
  const stage = guides.B.steps[7];
  const end = stage.frames.findIndex((f) => f.pathId === "front_basket_and_rotor_lower" && f.distanceMm === 0);
  await page.locator("#r7-operation-select").selectOption(String(end));
  const before = await frameState(page);
  expect(before.fixedIds).toHaveLength(276);
  for (const id of ["S_GUARD_UPPER_RIGHT_2_001", "H_BOLT_M3_20_011", "H_BOLT_M3_20_012"]) expect(before.fixedIds).toContain(id);
  for (const id of before.movingIds) expect(before.temporaryOffsetsMm[id]).toEqual([4, 0, 0]);
  await page.locator("#r7-operation-next").click();
  const joined = await frameState(page);
  expect(joined.pathId).toBe("front_basket_axial_seat");
  expect(joined.movingIds).toEqual(before.movingIds);
  expect(joined.fixedIds).toEqual(before.fixedIds);
  expect(joined.temporaryOffsetsMm).toEqual(before.temporaryOffsetsMm);
  await page.locator("#canvas-host canvas").screenshot({ path: testInfo.outputPath("r7-B-continuous-join.png") });
  await page.locator("#step-select").selectOption("4");
  await page.locator("#r7-path-select").selectOption("upper_pet_from_below");
  const upper = await frameState(page);
  for (const id of ["H_MAIN_HEX100_001", "H_MAIN_HEX100_002", "H_MAIN_HEX100_003"]) {
    expect(upper.fixedIds).toContain(id);
    expect(upper.temporaryOffsetsMm[id]).toEqual([-53, 0, 0]);
  }
  expect(upper.temporaryOffsetsMm.S_GUARD_UPPER_RIGHT_2_001).toEqual([0, -4, -300]);
  await page.locator("#part-select").selectOption("H_MAIN_HEX100");
  await expect(page.locator("#part-description")).toContainText("100 mm主六角軸");
  await page.locator("#fit-selection").click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("r7 controls stay keyboard accessible and all views, zoom and part selection remain real", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("r7.html?design=C");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "本文へ移動" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-status")).toContainText("C案を表示しました");
  const canvas = page.locator("#canvas-host canvas");
  await canvas.focus();
  const angle = await page.locator("#camera-stats").getAttribute("data-angle");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => page.locator("#camera-stats").getAttribute("data-angle")).not.toBe(angle);
  for (const view of ["left", "right", "front", "back", "top", "bottom", "isometric"]) {
    await page.locator(`[data-view="${view}"]`).click();
    await expect.poll(async () => {
      const bounds = JSON.parse(await page.locator("#camera-stats").getAttribute("data-bounds"));
      return bounds.every((value) => value >= -1 && value <= 1);
    }).toBe(true);
  }
  await page.locator("#part-select").selectOption("H_INPUT_HUB");
  await expect(page.locator("#part-description")).toContainText("購入品");
  await page.locator("#fit-selection").click();
  await page.locator("#clip-section").check();
  await page.locator("#clip-section").uncheck();
  await page.locator("#clear-selection").click();
  await page.locator("#reset-view").click();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("r7-C-viewer.png") });
});

test("r7 missing model data has local source fallback rather than old media", async ({ page }) => {
  await page.route("**/assets/r7-A.glb.gz", (route) => route.fulfill({ status: 503, body: "unavailable" }));
  await page.goto("r7.html");
  await page.locator("#load-viewer").click();
  await expect(page.locator("#viewer-error")).toContainText("HTTP 503");
  await expect(page.locator("#viewer-fallback")).toBeVisible();
  await expect(page.locator("#viewer-fallback img")).toHaveCount(3);
  expect(await page.locator("video").count()).toBe(0);
  await expect(page.locator("#r7-guide-B a[href$='.step']")).toHaveAttribute("href", /^r7-files\//);
});

test("r7 instructions and local files are readable without JavaScript", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(new URL("r7.html#r7-guides", baseURL).href);
  await expect(page.locator("#load-viewer")).toBeHidden();
  for (const design of ["A", "B", "C"]) {
    await expect(page.locator(`#r7-guide-${design} .static-step`)).toHaveCount(12);
    await expect(page.locator(`#r7-guide-${design} h3`)).toContainText(`${guides[design].model.instanceCount}点`);
  }
  await expect(page.locator("#r7-guide-B-07_lower_rotor")).toContainText("固定276点");
  await context.close();
});

test("r7 touch rotates, zooms and pans while keeping schema2 inventory unchanged", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Touch is verified only in the 375px touch project.");
  await ready(page, "C");
  const canvas = page.locator("#canvas-host canvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  const diagnostic = (key) => page.locator("#camera-stats").getAttribute(`data-${key}`);
  const before = await frameState(page);
  const session = await page.context().newCDPSession(page);
  const touch = (type, points) => session.send("Input.dispatchTouchEvent", { type, touchPoints: points });
  const angle = await diagnostic("angle");
  await touch("touchStart", [{ x: x-45, y, id: 1 }]);
  await touch("touchMove", [{ x, y: y+10, id: 1 }]);
  await touch("touchMove", [{ x: x+45, y: y+20, id: 1 }]);
  await touch("touchEnd", []);
  await expect.poll(() => diagnostic("angle")).not.toBe(angle);
  const distance = Number(await diagnostic("distance"));
  await touch("touchStart", [{ x: x-25, y, id: 1 }, { x: x+25, y, id: 2 }]);
  await touch("touchMove", [{ x: x-55, y, id: 1 }, { x: x+55, y, id: 2 }]);
  await touch("touchEnd", []);
  await expect.poll(async () => Number(await diagnostic("distance"))).toBeLessThan(distance);
  const target = await diagnostic("target");
  await touch("touchStart", [{ x: x-25, y, id: 1 }, { x: x+25, y, id: 2 }]);
  await touch("touchMove", [{ x: x-10, y: y+20, id: 1 }, { x: x+40, y: y+20, id: 2 }]);
  await touch("touchEnd", []);
  await expect.poll(() => diagnostic("target")).not.toBe(target);
  expect(await frameState(page)).toEqual(before);
  await session.detach();
});
