import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const pages = ["index.html", "production.html", "comparison.html", "viewer.html", "calculations.html", "r7.html", "walking.html"];
const japanese = /[ぁ-ゖァ-ヺ一-龯]/;

async function englishSurface(page, selector = "body") {
  const text = (await page.locator(selector).innerText()).replaceAll("日本語", "");
  expect(text).not.toMatch(japanese);
}

for (const locale of ["ja", "en"]) {
  test(`localization ${locale} current version journey: home, exact CAD, assembly, walking and downloads`, async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    const prefix = locale === "en" ? "en/" : "";
    const manifest = await (await page.request.get("build-manifest.json")).json();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${prefix}index.html#ver3`);
    await expect(page.locator("#ver3")).toHaveAttribute("data-engineering-revision", manifest.r7_source.revisionId);
    for (const design of ["A", "B", "C"]) {
      await page.locator(`#current-${design} a[href^="r7.html?"]`).click();
      await expect(page).toHaveURL(new RegExp(`/${prefix}r7\\.html\\?design=${design}#viewer$`));
      await expect(page.locator("h1")).toContainText("Ver.3.1");
      await page.locator("#load-viewer").click();
      await expect(page.locator("#viewer-workspace")).toHaveAttribute("aria-busy", "false", { timeout: 80_000 });
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", design === "B" ? "785" : "750");
      await expect(page.locator("#step-select option")).toHaveCount(13);
      await page.locator("#step-first").click();
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", "0");
      await page.locator("#step-next").click();
      await expect(page.locator("#stage-title")).not.toBeEmpty();
      await page.locator("#step-complete").click();
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", design === "B" ? "785" : "750");
      await page.locator("[data-language-link]").click();
      await expect(page.locator("html")).toHaveAttribute("lang", locale === "en" ? "ja" : "en");
      await expect(page).toHaveURL(new RegExp(`r7\\.html\\?design=${design}#viewer$`));
      await page.goto(`${prefix}index.html#ver3`);
    }
    await page.locator('#current-C a[href^="walking.html?"]').click();
    await expect(page).toHaveURL(new RegExp(`/${prefix}walking\\.html\\?design=C#walking$`));
    await expect(page.locator("h1")).toContainText("Ver.3.1");
    await expect(page.locator("#walking-version-note")).toContainText("r7-floor2-walking-kinematic-v1");
    await page.locator("#walk-load").click();
    await expect(page.locator("#walk-workspace")).toHaveAttribute("aria-busy", "false", { timeout: 90_000 });
    await expect(page.locator("#walk-stats")).toHaveAttribute("data-drawn", "750");
    await page.locator("#walk-cycle").click();
    await expect.poll(async () => Number(await page.locator("#walk-stats").getAttribute("data-forward"))).toBeGreaterThan(92);
    await page.goto(`${prefix}index.html#downloads`);
    for (const design of ["A", "B", "C"]) {
      const guide = await (await page.request.get(`assets/r7-assembly-${design}.json`)).json();
      for (const key of ["native", "cad", "stl", "bom"]) {
        await expect(page.locator(`#current-downloads a[href="${guide.links[key]}"]`)).toHaveCount(1);
      }
    }
    await page.locator('.version-nav a[href="comparison.html"]').click();
    await expect(page).toHaveURL(new RegExp(`/${prefix}comparison\\.html$`));
    await expect(page.locator("h1")).toContainText("Ver.3.0");
    await page.screenshot({ path: testInfo.outputPath(`${locale}-version-archive-navigation.png`) });
    await page.locator(".archive-notice a").click();
    await expect(page).toHaveURL(new RegExp(`/${prefix}r7\\.html#r7-change-matrix$`));
    await expect(page.locator("h1")).toContainText("Ver.3.1");
  });

  for (const filename of pages) {
    test(`localization ${locale} ${filename}: equivalent route, metadata and accessible layout`, async ({ page }, testInfo) => {
      const errors = [];
      const requested = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("request", request => requested.push(request.url()));
      const prefix = locale === "en" ? "en/" : "";
      await page.goto(`${prefix}${filename}?design=C&focus=legs#top`);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", new RegExp(`/${prefix}${filename}$`));
      await expect(page.locator('link[hreflang="ja"]')).toHaveAttribute("href", new RegExp(`Rhinoceros/${filename}$`));
      await expect(page.locator('link[hreflang="en"]')).toHaveAttribute("href", new RegExp(`/en/${filename}$`));
      const switcher = page.locator("[data-language-link]");
      await expect(switcher).toHaveAttribute("href", new RegExp(`${filename}\\?design=C&focus=legs#top$`));
      expect(requested.filter(url => /\.(mp4|gif|glb|gz)(?:$|\?)/.test(url) || /(?:viewer|walking)-engine\.js/.test(url))).toEqual([]);
      if (locale === "en") {
        await englishSurface(page);
        for (const alt of await page.locator("img").evaluateAll(images => images.map(image => image.alt))) {
          expect(alt).not.toMatch(japanese);
        }
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`${locale}-${filename}.png`), fullPage: false });
      await switcher.click();
      await expect(page.locator("html")).toHaveAttribute("lang", locale === "en" ? "ja" : "en");
      await expect(page).toHaveURL(new RegExp(`${filename}\\?design=C&focus=legs#top$`));
      expect(errors).toEqual([]);
    });
  }
}

