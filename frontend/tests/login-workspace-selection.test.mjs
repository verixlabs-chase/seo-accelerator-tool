import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const loginSource = readFileSync(new URL("../app/login/page.jsx", import.meta.url), "utf8");

test("multi-workspace sign-in requires a business choice before opening the dashboard", () => {
  assert.match(loginSource, /requires_org_selection/);
  assert.match(loginSource, /Choose the business you want to open/);
  assert.match(loginSource, /auth\/select-org/);
  assert.match(loginSource, /router\.replace\("\/dashboard"\)/);
});
