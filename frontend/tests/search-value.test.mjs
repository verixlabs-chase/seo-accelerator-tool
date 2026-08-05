import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const page = fs.readFileSync(
  path.resolve(here, "../app/(product)/organic-value/page.tsx"),
  "utf8",
);

test("Search Value uses the research-backed contract and removes subjective investment inputs", () => {
  assert.match(page, /\/search-value/);
  assert.match(page, /What similar visibility could cost in paid search/);
  assert.match(page, /Measured clicks vs\. modeled gaps/);
  assert.match(page, /Every dollar can be traced to a customer search/);
  assert.match(page, /formula_version/);
  assert.match(page, /input_hash/);
  assert.doesNotMatch(page, /Monthly SEO investment/);
  assert.doesNotMatch(page, /monthly_seo_investment/);
});

test("Search Value keeps supplier and outcome claims out of the customer page", () => {
  assert.doesNotMatch(page, /DataForSEO/i);
  assert.match(page, /not business revenue/i);
  assert.match(page, /does not\s+estimate sales, profit, leads, or guaranteed results/i);
});
