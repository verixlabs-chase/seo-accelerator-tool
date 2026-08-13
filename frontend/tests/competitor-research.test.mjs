import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(
  fileURLToPath(new URL("../app/(product)/competitors/page.tsx", import.meta.url)),
  "utf8",
);

test("competitor research requires an owner decision before comparison", () => {
  assert.match(page, /\/competitors\/discover/);
  assert.match(page, /Yes, this is a competitor/);
  assert.match(page, /Not a competitor/);
  assert.match(page, /decision: "dismissed"/);
});

test("competitor gaps show exact evidence instead of an invented score", () => {
  assert.match(page, /\/competitors\/research/);
  assert.match(page, /competitor_position/);
  assert.match(page, /owner_position/);
  assert.match(page, /competitor_url/);
  assert.match(page, /source_updated_at/);
  assert.match(page, /No made-up gap score is used/);
  assert.doesNotMatch(page, /gap_score/);
});

test("a reviewed gap can move into rankings or governed next steps", () => {
  assert.match(page, /\/keyword-research\/track/);
  assert.match(page, /Track this search/);
  assert.match(page, /\/keyword-research\/create-action/);
  assert.match(page, /Add to Next Steps/);
});

test("an exact competitor gap can become a review-only content brief", () => {
  assert.match(page, /\/competitors\/content-brief/);
  assert.match(page, /Create content brief/);
  assert.match(page, /Draft content brief/);
  assert.match(page, /Nothing published/);
  assert.match(page, /Review the outline/);
  assert.match(page, /content_brief/);
});

test("competitor movement uses comparable saved positions", () => {
  assert.match(page, /previous_competitor_position/);
  assert.match(page, /movement_direction/);
  assert.match(page, /Competitor movement alerts/);
  assert.match(page, /Earlier check/);
  assert.match(page, /at least three places/);
});

test("authority gaps show exact competitor-only referring pages without an invented score", () => {
  assert.match(page, /\/authority\/link-gaps/);
  assert.match(page, /\/authority\/link-gaps\/refresh/);
  assert.match(page, /Websites that mention competitors, but not you/);
  assert.match(page, /Open the exact page/);
  assert.match(page, /competitor_matches/);
  assert.match(page, /source_url/);
  assert.match(page, /target_url/);
  assert.match(page, /first_seen_at/);
  assert.match(page, /last_seen_at/);
  assert.doesNotMatch(page, /authority_score/);
});

test("owner link history separates explicit new and lost evidence", () => {
  assert.match(page, /\/authority\/link-changes/);
  assert.match(page, /\/authority\/link-changes\/refresh/);
  assert.match(page, /What changed with website mentions/);
  assert.match(page, /New links to review/);
  assert.match(page, /Lost links to investigate/);
  assert.match(page, /change_state/);
  assert.match(page, /source_url/);
  assert.match(page, /target_url/);
  assert.match(page, /verification_goal/);
});

test("authority inventory separates exact incoming links from same-run checked mentions", () => {
  assert.match(page, /\/authority\/inventory/);
  assert.match(page, /\/authority\/inventory\/refresh/);
  assert.match(page, /Exact business name/);
  assert.match(page, /Links you have and mentions to review/);
  assert.match(page, /no link from that same page was found in the same check/i);
  assert.match(page, /incoming_links/);
  assert.match(page, /exact_name_pages_checked/);
  assert.match(page, /unlinked_mentions/);
  assert.match(page, /unlinked_mention/);
});

test("authority opportunities use local relevance and deduplicated next-step promotion", () => {
  assert.match(page, /relevance_classification/);
  assert.match(page, /matched_services/);
  assert.match(page, /matched_service_areas/);
  assert.match(page, /relevance_label/);
  assert.match(page, /\/authority\/actions/);
  assert.match(page, /Confirm and add to Next Steps/);
});

test("authority outreach stays owner-reviewed and manual-send only", () => {
  assert.match(page, /\/authority\/outreach-drafts/);
  assert.match(page, /Prepare a message/);
  assert.match(page, /I checked the recipient/);
  assert.match(page, /Manual send only/);
  assert.match(page, /Copy message/);
  assert.doesNotMatch(page, /Send message/);
  assert.doesNotMatch(page, /enrich.*contact/i);
});

test("competitor customer copy does not expose the internal market supplier", () => {
  assert.doesNotMatch(page, /dataforseo/i);
});
