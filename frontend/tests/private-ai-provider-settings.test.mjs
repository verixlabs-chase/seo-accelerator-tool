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
  assert.match(section, /Private endpoints and models running on your own computer are Enterprise-only/);
  assert.match(section, /Growth \(\$699\/month\).*does not include private-model deployment or support/);
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
  assert.match(section, /Managed AI stays primary/);
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

test("the connection shows one plain-language catalog for every separately governed use", () => {
  assert.match(settings, /supported_capabilities/);
  assert.match(section, /What this connection can be checked for/);
  assert.match(section, /Each item requires its own compatibility result and owner approval/);
  assert.match(section, /Listing it here does not turn it on/);
  assert.match(section, /Every approved check remains fixed at 5%/);
  assert.match(section, /shares one private prompt per day/);
  assert.match(section, /keeps managed AI as fallback/);
  assert.match(section, /cannot publish or make changes/);
  assert.doesNotMatch(section, />\s*(?:Enable all|Approve all|Turn on all)\s*</i);
});

test("customer-owned private endpoint charges cannot be mistaken for InsightOS billing", () => {
  assert.match(settings, /billing_boundary/);
  assert.match(section, /Provider charges stay with your provider account/);
  assert.match(section, /InsightOS does not add private-model usage fees/);
  assert.doesNotMatch(section, /price_card|provider_reported_cost|platform_provider_cost/i);
});

