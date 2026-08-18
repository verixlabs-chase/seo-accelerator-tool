import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);

const sectionStart = settings.indexOf('id="private-ai-provider"');
const sectionEnd = settings.indexOf('id="google-search-console-connection"', sectionStart);
const section = settings.slice(sectionStart, sectionEnd);

test("private AI setup is Enterprise-owner scoped and loads without blocking Settings", () => {
  assert.match(settings, /me\?\.org_role === "org_owner"/);
  assert.match(settings, /item\.code === "private_ai_provider"/);
  assert.match(settings, /loadPrivateAIProviders\(\)\.catch\(\(\) => \{/);
  assert.match(settings, /setPrivateAIProviderLoadState\("unavailable"\)/);
  assert.match(settings, /platformApi\("\/ai\/providers"/);
  assert.match(settings, /endpoint_url: privateAIEndpoint/);
  assert.match(settings, /api_key: privateAIApiKey \|\| null/);
  assert.match(section, /type="password"/);
  assert.match(section, /Stored encrypted and never shown again/);
  assert.match(section, /Private AI candidate status is unavailable/);
  assert.match(section, /will not assume there are no saved candidates/);
  assert.match(section, /privateAIProviderLoadState === "ready"/);
});

test("the owner workflow exposes every evidence gate and only zero-traffic standby", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/preflight`/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/validate`/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/benchmarks`/);
  assert.match(settings, /benchmarks\/\$\{benchmarkId\}\/review/);
  assert.match(settings, /Uses only the evidence provided/);
  assert.match(settings, /Keeps owner approval controls/);
  assert.match(settings, /Does not invent missing measurements/);
  assert.match(section, /Approve for a later standby step/);
  assert.match(section, /Routing inactive/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/standby`/);
  assert.match(section, /Register zero-traffic standby/);
  assert.match(section, /managed AI remains the only live route/);
  assert.match(section, /0% traffic and no customer prompts/);
  assert.doesNotMatch(settings, /ai\/providers[^"'`\n]*\/(?:activate|route|promote)/i);
  assert.doesNotMatch(section, />\s*(?:Activate|Launch|Promote)\s*</i);
});

test("approval requires all four explicit safety acknowledgements", () => {
  assert.match(settings, /reviewed_synthetic_results/);
  assert.match(settings, /understands_not_active/);
  assert.match(settings, /understands_managed_fallback_required/);
  assert.match(settings, /understands_no_automatic_changes/);
  assert.match(settings, /Object\.values\(acknowledgements\)\.every\(Boolean\)/);
  assert.match(section, /managed provider must remain available as fallback/);
  assert.match(section, /does not authorize automatic website or business-profile changes/);
  assert.match(section, /disabled=\{!allAcknowledged/);
  assert.match(settings, /reviewed_standby_boundary/);
  assert.match(settings, /understands_zero_customer_prompts/);
  assert.match(settings, /understands_managed_route_unchanged/);
  assert.match(settings, /understands_manual_disable_available/);
  assert.match(section, /disabled=\{!allStandbyAcknowledged/);
});

test("customer-visible provider truth stays redacted and explicitly inactive", () => {
  assert.match(section, /Inactive candidate/);
  assert.match(section, /still inactive/);
  assert.match(section, /Standby status is unavailable/);
  assert.match(section, /will not assume this provider is inactive/);
  assert.match(section, /Synthetic checks are limited examples/);
  assert.match(section, /never shown again/);
  assert.doesNotMatch(section, /validation_evidence_hash|benchmark_artifact_hash|resolved_address_hash/i);
  assert.doesNotMatch(section, /automatic_activation_allowed:\s*true|routing_enabled:\s*true/i);
});

test("fallback readiness stays evidence-only and cannot enable private routing", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/routing-readiness`/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/routing-readiness`/);
  assert.match(section, /Live-routing safety check/);
  assert.match(section, /This check does not turn on private-model traffic/);
  assert.match(section, /Check fallback readiness/);
  assert.match(section, /Prerequisites passed/);
  assert.match(section, /private-provider runs/);
  assert.match(section, /receives 0% traffic and no customer prompts/);
  assert.doesNotMatch(section, />\s*(?:Enable routing|Send traffic|Go live)\s*</i);
});

test("the first live canary is fixed, owner-confirmed, and automatically reversible", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/routing-canary`/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/routing-canary`/);
  assert.match(section, /Start fixed 5% private-AI check/);
  assert.match(section, /5% maximum · 1 per day/);
  assert.match(section, /hard limit of one private prompt per day/);
  assert.match(section, /managed fallback reserved first/);
  assert.match(section, /automatically stops this check/);
  assert.match(section, /cannot change a website, listing, or business profile/);
  assert.match(section, /Stop limited private-AI check/);
  assert.match(settings, /reviewed_five_percent_limit/);
  assert.match(settings, /understands_real_customer_prompt/);
  assert.match(settings, /understands_automatic_rollback/);
  assert.match(section, /disabled=\{!allCanaryAcknowledged/);
  assert.doesNotMatch(section, /type="range"|traffic_percentage:\s*(?:10|25|50|100)/);
  assert.doesNotMatch(section, />\s*(?:Route all traffic|Make primary|Disable fallback)\s*</i);
});

test("multi-run canary monitoring is evidence-only and cannot expand routing", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/routing-canary-monitoring`/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/routing-canary-monitoring`/);
  assert.match(section, /Successful days:/);
  assert.match(section, /Minimum health evidence collected/);
  assert.match(section, /Collecting health evidence/);
  assert.match(section, /Health review has a blocker/);
  assert.match(section, /Save health review/);
  assert.match(section, /cannot increase traffic, add prompt types, or authorize automatic changes/);
  assert.match(settings, /required_success_days: 3/);
  assert.match(settings, /max_latency_threshold_ms: 8000/);
  assert.match(settings, /traffic_change_allowed: false/);
  assert.match(settings, /capability_change_allowed: false/);
  assert.doesNotMatch(section, />\s*(?:Expand routing|Add capability|Raise traffic)\s*</i);
});

test("saved-evidence questions require their own synthetic check and fixed owner approval", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/question-capability`/);
  assert.match(settings, /question-capability\/benchmark/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/question-capability`/);
  assert.match(section, /Saved-evidence questions/);
  assert.match(section, /uses synthetic data and sends no customer prompt/);
  assert.match(section, /Start fixed 5% saved-question check/);
  assert.match(section, /share one total private prompt per day/);
  assert.match(section, /Any failure stops this capability and uses managed AI/);
  assert.match(section, /cannot create, approve, publish, or execute work/);
  assert.match(settings, /reviewed_question_capability_check/);
  assert.match(settings, /understands_real_customer_questions/);
  assert.match(settings, /understands_shared_daily_limit/);
  assert.match(settings, /understands_managed_fallback_and_rollback/);
  assert.match(section, /disabled=\{!allQuestionAcknowledged/);
  assert.doesNotMatch(section, />\s*(?:Make primary|Route all questions|Automate fixes)\s*</i);
});
