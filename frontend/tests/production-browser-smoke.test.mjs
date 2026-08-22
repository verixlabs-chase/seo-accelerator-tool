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
const deploymentRunbookSource = readFileSync(
  new URL("../../docs/platform/runbooks/deployment_runbook.md", import.meta.url),
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


test("production smoke proves the same-origin limiter without flooding production", () => {
  assert.match(
    smokeSource,
    /same-origin health proves PostgreSQL request protection without changing customer data/,
  );
  assert.match(smokeSource, /request\.get\("\/api\/v1\/health"/);
  assert.match(smokeSource, /request\.get\("\/api\/v1\/health\/readiness"/);
  assert.match(smokeSource, /enabled: true/);
  assert.match(smokeSource, /backend: "postgres"/);
  assert.match(smokeSource, /rate_limit_store: true/);
  assert.match(smokeSource, /"X-RateLimit-Limit"/);
  assert.match(smokeSource, /"X-RateLimit-Remaining"/);
  assert.match(smokeSource, /"X-RateLimit-Reset"/);
  assert.match(smokeSource, /readinessHeaders\["cache-control"\]/);
  assert.match(smokeSource, /toContain\("no-store"\)/);
  assert.match(
    smokeSource,
    /livenessHeaders\["x-ratelimit-limit"\]\)\.toBeUndefined\(\)/,
  );
  assert.equal(
    smokeSource.match(/await request\.get\(/g)?.length,
    2,
    "the production proof must make exactly one liveness and one readiness request",
  );
  assert.doesNotMatch(
    smokeSource,
    /RATE_LIMIT_REQUESTS_PER_MINUTE|internal\/jobs\/drain|rate_limit_exceeded/,
  );
});


test("limiter promotion proof remains isolated, bounded, and reversible", () => {
  assert.match(deploymentRunbookSource, /Direct-versus-proxy identity proof/);
  assert.match(deploymentRunbookSource, /Controlled 429 proof/);
  assert.match(deploymentRunbookSource, /Fail-closed 503 proof/);
  assert.match(deploymentRunbookSource, /Cron cleanup proof/);
  assert.match(deploymentRunbookSource, /Never perform these checks against production/);
  assert.match(deploymentRunbookSource, /exactly three sequential/);
  assert.match(deploymentRunbookSource, /rate_limit_cleanup\.attempted=true/);
  assert.match(deploymentRunbookSource, /RATE_LIMIT_ENABLED=false/);
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
