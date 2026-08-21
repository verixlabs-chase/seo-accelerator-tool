import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


const packageJson = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
);
const loginSource = readFileSync(
  new URL("../app/login/page.jsx", import.meta.url),
  "utf8",
);
const smokeSource = readFileSync(
  new URL("../e2e/production-smoke.spec.ts", import.meta.url),
  "utf8",
);
const playwrightConfigSource = readFileSync(
  new URL("../playwright.config.ts", import.meta.url),
  "utf8",
);
const workflowSource = readFileSync(
  new URL("../../.github/workflows/production-smoke.yml", import.meta.url),
  "utf8",
);


test("production browser smoke is an explicit Playwright contract", () => {
  assert.equal(packageJson.scripts["test:e2e"], "playwright test");
  assert.match(smokeSource, /public sign-in remains understandable and accessible/);
  assert.match(smokeSource, /without changing data/);
  assert.match(smokeSource, /Choose the location shown across the workspace/);
  assert.match(smokeSource, /width: 390, height: 844/);
  assert.match(smokeSource, /Available reports/);
  assert.match(smokeSource, /locations ready to compare/);
  assert.match(smokeSource, /auth\/logout/);
  assert.match(smokeSource, /browserProblemTypes/);
  assert.match(smokeSource, /session_revoked/);
  assert.match(smokeSource, /did not provide a revocable session endpoint/);
  assert.doesNotMatch(smokeSource, /message\.text\(\)|error\.message/);
});


test("production credentials cannot be redirected by a workflow input", () => {
  assert.match(
    workflowSource,
    /E2E_BASE_URL: https:\/\/insightos\.verixlabs\.com/,
  );
  assert.doesNotMatch(workflowSource, /inputs\.base_url/);
  assert.match(workflowSource, /secrets\.E2E_SMOKE_EMAIL/);
  assert.match(workflowSource, /secrets\.E2E_SMOKE_PASSWORD/);
  assert.match(workflowSource, /github\.ref == 'refs\/heads\/main'/);
  assert.doesNotMatch(workflowSource, /uses:\s+actions\/[^@\s]+@v\d/);
  assert.doesNotMatch(workflowSource, /upload-artifact/);
  assert.match(playwrightConfigSource, /isProductionRun \? "off"/);
  const jobEnvironment = workflowSource.match(
    /    env:\n(?<value>(?:      .+\n)+)    steps:/,
  )?.groups?.value || "";
  assert.doesNotMatch(jobEnvironment, /E2E_EMAIL|E2E_PASSWORD/);
});


test("the sign-in fields expose stable accessible names", () => {
  assert.match(loginSource, /htmlFor="email"/);
  assert.match(loginSource, /id="email"/);
  assert.match(loginSource, /htmlFor="password"/);
  assert.match(loginSource, /id="password"/);
});
