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
  const sessionHistory = settings.indexOf("visibleAuthSessions.map(renderAuthSession)", disclosure);
  assert.ok(disclosure >= 0, "account security should be a disclosure");
  assert.ok(sessionHistory > disclosure, "session history should live inside the disclosure");
  assert.match(settings.slice(disclosure, sessionHistory), /Open this only when you want to review or sign out another browser/);
  assert.match(settings.slice(disclosure, sessionHistory), /active \$\{authSessions.length === 1 \? "browser" : "browsers"\}/);
  assert.match(settings, /otherAuthSessions\.slice\(0, 2\)/);
  assert.match(settings, /Show \{additionalAuthSessions\.length\} older signed-in/);
  assert.match(settings, /additionalAuthSessions\.map\(renderAuthSession\)/);
});

test("workflow setup presents three owner steps and explains the n8n production URL", () => {
  assert.match(settings, /Connect Zapier, Make, Pipedream, or n8n/);
  assert.match(settings, /Send updates to another tool/);
  assert.match(settings, /Let a workflow request saved work/);
  assert.match(settings, /aria-pressed=\{automationWorkflowDirection === "outgoing"\}/);
  assert.match(settings, /aria-pressed=\{automationWorkflowDirection === "incoming"\}/);
  assert.match(settings, /setAutomationWorkflowDirection\("outgoing"\)/);
  assert.match(settings, /setAutomationWorkflowDirection\("incoming"\)/);
  assert.match(settings, /automationWorkflowDirection === "outgoing" \? \(/);
  assert.match(settings, /automationWorkflowDirection === "incoming" \? \(/);
  assert.match(settings, /\["1", "Create a receiving webhook"/);
  assert.match(settings, /\["2", "Paste its URL here"/);
  assert.match(settings, /\["3", "Save and send a test"/);
  assert.match(settings, /Paste the receiving address from/);
  assert.match(settings, /copy the Webhook node&apos;s Production URL/);
  assert.match(settings, /temporary Test URL will not work here/);
  assert.doesNotMatch(settings, />\s*External automation\s*</);
  assert.doesNotMatch(settings, />\s*Add a workflow endpoint\s*</);
});

test("workflow tools are a top-level Settings section, not buried under workspace deletion", () => {
  const closure = settings.indexOf('aria-labelledby="workspace-closure-heading"');
  const closureEnd = settings.indexOf("</section>", closure);
  const workflow = settings.indexOf('<section id="external-automation"');
  assert.ok(closure >= 0 && closureEnd > closure);
  assert.ok(workflow > closureEnd, "workflow tools should render after the owner-only closure section ends");
  assert.match(settings.slice(workflow, workflow + 500), /aria-labelledby="workflow-tools-heading"/);
});

test("workflow connections show evidence-backed setup progress instead of treating a saved URL as connected", () => {
  assert.match(settings, /Receiving address saved/);
  assert.match(settings, /Signed test received/);
  assert.match(settings, /First real update received/);
  assert.match(settings, /connection\.verification_status === "verified"/);
  assert.match(settings, /connection\.conformance_proof\.production_proven/);
  assert.match(settings, /A saved address alone is not connected/);
  assert.match(settings, /Test received — ready for automatic updates/);
  assert.match(settings, /Connected and proven with a real update/);
  assert.doesNotMatch(settings, /connection\.status === "active" \? "Sending updates"/);
});

test("provider setup explains where to confirm and recover a test without developer vocabulary", () => {
  assert.match(settings, /How to know the test arrived/);
  assert.match(settings, /selectedAutomationProviderSetup\.test_confirmation/);
  assert.match(settings, /If the test does not arrive/);
  assert.match(settings, /selectedAutomationProviderSetup\.recovery_note/);
  assert.match(settings, /Paste the receiving address from/);
  assert.match(settings, /Keep this workflow security key private/);
  assert.match(settings, /I saved it — send safe test/);
  assert.match(settings, /testAutomationConnection\(automationConnectionReadyToTest\)/);
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
  const optionalAbilities = settings.indexOf("Add more things this workflow may do");
  const optionalReportCreation = settings.indexOf(
    "Let a workflow tool create private reports from saved results",
    optionalAbilities,
  );
  const manageIncomingConnection = settings.indexOf("Manage connection");
  const incomingApiFile = settings.indexOf("Download API file", manageIncomingConnection);

  assert.ok(advanced >= 0 && payload > advanced && signature > payload);
  assert.ok(customUpdates >= 0 && eventMap > customUpdates);
  assert.ok(activity >= 0 && attempts > activity);
  assert.ok(connectionDetails >= 0 && secretVersion > connectionDetails);
  assert.ok(optionalAbilities >= 0 && optionalReportCreation > optionalAbilities);
  assert.ok(manageIncomingConnection >= 0 && incomingApiFile > manageIncomingConnection);
  assert.match(settings, /No extras enabled/);
  assert.match(settings, /Review optional abilities/);
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
  assert.match(ops, /Treat Overview as the primary visualization surface/);
  assert.match(ops, /Are more people finding and[\s\S]*contacting this business/);
  assert.match(ops, /must not resemble a dense specialist analytics console/);
  assert.match(ops, /Overview totals and[\s\S]*reconcile exactly with their source pages/);
});
