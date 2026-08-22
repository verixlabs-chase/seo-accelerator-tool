import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:3000";
const isProductionRun = new URL(baseURL).hostname === "insightos.verixlabs.com";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["line"]] : "list",
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    ...devices["Desktop Chrome"],
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    // Production pages contain real tenant metrics. Never persist screenshots,
    // traces, or video from the protected smoke run.
    screenshot: isProductionRun ? "off" : "only-on-failure",
    trace: isProductionRun ? "off" : "retain-on-failure",
    video: isProductionRun ? "off" : "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  outputDir: "test-results/playwright",
});
