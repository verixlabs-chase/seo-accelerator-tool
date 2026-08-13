import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


const progressSource = readFileSync(
  new URL("../app/(product)/opportunities/ProgressMilestones.tsx", import.meta.url),
  "utf8",
);
const opportunitiesSource = readFileSync(
  new URL("../app/(product)/opportunities/page.tsx", import.meta.url),
  "utf8",
);


test("next steps shows compact evidence-backed progress beside the action plan", () => {
  assert.match(opportunitiesSource, /ProgressMilestones campaignId=\{selectedCampaignId\}/);
  assert.match(progressSource, /Progress you earned/);
  assert.match(progressSource, /Your next milestone/);
  assert.match(progressSource, /Proof:/);
  assert.match(progressSource, /scope\.label/);
  assert.match(progressSource, /earned_at/);
  assert.match(progressSource, /Healthy habits/);
  assert.match(progressSource, /All-location progress/);
  assert.match(progressSource, /progress_earned_count/);
});


test("milestones evaluate deterministically and preferences preserve history", () => {
  assert.match(progressSource, /engagement\/achievements\/evaluate/);
  assert.match(progressSource, /engagement\/achievement-preferences/);
  assert.match(progressSource, /Dismiss milestone message/);
  assert.match(progressSource, /Show milestone messages/);
  assert.match(progressSource, /Allow progress reminders/);
  assert.match(progressSource, /checklist_completion/);
  assert.match(progressSource, /portfolio_data_current/);
});


test("progress language rejects points games and unsupported result claims", () => {
  assert.doesNotMatch(progressSource, /leaderboard|points earned|daily streak/i);
  assert.match(
    progressSource,
    /Completing a checklist alone never claims that results improved\./,
  );
  assert.match(
    progressSource,
    /Improvement milestones will appear only after a fresh measurement proves the result\./,
  );
});
