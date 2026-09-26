import { defineConfig, devices } from "@playwright/test";

const remoteURL = process.env.SITE_URL;
const baseURL = remoteURL || "http://127.0.0.1:4173/TeoJansen_Rhinoceros/";

export default defineConfig({
  testDir: "./tests",
  testMatch: "*.spec.mjs",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  timeout: 45_000,
  expect: { timeout: 12_000 },
  use: {
    baseURL,
    browserName: "chromium",
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
      ...(process.env.PLAYWRIGHT_SOFTWARE_GPU === "1"
        ? { args: ["--use-angle=swiftshader", "--disable-gpu"] } : {}),
    },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: "mobile",
      use: {
        ...devices["iPhone SE"],
        defaultBrowserType: "chromium",
        viewport: { width: 375, height: 812 },
      },
    },
  ],
  webServer: remoteURL ? undefined : {
    command: "python3 serve.py --port 4173",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 20_000,
  },
});