test("the local-model relay is outbound connection-only and immediately revocable", () => {
  assert.match(settings, /platformApi\("\/ai\/relay-enrollments"/);
  assert.match(settings, /`\/ai\/relay-enrollments\/\$\{enrollmentId\}`/);
  assert.match(section, /Connect a model running on your own computer/);
  assert.match(section, /makes an outbound connection to InsightOS/);
  assert.match(section, /cannot receive customer prompts or run model work yet/);
  assert.match(section, /Create one-time connection key/);
  assert.match(section, /InsightOS stores only a secure fingerprint/);
  assert.match(section, /Revoke connection/);
  assert.match(section, /Local model connection paused/);
  assert.match(section, /Growth \(\$699\/month\) cannot run relay checks or local-model qualification/);
  assert.match(section, /privateAIProviderPlanEligible &&/);
  assert.match(section, /heartbeat is empty unless the owner prepares one short-lived synthetic receipt check/);
  assert.match(settings, /understands_no_customer_prompts/);
  assert.match(settings, /understands_no_database_or_execution_access/);
  assert.doesNotMatch(section, />\s*(?:Send prompt|Run model|Enable work packets|Allow database access)\s*</i);
});

test("the relay packet check is signed, synthetic, short-lived, and non-executing", () => {
  assert.match(settings, /`\/ai\/relay-enrollments\/\$\{enrollmentId\}\/diagnostic-packets`/);
  assert.match(section, /Prepare signed connection check/);
  assert.match(section, /Signed receipt check verified/);
  assert.match(section, /Signed receipt check expired/);
  assert.match(section, /random synthetic challenge only/);
  assert.match(section, /includes no customer data and cannot call a model or run work/);
  assert.match(section, /no customer prompt, model call, database, website, business-profile, publishing, or execution access/);
  assert.match(settings, /customer_data_included: false/);
  assert.match(settings, /model_execution_requested: false/);
  assert.match(settings, /business_execution_requested: false/);
  assert.match(settings, /publishing_requested: false/);
  assert.doesNotMatch(section, />\s*(?:Run local model|Send customer prompt|Enable relay work)\s*</i);
});

test("the customer relay helper is a plain download with simple secret-safe setup", () => {
  assert.match(settings, /platformApiFile\("\/ai\/relay-enrollments\/agent\/download"/);
  assert.match(section, /Download relay helper/);
  assert.match(section, /python insightos-local-relay\.py/);
  assert.match(section, /Paste this one-time key when the helper asks for it/);
  assert.match(section, /InsightOS cannot recover the old key/);
  assert.doesNotMatch(section, /INSIGHTOS_RELAY_TOKEN=/);
  assert.doesNotMatch(section, /pip install|OpenAI API key|port forwarding|public IP/i);
});

test("local runtime discovery reports only software kind and count without calling a model", () => {
  assert.match(settings, /runtime_discovery/);
  assert.match(section, /Ollama and LM Studio found/);
  assert.match(section, /No supported local model software found yet/);
  assert.match(section, /Model names stayed on this computer/);
  assert.match(section, /Discovery only — no customer data was sent and no model was called/);
  assert.match(section, /checks loopback only/);
  assert.doesNotMatch(section, />\s*(?:Run local model|Select local model|Send prompt)\s*</i);
});

test("local model qualification is explicit, synthetic, minimized, and non-activating", () => {
  assert.match(settings, /model_qualification/);
  assert.match(section, /python insightos-local-relay\.py --once --check-model/);
  assert.match(section, /Made-up local model check passed/);
  assert.match(section, /Made-up local model check needs attention/);
  assert.match(section, /model name and any response stayed on this computer/);
  assert.match(section, /does not enable customer prompts, routing, publishing, website changes, or business-profile work/);
  assert.match(settings, /synthetic_input_only: true/);
  assert.match(settings, /model_call_attempted: true/);
  assert.match(settings, /model_response_received: boolean/);
  assert.match(settings, /raw_model_identifier_sent: false/);
  assert.match(settings, /model_output_sent: false/);
  assert.match(settings, /customer_work_allowed: false/);
  assert.doesNotMatch(section, />\s*(?:Enable local model|Start routing|Use for customer work|Publish result)\s*</i);
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

test("saved-action draft wording is separately checked and can never publish", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/draft-capability`/);
  assert.match(settings, /draft-capability\/benchmark/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/draft-capability`/);
  assert.match(section, /Saved-action draft wording/);
  assert.match(section, /uses synthetic information and sends no customer data/);
  assert.match(section, /Start fixed 5% draft-wording check/);
  assert.match(section, /share one total private prompt per day/);
  assert.match(section, /Every draft still requires review/);
  assert.match(section, /cannot approve, publish, send, or execute work/);
  assert.match(settings, /reviewed_draft_capability_check/);
  assert.match(settings, /understands_real_saved_action_context/);
  assert.match(settings, /understands_draft_only_no_publish/);
  assert.match(settings, /publishing_allowed: false/);
  assert.match(section, /disabled=\{!allDraftAcknowledged/);
  assert.doesNotMatch(section, />\s*(?:Publish draft|Send draft|Apply wording|Auto-publish)\s*</i);
});

test("unclear-search review requires its own check and bounded owner approval", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/keyword-review-capability`/);
  assert.match(settings, /keyword-review-capability\/benchmark/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/keyword-review-capability`/);
  assert.match(section, /Unclear search review/);
  assert.match(section, /made-up unclear search against a made-up service and work area/);
  assert.match(section, /No customer searches, website information, or account data are sent/);
  assert.match(section, /Start fixed 5% unclear-search check/);
  assert.match(section, /share one total private prompt per day/);
  assert.match(section, /Any failure stops this capability and uses managed AI/);
  assert.match(section, /sort or hide only the unclear saved searches/);
  assert.match(section, /cannot add or track searches, create work/);
  assert.match(settings, /reviewed_keyword_review_check/);
  assert.match(settings, /understands_real_saved_search_context/);
  assert.match(settings, /understands_saved_search_classification_only/);
  assert.match(section, /disabled={!allKeywordReviewAcknowledged/);
  assert.match(settings, /saved_searches_changed: false/);
  assert.match(settings, /may_add_or_track_searches: false/);
  assert.match(settings, /publishing_allowed: false/);
  assert.doesNotMatch(section, />\s*(?:Route all searches|Apply all classifications|Publish searches)\s*</i);
});

test("website draft wording requires its own check and fixed owner approval", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/content-draft-capability`/);
  assert.match(settings, /content-draft-capability\/benchmark/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/content-draft-capability`/);
  assert.match(section, /Optional website draft wording/);
  assert.match(section, /made-up website draft/);
  assert.match(section, /No customer website, draft, search, or account data is sent/);
  assert.match(section, /Check website-draft compatibility/);
  assert.match(section, /Synthetic website-draft check passed/);
  assert.match(section, /Start fixed 5% website-draft check/);
  assert.match(section, /share one total private prompt per day/);
  assert.match(section, /Any failure stops this capability and uses managed AI/);
  assert.match(section, /separate review-only suggestion for the exact saved draft/);
  assert.match(section, /cannot edit the owner draft, approve wording, publish a page/);
  assert.match(settings, /reviewed_content_draft_check/);
  assert.match(settings, /understands_real_saved_website_draft_context/);
  assert.match(settings, /understands_shared_daily_limit/);
  assert.match(settings, /understands_managed_fallback_and_rollback/);
  assert.match(settings, /understands_suggestion_only_no_edit_or_publish/);
  assert.match(section, /disabled={!allContentDraftAcknowledged/);
  assert.match(settings, /owner_drafts_changed: false/);
  assert.match(settings, /suggestion_only: true/);
  assert.match(settings, /may_edit_or_publish: false/);
  assert.match(settings, /publishing_allowed: false/);
  assert.doesNotMatch(section, />\s*(?:Publish page|Apply website wording|Edit owner draft)\s*</i);
});

test("onboarding baseline explanation uses owner-approved fixed canary controls", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/baseline-capability`/);
  assert.match(settings, /baseline-capability\/benchmark/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/baseline-capability`/);
  assert.match(settings, /method: "PUT"/);
  assert.match(section, /Optional baseline explanation/);
  assert.match(section, /made-up onboarding baseline/);
  assert.match(section, /No customer website, Google data, traffic, ranking, or account information is sent/);
  assert.match(section, /Check baseline compatibility/);
  assert.match(section, /Made-up baseline check passed/);
  assert.match(section, /Start fixed 5% baseline explanation check/);
  assert.match(section, /Limited baseline explanation check is on/);
  assert.match(section, /Stop baseline explanation check/);
  assert.match(section, /shares one total private prompt per day/);
  assert.match(section, /Any failure stops this capability and uses managed AI/);
  assert.match(settings, /reviewed_baseline_check/);
  assert.match(settings, /understands_real_saved_baseline_context/);
  assert.match(settings, /understands_shared_daily_limit/);
  assert.match(settings, /understands_managed_fallback_and_rollback/);
  assert.match(settings, /understands_explanation_only_no_changes/);
  assert.match(section, /cannot change the score, diagnosis, priorities, fixes, website, or business profile/);
  assert.match(settings, /explanation_only: true/);
  assert.match(settings, /scores_changed: false/);
  assert.match(settings, /diagnosis_changed: false/);
  assert.match(settings, /fixes_changed: false/);
  assert.match(settings, /website_changes_allowed: false/);
  assert.doesNotMatch(section, />\s*(?:Apply diagnosis|Run baseline fixes|Change baseline score)\s*</i);
});

