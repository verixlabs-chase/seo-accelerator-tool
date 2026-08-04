import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8");

test("settings presents Insight Credits without exposing the internal dollar budget", () => {
  const settings = source("../app/(product)/settings/page.tsx");

  assert.match(settings, /Insight Credits available this month/);
  assert.match(settings, /credits left this month/);
  assert.match(settings, /Failed work returns unused credits automatically/);
  assert.doesNotMatch(settings, /Monthly data budget/);
  assert.doesNotMatch(settings, /usageAllowance\.allowance/);
  assert.doesNotMatch(
    settings,
    /\$\{usageAllowance\.credits\.(?:monthly|used|reserved|remaining)\.toFixed/,
  );
});

test("keyword research shows the paid refresh price before it runs", () => {
  const research = source("../app/(product)/keyword-research/page.tsx");

  assert.match(research, /Refreshing this location uses up to/);
  assert.match(research, /Unused credits are returned automatically/);
  assert.match(research, /item\.code === "keyword_relevance_review"/);
  assert.match(research, /Uses \{reviewCreditPrice\.credits\} Insight/);
});