for (const filename of ["viewer.html", "r7.html"]) {
  for (const design of ["A", "B", "C"]) {
    test(`localization English ${filename} ${design}: actual CAD and assembly controls`, async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(`en/${filename}?design=${design}#viewer`);
      await page.locator("#load-viewer").click();
      await expect(page.locator("#viewer-workspace")).toBeVisible();
      await expect(page.locator("#viewer-workspace")).toHaveAttribute("aria-busy", "false", { timeout: 80_000 });
      await expect(page.locator("#viewer-error")).toBeHidden();
      const counts = filename === "r7.html" ? { A: 750, B: 785, C: 750 } : { A: 791, B: 796, C: 755 };
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", String(counts[design]));
      await page.locator("#step-first").click();
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", "0");
      await page.locator("#step-next").click();
      await englishSurface(page, "#viewer-workspace");
      for (const label of await page.locator("#step-select option, #part-select option").allTextContents()) {
        expect(label).not.toMatch(japanese);
      }
      await page.locator("#step-complete").click();
      await expect(page.locator("#instance-count")).toHaveAttribute("data-visible", String(counts[design]));
      await page.locator("#canvas-host").screenshot({ path: testInfo.outputPath(`en-${filename}-${design}-cad.png`) });
      const part = await page.locator("#part-select option").evaluateAll(options => options.find(o => o.value && !o.disabled).value);
      await page.locator("#part-select").selectOption(part);
      await englishSurface(page, "#part-description");
      await page.locator('[data-view="front"]').click();
      await page.locator("#fit-selection").click();
      const nextDesign = design === "A" ? "B" : "A";
      await page.locator("#design-select").selectOption(nextDesign);
      await expect(page.locator("[data-language-link]")).toHaveAttribute("href", new RegExp(`design=${nextDesign}#viewer$`));
      expect(errors).toEqual([]);
    });
  }
}

for (const design of ["A", "B", "C"]) {
  test(`localization English walking ${design}: play, pause, phase and language state`, async ({ page }, testInfo) => {
    test.setTimeout(150_000);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`en/walking.html?design=${design}#walking`);
    await page.locator("#walk-load").click();
    await expect(page.locator("#walk-workspace")).toHaveAttribute("aria-busy", "false", { timeout: 90_000 });
    await expect(page.locator("#walk-error")).toBeHidden();
    await expect(page.locator("#walk-workspace")).toBeVisible();
    await expect(page.locator("#walk-play")).toHaveText("Play walking");
    await page.locator("#walk-play").click();
    await expect(page.locator("#walk-play")).toHaveText("Pause walking");
    await expect.poll(() => page.locator("#walk-stats").getAttribute("data-seconds"), { timeout: 30_000 }).not.toBe("0");
    await page.locator("#walk-play").click();
    await expect(page.locator("#walk-play")).toHaveText("Play walking");
    await page.locator("#walk-cycle").click();
    await expect(page.locator("#walk-crank")).toContainText("cycles");
    await page.locator("#walk-workspace").screenshot({ path: testInfo.outputPath(`en-walking-${design}.png`) });
    await englishSurface(page, "#walk-workspace");
    expect(errors).toEqual([]);
  });
}