test("review reply wording requires a separate fixed canary and can never post", () => {
  assert.match(settings, /`\/ai\/providers\/\$\{provider\.id\}\/review-response-capability`/);
  assert.match(settings, /review-response-capability\/benchmark/);
  assert.match(section, /Optional review reply wording/);
  assert.match(section, /safe reply for a made-up review/);
  assert.match(section, /No customer review, customer name, business account, or profile data is sent/);
  assert.match(section, /Check review-reply compatibility/);
  assert.match(section, /Made-up review reply check passed/);
  assert.match(settings, /`\/ai\/providers\/\$\{connectionId\}\/review-response-capability`/);
  assert.match(settings, /method: "PUT"/);
  assert.match(section, /Start fixed 5% review-reply wording check/);
  assert.match(section, /Limited review-reply wording check is on/);
  assert.match(section, /Stop review-reply wording check/);
  assert.match(section, /shares one total private prompt per day/);
  assert.match(section, /Any failure stops this capability and uses managed AI/);
  assert.match(settings, /reviewed_review_reply_check/);
  assert.match(settings, /understands_real_saved_review_context/);
  assert.match(settings, /understands_shared_daily_limit/);
  assert.match(settings, /understands_managed_fallback_and_rollback/);
  assert.match(settings, /understands_draft_only_no_posting/);
  assert.match(section, /disabled={!allReviewResponseAcknowledged/);
  assert.match(section, /cannot approve or post a reply, change review status, publish/);
  assert.match(settings, /customer_review_sent: false/);
  assert.match(settings, /review_status_changed: false/);
  assert.match(settings, /may_post_response: false/);
  assert.doesNotMatch(section, />\s*(?:Post reply|Approve reply|Send reply|Auto-post replies)\s*</i);
});
