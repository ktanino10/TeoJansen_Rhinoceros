import { defineConfig, devices } from "@playwright/test";

const externalPreview = process.env.R7_SITE_URL;
const baseURL = externalPreview || "http://127.0.0.1:4177/r7-preview/TeoJansen_Rhinoceros/";
const url = new URL(baseURL);
if (!["127.0.0.1", "localhost"].includes(url.hostname) || process.env.CI) {
  throw new Error("Unpublished r7 tests must target a loopback-only local preview.");
}

export default defineConfig({
  testDir: "./r7_tests",
  testMatch: "*.spec.mjs",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  outputDir: "./test-results-r7",
  use: {
    baseURL,
    browserName: "chromium",
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
      ...(process.env.PLAYWRIGHT_SOFTWARE_GPU === "1" ? { args: ["--use-angle=swiftshader", "--disable-gpu"] } : {}),
    },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { ...devices["iPhone SE"], defaultBrowserType: "chromium", viewport: { width: 375, height: 812 } } },
  ],
  webServer: externalPreview ? undefined : {
    command: "python3 serve.py --port 4177",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 20_000,
  },
});