test("localization English loading failures and JavaScript-free fallback stay English", async ({ page, browser }) => {
  await page.route("**/assets/r7-walking-index.json", route => route.abort());
  await page.goto("en/walking.html");
  await page.locator("#walk-load").click();
  await expect(page.locator("#walk-error")).toBeVisible();
  await expect(page.locator("#walk-error")).toContainText("Walking 3D could not load");
  await englishSurface(page);
  const context = await browser.newContext({ javaScriptEnabled: false });
  const noScript = await context.newPage();
  await noScript.goto(new URL("en/r7.html", test.info().project.use.baseURL).href);
  await expect(noScript.locator("#r7-guide-A")).toBeVisible();
  await englishSurface(noScript);
  await context.close();
});

for (const locale of ["ja", "en"]) {
  test(`localization ${locale} walking videos: matching media, optional CC and unchanged timing`, async ({ page, request }, testInfo) => {
    const requests = [];
    const errors = [];
    page.on("request", request => requests.push(request.url()));
    page.on("pageerror", error => errors.push(error.message));
    const media = await (await request.get("assets/r7-walking-locales-manifest.json")).json();
    await page.goto(`${locale === "en" ? "en/" : ""}walking.html#walking-films`);
    expect(requests.filter(url => url.endsWith(".mp4"))).toEqual([]);
    for (const design of ["C", "A", "B"]) {
      const expected = media.designs[design];
      const variant = expected.locales[locale];
      const video = page.locator(`#r7-walking-${design}`);
      const track = video.locator("track");
      await expect(video).toHaveAttribute("aria-label", `Ver.3.1 · ${variant.title}`);
      await expect(video).toHaveAttribute("title", variant.description);
      await expect(track).toHaveAttribute("srclang", locale);
      await expect(track).toHaveAttribute("label", variant.captions.label);
      expect(await track.getAttribute("default")).toBeNull();
      const suffix = locale === "en" ? "-en" : "";
      await expect(video.locator("source")).toHaveAttribute("src", new RegExp(`r7-walking-${design}${suffix}\\.mp4$`));
      expect(await video.evaluate(v => v.textTracks[0].mode)).toBe("disabled");
      const play = locale === "en" ? `Play ${variant.title}` : `${variant.title}を再生`;
      const pause = locale === "en" ? `Pause ${variant.title}` : `${variant.title}を一時停止`;
      await page.getByRole("button", { name: play, exact: true }).click();
      await expect.poll(() => video.evaluate(v => !v.paused && v.currentTime > .05)).toBe(true);
      expect(await video.evaluate(v => [v.videoWidth, v.videoHeight])).toEqual([960, 720]);
      const box = await video.boundingBox();
      expect(box.width / box.height).toBeCloseTo(4 / 3, 2);
      expect(await video.evaluate(v => v.duration)).toBeCloseTo(expected.durationSeconds, 3);
      await page.getByRole("button", { name: pause, exact: true }).click();
      await page.locator(`#walking-film-${design}`).screenshot({
        path: testInfo.outputPath(`${locale}-walking-${design}-single-overlay.png`),
        style: ".site-header,.skip-link{visibility:hidden}",
      });
      await video.evaluate(v => { v.textTracks[0].mode = "showing"; });
      await expect.poll(() => video.evaluate(v => v.textTracks[0].cues?.length || 0)).toBe(4);
      const cues = await video.evaluate(v => [...v.textTracks[0].cues].map(cue => cue.text).join("\n"));
      expect(cues).toContain("120 rpm");
      if (locale === "en") expect(cues).not.toMatch(japanese);
      else expect(cues).toContain("実機");
      await page.getByRole("button", { name: play, exact: true }).click();
      await page.getByRole("button", { name: pause, exact: true }).click();
      expect(await video.evaluate(v => v.textTracks[0].mode)).toBe("showing");
    }
    expect(errors).toEqual([]);
  });
}
