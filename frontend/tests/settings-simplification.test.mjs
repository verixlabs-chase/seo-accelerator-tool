import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const settings = readFileSync(
  fileURLToPath(new URL("../app/(product)/settings/page.tsx", import.meta.url)),
  "utf8",
);
const roadmap = readFileSync(
  fileURLToPath(new URL("../../docs/claude-next-build-brief.md", import.meta.url)),
  "utf8",
);

test("Settings starts with plain task-based navigation", () => {
  assert.match(settings, /title="Manage your connections and account"/);
  assert.match(settings, /Technical details stay out of the way unless you open them/);
  assert.match(settings, /aria-label="Settings tasks"/);
  assert.match(settings, /\["Business data", "Connect or repair Google"/);
  assert.match(settings, /\["Workflow tools", "Connect Zapier, Make, or n8n"/);
  assert.match(settings, /\["Plan and billing", "Manage subscription and usage"/);
  assert.match(settings, /\["Account security", "Review other signed-in browsers"/);
});

test("long sign-in history is summarized until the owner opens account security", () => {
  const disclosure = settings.indexOf('<details id="account-security"');
  const sessionHistory = settings.indexOf("authSessions.map((session)", disclosure);
  assert.ok(disclosure >= 0, "account security should be a disclosure");
  assert.ok(sessionHistory > disclosure, "session history should live inside the disclosure");
  assert.match(settings.slice(disclosure, sessionHistory), /Open this only when you want to review or sign out another browser/);
  assert.match(settings.slice(disclosure, sessionHistory), /active \$\{authSessions.length === 1 \? "browser" : "browsers"\}/);
});

test("workflow setup presents three owner steps and explains the n8n production URL", () => {
  assert.match(settings, /Send useful updates to Zapier, Make, Pipedream, or n8n/);
  assert.match(settings, /\["1", "Create a receiving webhook"/);
  assert.match(settings, /\["2", "Paste its URL here"/);
  assert.match(settings, /\["3", "Save and send a test"/);
  assert.match(settings, /Paste the webhook URL from your tool/);
  assert.match(settings, /copy the Webhook node&apos;s Production URL/);
  assert.match(settings, /temporary Test URL will not work here/);
  assert.doesNotMatch(settings, />\s*External automation\s*</);
  assert.doesNotMatch(settings, />\s*Add a workflow endpoint\s*</);
});

test("specialist automation controls are progressively disclosed", () => {
  const advanced = settings.indexOf("Technical verification details (advanced)");
  const payload = settings.indexOf("selectedAutomationProviderSetup.payload_path", advanced);
  const signature = settings.indexOf("selectedAutomationProviderSetup.signature_contract.algorithm", advanced);
  const customUpdates = settings.indexOf("Choose individual updates instead (optional)");
  const eventMap = settings.indexOf("automationEvents.map((event)", customUpdates);
  const activity = settings.indexOf("Workflow activity this month");
  const attempts = settings.indexOf("automationMonthlyUsage.attempts", activity);
  const connectionDetails = settings.indexOf("Connection details (advanced)");
  const secretVersion = settings.indexOf("connection.signing_secret_version", connectionDetails);

  assert.ok(advanced >= 0 && payload > advanced && signature > payload);
  assert.ok(customUpdates >= 0 && eventMap > customUpdates);
  assert.ok(activity >= 0 && attempts > activity);
  assert.ok(connectionDetails >= 0 && secretVersion > connectionDetails);
  assert.match(settings, /See every update InsightOS can send/);
  assert.match(settings, /Workflow tools can receive updates\. They cannot approve recommendations/);
});

test("the final launch sprint requires whole-product testing with non-technical owners", () => {
  const opsStart = roadmap.indexOf("### Operations OPS1 - Customer Support and Launch Operations");
  const opsEnd = roadmap.indexOf("### Automation AUT1", opsStart);
  const ops = roadmap.slice(opsStart, opsEnd);

  assert.match(ops, /final whole-product usability gate/);
  assert.match(ops, /Inventory and test every customer-visible route, navigation menu, section/);
  assert.match(ops, /Long records[\s\S]*Where you're signed in[\s\S]*collapsed/);
  assert.match(ops, /connect Zapier\/Make\/n8n/);
  assert.match(ops, /At least five representative non-technical participants/);
  assert.match(ops, /wall of records, unexplained technical language/);
  assert.match(ops, /whole-product visualization audit/);
  assert.match(ops, /every graph must answer a named owner question/);
  assert.match(ops, /unavailable source is never rendered as zero/);
  assert.match(ops, /at least two comparable saved observations/);
  assert.match(ops, /Every plotted point[\s\S]*saved source record or reproducible aggregate/);
  assert.match(ops, /keyboard and screen-reader equivalent/);
  assert.match(ops, /matches the numbers in tables and exported reports/);
});
