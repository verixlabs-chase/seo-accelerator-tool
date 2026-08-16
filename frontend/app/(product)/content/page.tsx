"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  DetailsDisclosure,
  EmptyState,
  KpiCard,
  LoadingCard,
  OwnerDecisionPanel,
  PageSection,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type ContentPage = {
  id: string;
  title: string;
  url: string;
  page_type: string;
  publication_state: string;
  source: "connected_website" | "website_scan" | string;
  source_label: string;
  last_checked_at: string;
  word_count: number;
  attention: string[];
};

type ContentBrief = {
  id: string;
  status: string;
  title: string;
  primary_search: string;
  recommended_page_action: string;
  target_url?: string | null;
  competitor_domain: string;
  competitor_url?: string | null;
  service_name?: string | null;
  service_area_name?: string | null;
  evidence: {
    owner_position?: number | null;
    competitor_position?: number | null;
    search_volume?: number | null;
    source_updated_at?: string | null;
    evidence_note?: string | null;
  };
  outline: Array<{ order: number; heading: string; guidance: string }>;
  created_at: string;
  working_draft?: WorkingContentDraft | null;
};

type WorkingContentDraft = {
  id: string;
  status: "working";
  title: string;
  sections: Array<{ order: number; heading: string; guidance?: string; body: string }>;
  revision: number;
  created_at: string;
  updated_at: string;
  ai_suggestion?: ContentDraftAISuggestionResult | null;
  metadata_recommendations?: ContentMetadataRecommendation[];
  structured_data_recommendation?: ContentStructuredDataRecommendation | null;
  internal_link_recommendations?: ContentInternalLinkRecommendations | null;
  safety: {
    ai_generated: false;
    automatic_publishing_allowed: false;
    website_changed: false;
    approval_to_publish_recorded: false;
  };
};

type ContentMetadataRecommendation = {
  code: "seo_title" | "meta_description";
  label: string;
  state: "add" | "review" | "matches" | "not_enough_information";
  current_value?: string | null;
  current_label: string;
  proposed_value?: string | null;
  proposed_character_count?: number | null;
  review_after_characters: number;
  reason: string;
  evidence: string[];
  source_label?: string | null;
  observed_at?: string | null;
  limitations: string[];
  safety: {
    owner_approval_required: true;
    automatic_publishing_allowed: false;
    website_changed: false;
  };
};

type ContentStructuredDataRecommendation = {
  state: "add" | "prepare" | "matches" | "fix_saved_code" | "not_enough_information";
  recommended_type?: "Service" | null;
  recommended_type_label?: string | null;
  current_types: string[];
  current_state: "not_saved" | "invalid" | "present" | "not_found";
  fields: Array<{
    code: "service_name" | "service_area" | "page_url" | "business_identity";
    label: string;
    value?: string | null;
    state: "confirmed" | "missing" | "optional_not_saved" | "owner_confirmation_required";
    required: boolean;
  }>;
  reason: string;
  evidence: string[];
  source_label?: string | null;
  observed_at?: string | null;
  limitations: string[];
  safety: {
    owner_approval_required: true;
    publishable_code_created: false;
    automatic_publishing_allowed: false;
    website_changed: false;
  };
};

type ContentInternalLinkRecommendations = {
  state:
    | "recommendations_ready"
    | "already_supported"
    | "no_related_pages"
    | "target_not_saved"
    | "not_enough_information";
  target: { title?: string | null; url?: string | null };
  items: Array<{
    state: "recommended" | "already_exists";
    source_title: string;
    source_url: string;
    target_title?: string | null;
    target_url: string;
    suggested_anchor: string;
    relationship_evidence: string[];
    source_label?: string | null;
    observed_at?: string | null;
    existing_link_found: boolean;
  }>;
  reason: string;
  limitations: string[];
  safety: {
    owner_approval_required: true;
    link_insertion_allowed: false;
    automatic_publishing_allowed: false;
    website_changed: false;
  };
};

type ContentDraftAISuggestion = {
  draft_id: string;
  suggestion_state: "ready" | "not_enough_information";
  suggested_title: string;
  sections: Array<{ order: number; heading: string; body: string }>;
  evidence_used: string[];
  uncertainties: string[];
  approval_required: true;
  can_publish: false;
};

type ContentDraftAISuggestionResult = {
  state: string;
  suggestion?: ContentDraftAISuggestion | null;
  updated_at?: string;
  safety: {
    owner_draft_changed: false;
    approval_recorded: false;
    automatic_publishing_allowed: false;
    website_changed: false;
  };
};

type ContentWork = {
  id: string;
  title: string;
  status: string;
  target_url?: string | null;
  planned_month: number;
  updated_at: string;
};

type ContentWorkspace = {
  location: {
    campaign_id: string;
    business_location_id?: string | null;
    name: string;
    domain: string;
  };
  capabilities?: { working_drafts_available?: boolean };
  truth: { state: string; summary: string; limitations: string[] };
  summary: {
    pages: number;
    pages_needing_attention: number;
    draft_briefs: number;
    working_drafts: number;
    planned_work: number;
    published_work: number;
  };
  sources: Array<{
    code: string;
    label: string;
    state: string;
    last_checked_at?: string | null;
  }>;
  pages: ContentPage[];
  briefs: ContentBrief[];
  work: ContentWork[];
  next_action: { code: string; label: string; detail: string; href?: string | null };
};

type ContentBriefReviewResult = {
  changed: boolean;
  message: string;
  item: ContentBrief;
  safety: {
    brief_evidence_changed: false;
    draft_generated: false;
    publishing_enabled: false;
    website_changed: false;
  };
};

type ContentDraftMutationResult = {
  created?: boolean;
  changed?: boolean;
  message: string;
  item: WorkingContentDraft;
};

const SAFE_ACTION_PATHS = new Set(["/content#briefs", "/content#pages", "/site-health", "/competitors"]);

function formatDate(value?: string | null) {
  if (!value) return "Not checked yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Saved date unavailable";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function actionLabel(value: string) {
  if (value === "improve_existing_page") return "Improve the existing page";
  if (value === "create_service_page") return "Prepare a new service page";
  return "Review the page choice";
}

function publicationLabel(value: string) {
  if (value === "publish" || value === "public") return "Public page";
  if (value === "draft") return "Saved draft";
  if (value === "private") return "Private page";
  if (value === "needs_attention") return "Page needs attention";
  return value.replaceAll("_", " ");
}

function metadataStateLabel(value: ContentMetadataRecommendation["state"]) {
  if (value === "add") return "Add this";
  if (value === "matches") return "Already matches";
  if (value === "not_enough_information") return "More information needed";
  return "Review the difference";
}

function structuredDataStateLabel(value: ContentStructuredDataRecommendation["state"]) {
  if (value === "add") return "Details recommended";
  if (value === "prepare") return "Ready for page planning";
  if (value === "matches") return "Already represented";
  if (value === "fix_saved_code") return "Saved code needs review";
  return "More information needed";
}

function structuredDataFieldStateLabel(
  value: ContentStructuredDataRecommendation["fields"][number]["state"],
) {
  if (value === "confirmed") return "Confirmed";
  if (value === "owner_confirmation_required") return "Owner confirmation needed";
  if (value === "optional_not_saved") return "Optional — not saved";
  return "Missing";
}

function internalLinkStateLabel(value: ContentInternalLinkRecommendations["state"]) {
  if (value === "recommendations_ready") return "Links to review";
  if (value === "already_supported") return "Links already found";
  if (value === "target_not_saved") return "Final page address needed";
  if (value === "not_enough_information") return "More information needed";
  return "No safe suggestion yet";
}

function WorkingDraftEditor({
  draft,
  campaignId,
  onSaved,
}: {
  draft: WorkingContentDraft;
  campaignId: string;
  onSaved: (message: string) => Promise<void>;
}) {
  const [title, setTitle] = useState(draft.title);
  const [sections, setSections] = useState(draft.sections);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [suggestionMessage, setSuggestionMessage] = useState("");

  const hasUnsavedChanges = title !== draft.title
    || JSON.stringify(sections) !== JSON.stringify(draft.sections);

  useEffect(() => {
    setTitle(draft.title);
    setSections(draft.sections);
  }, [draft.id, draft.revision, draft.sections, draft.title]);

  async function saveDraft() {
    if (saving) return;
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const result = (await platformApi(`/content/drafts/${encodeURIComponent(draft.id)}`, {
        method: "PUT",
        body: JSON.stringify({
          campaign_id: campaignId,
          title,
          sections: sections.map((section) => ({
            order: section.order,
            heading: section.heading,
            body: section.body,
          })),
        }),
      })) as ContentDraftMutationResult;
      setMessage(result.message);
      await onSaved(result.message);
    } catch {
      setError("The working draft could not be saved. Nothing was published.");
    } finally {
      setSaving(false);
    }
  }

  async function suggestWording() {
    if (suggesting || hasUnsavedChanges) return;
    setSuggesting(true);
    setSuggestionMessage("");
    setError("");
    try {
      const result = (await platformApi(
        `/content/drafts/${encodeURIComponent(draft.id)}/ai-suggestion`,
        {
          method: "POST",
          body: JSON.stringify({ campaign_id: campaignId }),
        },
      )) as ContentDraftAISuggestionResult;
      if (result.state === "available" && result.suggestion) {
        setSuggestionMessage("A separate wording suggestion is ready for review. Your working draft was not changed.");
        await onSaved("AI wording suggestion saved separately. Your working draft was not changed.");
      } else if (result.state === "allowance_exhausted") {
        setSuggestionMessage("The included AI writing allowance is used for this period. Your working draft was not changed.");
      } else if (result.state === "not_configured") {
        setSuggestionMessage("Optional AI wording is not available yet. You can keep writing and saving the draft normally.");
      } else {
        setSuggestionMessage("AI wording could not be prepared from the saved evidence. Your working draft was not changed.");
      }
    } catch {
      setError("The optional AI wording could not be prepared. Your working draft was not changed.");
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <section className="mt-4 border-t border-[#2a2b30] pt-4" aria-label="Editable working draft">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold text-white">Working draft</p>
          <p className="mt-1 text-xs text-zinc-500">Revision {draft.revision} · saved {formatDate(draft.updated_at)}</p>
        </div>
        <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-1 text-xs text-amber-100">
          Not approved or published
        </span>
      </div>
      <label className="mt-4 block text-sm font-medium text-zinc-200">
        Page heading
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={320}
          className="mt-2 w-full rounded-md border border-[#34353b] bg-[#111214] px-3 py-2 text-zinc-100 outline-none focus:border-accent-500"
        />
      </label>
      <div className="mt-4 space-y-4">
        {sections.map((section, index) => (
          <section key={`${draft.id}-${section.order}`} className="border-l-2 border-[#34353b] pl-3">
            <label className="block text-sm font-medium text-zinc-200">
              Section {section.order} heading
              <input
                value={section.heading}
                onChange={(event) => setSections((current) => current.map((item, itemIndex) => (
                  itemIndex === index ? { ...item, heading: event.target.value } : item
                )))}
                maxLength={160}
                className="mt-2 w-full rounded-md border border-[#34353b] bg-[#111214] px-3 py-2 text-zinc-100 outline-none focus:border-accent-500"
              />
            </label>
            {section.guidance ? <p className="mt-2 text-xs leading-5 text-zinc-500">Guide: {section.guidance}</p> : null}
            <label className="mt-3 block text-sm font-medium text-zinc-200">
              Your wording
              <textarea
                value={section.body}
                onChange={(event) => setSections((current) => current.map((item, itemIndex) => (
                  itemIndex === index ? { ...item, body: event.target.value } : item
                )))}
                maxLength={3000}
                rows={5}
                placeholder="Write or paste the wording for this section."
                className="mt-2 w-full resize-y rounded-md border border-[#34353b] bg-[#111214] px-3 py-2 text-zinc-100 outline-none focus:border-accent-500"
              />
            </label>
          </section>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void saveDraft()}
          disabled={saving || !title.trim()}
          className="rounded-md bg-accent-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save working draft"}
        </button>
        <p className="text-xs text-zinc-500">Saving stores owner-written text only. It cannot contact WordPress or publish.</p>
      </div>
      {(draft.metadata_recommendations || []).length ? (
        <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <DetailsDisclosure
            label="Title and search-description recommendations"
            summary="Compared with the latest exact page evidence when it was available"
          >
            <div className="space-y-4">
              {(draft.metadata_recommendations || []).map((item) => (
                <article key={`${draft.id}-${item.code}`} className="rounded-md border border-[#303238] bg-[#111214] p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-zinc-100">{item.label}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {item.source_label
                          ? `${item.source_label} · checked ${formatDate(item.observed_at)}`
                          : "No exact current page value was saved"}
                      </p>
                    </div>
                    <span className="rounded-full border border-emerald-500/25 px-2 py-1 text-xs text-emerald-100">
                      {metadataStateLabel(item.state)}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">{item.current_label}</p>
                      <p className="mt-1 text-sm leading-6 text-zinc-300">{item.current_value || "No saved value"}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Proposed wording</p>
                      <p className="mt-1 text-sm leading-6 text-zinc-100">
                        {item.proposed_value || "The confirmed facts are not sufficient for a safe suggestion."}
                      </p>
                      {item.proposed_character_count !== null && item.proposed_character_count !== undefined ? (
                        <p className="mt-1 text-xs text-zinc-500">
                          {item.proposed_character_count} characters · review after {item.review_after_characters}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-zinc-400">{item.reason}</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">Evidence: {item.evidence.join(" · ")}</p>
                </article>
              ))}
              <p className="text-xs leading-5 text-zinc-500">
                Character checks are writing guidance, not Google ranking rules. Google may display different wording.
                These recommendations have not changed the working draft or website.
              </p>
            </div>
          </DetailsDisclosure>
        </div>
      ) : null}
      {draft.structured_data_recommendation ? (
        <div className="mt-4 rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
          <DetailsDisclosure
            label="Structured page details"
            summary="Checks saved behind-the-scenes page details against the accepted service brief"
          >
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-zinc-100">
                    {draft.structured_data_recommendation.recommended_type_label || "Page details need more information"}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {draft.structured_data_recommendation.source_label
                      ? `${draft.structured_data_recommendation.source_label} · checked ${formatDate(draft.structured_data_recommendation.observed_at)}`
                      : "No exact current page details were saved"}
                  </p>
                </div>
                <span className="rounded-full border border-violet-400/25 px-2 py-1 text-xs text-violet-100">
                  {structuredDataStateLabel(draft.structured_data_recommendation.state)}
                </span>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                <div className="rounded-md border border-[#303238] bg-[#111214] p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Current page types</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-300">
                    {draft.structured_data_recommendation.current_types.length
                      ? draft.structured_data_recommendation.current_types.join(" · ")
                      : "None found in the saved check"}
                  </p>
                </div>
                <div className="rounded-md border border-[#303238] bg-[#111214] p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Recommended detail type</p>
                  <p className="mt-2 text-sm font-medium text-zinc-100">
                    {draft.structured_data_recommendation.recommended_type_label || "Not ready yet"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-zinc-500">{draft.structured_data_recommendation.reason}</p>
                </div>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {draft.structured_data_recommendation.fields.map((field) => (
                  <div key={`${draft.id}-structured-${field.code}`} className="rounded-md border border-[#303238] bg-[#111214] p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-zinc-200">{field.label}</p>
                      <span className="text-xs text-zinc-500">{structuredDataFieldStateLabel(field.state)}</span>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-zinc-100">{field.value || "No confirmed value"}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs leading-5 text-zinc-500">
                Evidence: {draft.structured_data_recommendation.evidence.join(" · ")}
              </p>
              <p className="text-xs leading-5 text-zinc-500">
                This does not generate or publish website code. Structured details do not guarantee a special search result
                or higher rankings. Confirm the public business identity and final page address before a later change preview.
              </p>
            </div>
          </DetailsDisclosure>
        </div>
      ) : null}
      {draft.internal_link_recommendations ? (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <DetailsDisclosure
            label="Helpful links between pages"
            summary="Uses exact saved page titles and accepted service wording"
          >
            <div className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-zinc-100">
                    {draft.internal_link_recommendations.target.title || "Target page not named yet"}
                  </p>
                  <p className="mt-1 break-all text-xs text-zinc-500">
                    {draft.internal_link_recommendations.target.url || "Save the final page address before planning links."}
                  </p>
                </div>
                <span className="rounded-full border border-amber-400/25 px-2 py-1 text-xs text-amber-100">
                  {internalLinkStateLabel(draft.internal_link_recommendations.state)}
                </span>
              </div>
              <p className="text-sm leading-6 text-zinc-400">{draft.internal_link_recommendations.reason}</p>
              {draft.internal_link_recommendations.items.length ? (
                <div className="space-y-3">
                  {draft.internal_link_recommendations.items.map((item) => (
                    <article key={`${draft.id}-link-${item.source_url}-${item.target_url}`} className="rounded-md border border-[#303238] bg-[#111214] p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Link from this saved page</p>
                          <p className="mt-1 font-medium text-zinc-100">{item.source_title}</p>
                          <p className="mt-1 break-all text-xs text-zinc-500">{item.source_url}</p>
                        </div>
                        <span className="text-xs text-amber-100">
                          {item.existing_link_found ? "Link already found" : "Review suggestion"}
                        </span>
                      </div>
                      <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Link to this page</p>
                          <p className="mt-1 text-sm text-zinc-200">{item.target_title || item.target_url}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Suggested link wording</p>
                          <p className="mt-1 text-sm text-zinc-200">{item.suggested_anchor}</p>
                        </div>
                      </div>
                      <p className="mt-3 text-xs leading-5 text-zinc-500">
                        Evidence: {item.relationship_evidence.join(" · ")}
                        {item.source_label ? ` · ${item.source_label} checked ${formatDate(item.observed_at)}` : ""}
                      </p>
                    </article>
                  ))}
                </div>
              ) : null}
              <p className="text-xs leading-5 text-zinc-500">
                This does not insert links, create website code, or publish anything. Review the surrounding sentence so
                every link is useful to a person. Internal links do not guarantee higher rankings or more traffic.
              </p>
            </div>
          </DetailsDisclosure>
        </div>
      ) : null}
      <div className="mt-4 rounded-lg border border-sky-500/20 bg-sky-500/5 p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-medium text-sky-100">Optional AI wording</p>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-zinc-400">
              Uses the accepted brief and saved headings and guidance. It does not read or overwrite your section text,
              approve the draft, contact WordPress, or publish. One included AI action is used when the writing service runs.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void suggestWording()}
            disabled={suggesting || hasUnsavedChanges}
            className="rounded-md border border-sky-400/30 px-3 py-2 text-sm font-semibold text-sky-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {suggesting ? "Preparing suggestion…" : "Suggest wording with AI"}
          </button>
        </div>
        {hasUnsavedChanges ? (
          <p className="mt-2 text-xs text-amber-100">Save your changes first so the suggestion uses the current saved revision.</p>
        ) : null}
        {suggestionMessage ? <p role="status" className="mt-2 text-sm text-sky-100">{suggestionMessage}</p> : null}
        {draft.ai_suggestion?.state === "available" && draft.ai_suggestion.suggestion ? (
          <div className="mt-3">
            <DetailsDisclosure
              label="AI wording suggestion — review before using"
              summary="Saved separately from your working draft"
            >
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Suggested page heading</p>
                  <p className="mt-1 font-medium text-zinc-100">{draft.ai_suggestion.suggestion.suggested_title}</p>
                </div>
                {draft.ai_suggestion.suggestion.sections.map((section) => (
                  <section key={`${draft.id}-suggestion-${section.order}`} className="border-l-2 border-sky-500/30 pl-3">
                    <p className="font-medium text-zinc-100">{section.order}. {section.heading}</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-300">{section.body}</p>
                  </section>
                ))}
                <p className="text-xs leading-5 text-zinc-500">
                  Evidence used: accepted content brief and saved headings and section guidance. This suggestion has not changed your working draft.
                </p>
                {draft.ai_suggestion.suggestion.uncertainties.length ? (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Check before using</p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-400">
                      {draft.ai_suggestion.suggestion.uncertainties.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
              </div>
            </DetailsDisclosure>
          </div>
        ) : null}
      </div>
      {message ? <p role="status" className="mt-3 text-sm text-emerald-100">{message}</p> : null}
      {error ? <p role="alert" className="mt-3 text-sm text-rose-100">{error}</p> : null}
    </section>
  );
}

export default function ContentWorkspacePage() {
  const pathname = usePathname();
  const router = useRouter();
  const { campaigns, selectedCampaign, selectedCampaignId, loadingLocations } = useLocationContext();
  const [payload, setPayload] = useState<ContentWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [briefReviewBusy, setBriefReviewBusy] = useState("");
  const [briefReviewMessage, setBriefReviewMessage] = useState("");
  const [briefReviewError, setBriefReviewError] = useState("");
  const [draftCreateBusy, setDraftCreateBusy] = useState("");

  const loadWorkspace = useCallback(async (campaignId: string, refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const response = (await platformApi(
        `/content/workspace?campaign_id=${encodeURIComponent(campaignId)}`,
      )) as ContentWorkspace;
      setPayload(response);
    } catch {
      setError("The saved content workspace could not be loaded.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedCampaignId) {
      setPayload(null);
      return;
    }
    void loadWorkspace(selectedCampaignId);
  }, [loadWorkspace, selectedCampaignId]);

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(() => {
    if (error) return [{ label: "Saved content", value: "Needs a reload", tone: "warning" }];
    return [];
  }, [error]);
  const lastSavedAt = useMemo(() => {
    const values = payload?.sources
      .map((source) => source.last_checked_at)
      .filter((value): value is string => Boolean(value)) || [];
    return values.sort().at(-1) || null;
  }, [payload]);
  const firstDraftBrief = payload?.briefs?.find((brief) => brief.status === "draft") || null;
  const firstPageNeedingAttention = payload?.pages?.find((page) => page.attention.length > 0) || null;
  const nextHref = payload?.next_action?.href && SAFE_ACTION_PATHS.has(payload.next_action.href)
    ? payload.next_action.href
    : null;

  function followNextAction() {
    if (!nextHref) return;
    if (nextHref.startsWith("/content#")) {
      document.getElementById(nextHref.split("#")[1])?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    router.push(nextHref);
  }

  async function reviewBrief(brief: ContentBrief, decision: "accept" | "decline") {
    if (!selectedCampaignId || briefReviewBusy) return;
    setBriefReviewBusy(brief.id);
    setBriefReviewMessage("");
    setBriefReviewError("");
    try {
      const result = (await platformApi(`/content/briefs/${encodeURIComponent(brief.id)}/review`, {
        method: "PUT",
        body: JSON.stringify({ campaign_id: selectedCampaignId, decision }),
      })) as ContentBriefReviewResult;
      setBriefReviewMessage(result.message);
      await loadWorkspace(selectedCampaignId, true);
    } catch {
      setBriefReviewError("That brief decision could not be saved. Nothing was changed or published.");
    } finally {
      setBriefReviewBusy("");
    }
  }

  async function startWorkingDraft(brief: ContentBrief) {
    if (!selectedCampaignId || draftCreateBusy) return;
    setDraftCreateBusy(brief.id);
    setBriefReviewMessage("");
    setBriefReviewError("");
    try {
      const result = (await platformApi(`/content/briefs/${encodeURIComponent(brief.id)}/draft`, {
        method: "POST",
        body: JSON.stringify({ campaign_id: selectedCampaignId }),
      })) as ContentDraftMutationResult;
      setBriefReviewMessage(result.message);
      await loadWorkspace(selectedCampaignId, true);
    } catch {
      setBriefReviewError("The working draft could not be started. Nothing was generated or published.");
    } finally {
      setDraftCreateBusy("");
    }
  }

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed location"} / ${selectedCampaign.domain || "No website"}`
          : "No location selected"
      }
      dateRangeLabel={lastSavedAt ? `Saved ${formatDate(lastSavedAt)}` : "No saved page check"}
      topBarActions={
        <button
          type="button"
          onClick={() => selectedCampaignId && void loadWorkspace(selectedCampaignId, true)}
          disabled={!selectedCampaignId || loading || refreshing}
          className="rounded-md border border-[#2a2b30] bg-[#141518] px-3 py-1.5 text-sm text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {refreshing ? "Reloading…" : "Reload saved content"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Content"
          title="Plan useful website pages from saved evidence"
          summary="Review saved pages and competitor-backed briefs before writing or changing anything."
        />

        <TruthNotice title="Nothing on this page can publish to your website.">
          This workspace uses saved page checks and confirmed research. A brief is a reviewable plan,
          not proof that a page change will improve rankings.
        </TruthNotice>

        {loading || loadingLocations ? (
          <LoadingCard
            title="Loading saved pages and briefs"
            summary="Checking this location for saved website pages, page issues, and research-backed drafts."
          />
        ) : null}

        {!loading && !loadingLocations && campaigns.length === 0 ? (
          <EmptyState
            title="Set up a location first"
            summary="Content pages and briefs stay separate for every location. Add a location before planning page work."
            actionLabel="Open setup"
            onAction={() => router.push("/dashboard")}
            icon="locations"
          />
        ) : null}

        {error ? (
          <section role="alert" className="border-y border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            <p className="font-semibold">{error}</p>
            <p className="mt-1 text-rose-100/80">
              {payload ? "The last saved workspace remains below." : "Try again later. No missing page is being reported as healthy."}
            </p>
          </section>
        ) : null}

        {!loading && payload ? (
          <OwnerDecisionPanel
            eyebrow="Current content result"
            title={
              firstDraftBrief
                ? `${payload.summary.draft_briefs} content brief${payload.summary.draft_briefs === 1 ? " is" : "s are"} ready for review`
                : firstPageNeedingAttention
                  ? `${payload.summary.pages_needing_attention} page${payload.summary.pages_needing_attention === 1 ? " needs" : "s need"} attention`
                  : payload.summary.pages
                    ? "Saved pages are ready for content planning"
                    : "No saved website pages yet"
            }
            summary={payload.truth.summary}
            nextStep={payload.next_action.detail}
            actionLabel={nextHref ? payload.next_action.label : undefined}
            onAction={nextHref ? followNextAction : undefined}
            tone={firstDraftBrief ? "neutral" : firstPageNeedingAttention ? "warning" : payload.summary.pages ? "positive" : "neutral"}
          />
        ) : null}

        {briefReviewMessage ? (
          <section role="status" className="border-y border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {briefReviewMessage}
          </section>
        ) : null}

        {briefReviewError ? (
          <section role="alert" className="border-y border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {briefReviewError}
          </section>
        ) : null}

        {!loading && payload ? (
          <section aria-label="Saved content facts" className="grid gap-px bg-[#26272c] sm:grid-cols-2 xl:grid-cols-5">
            <KpiCard
              label="Saved pages"
              value={payload.summary.pages.toLocaleString()}
              summary="Public pages and drafts found in the latest saved website evidence."
              icon="content"
            />
            <KpiCard
              label="Pages needing attention"
              value={payload.summary.pages_needing_attention.toLocaleString()}
              summary="Pages with a clear saved issue such as a missing description or too little useful detail."
              icon="warning"
            />
            <KpiCard
              label="Draft briefs"
              value={payload.summary.draft_briefs.toLocaleString()}
              summary="Research-backed page plans waiting for a person to review."
              icon="reports"
            />
            <KpiCard
              label="Working drafts"
              value={payload.summary.working_drafts.toLocaleString()}
              summary="Owner-editable page wording saved in InsightOS and not approved for publishing."
              icon="content"
            />
            <KpiCard
              label="Published work"
              value={payload.summary.published_work.toLocaleString()}
              summary="Saved content work already marked as published in InsightOS."
              icon="check"
            />
          </section>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="Content briefs ready for review"
            summary="Each brief starts from one confirmed customer search and competitor gap."
            icon="reports"
          >
            <div id="briefs" className="scroll-mt-24">
              {payload.briefs.length === 0 ? (
                <EmptyState
                  title="No content briefs are saved yet"
                  summary="Confirm real competitors and exact search gaps before creating a review-only page plan."
                  actionLabel="Review competitors"
                  onAction={() => router.push("/competitors")}
                  icon="content"
                />
              ) : (
                <div className="space-y-3">
                  {payload.briefs.map((brief) => (
                    <article key={brief.id} className="border-y border-[#2a2b30] bg-white/[0.015] px-4 py-4">
                      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,0.35fr)]">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-full border px-2 py-0.5 text-xs ${
                              brief.status === "accepted"
                                ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                                : brief.status === "declined"
                                  ? "border-zinc-600/50 bg-zinc-800/60 text-zinc-300"
                                  : "border-accent-500/25 bg-accent-500/10 text-accent-100"
                            }`}>
                              {brief.status === "accepted"
                                ? "Page target accepted"
                                : brief.status === "declined"
                                  ? "Brief declined"
                                  : "Draft for review"}
                            </span>
                            <span className="text-xs text-zinc-500">Saved {formatDate(brief.created_at)}</span>
                          </div>
                          <h3 className="mt-2 text-lg font-semibold text-white">{brief.title}</h3>
                          <p className="mt-1 text-sm text-zinc-300">
                            Customer search: <strong className="font-medium text-zinc-100">{brief.primary_search}</strong>
                          </p>
                          <p className="mt-1 text-sm text-zinc-400">
                            {actionLabel(brief.recommended_page_action)}
                            {brief.target_url ? ` · ${brief.target_url}` : ""}
                          </p>
                        </div>
                        <div className="border-t border-[#2a2b30] pt-3 text-sm lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">Saved evidence</p>
                          <p className="mt-2 text-zinc-300">Confirmed competitor: {brief.competitor_domain}</p>
                          <p className="mt-1 text-zinc-400">
                            Their saved position: {brief.evidence.competitor_position ?? "Not available"}
                            {" · "}Your saved position: {brief.evidence.owner_position ?? "Not found"}
                          </p>
                        </div>
                      </div>
                      <DetailsDisclosure
                        label="Review the suggested page outline"
                        summary={`${brief.outline.length} sections based on this exact saved gap.`}
                      >
                        <ol className="space-y-3">
                          {brief.outline.map((section) => (
                            <li key={`${brief.id}-${section.order}`} className="border-l-2 border-accent-500/30 pl-3">
                              <p className="font-medium text-zinc-100">{section.order}. {section.heading}</p>
                              <p className="mt-1 text-sm leading-5 text-zinc-400">{section.guidance}</p>
                            </li>
                          ))}
                        </ol>
                      </DetailsDisclosure>
                      {brief.status === "draft" ? (
                        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#2a2b30] pt-4">
                          <button
                            type="button"
                            onClick={() => void reviewBrief(brief, "accept")}
                            disabled={Boolean(briefReviewBusy)}
                            className="rounded-md bg-accent-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {briefReviewBusy === brief.id
                              ? "Saving decision…"
                              : brief.recommended_page_action === "create_service_page"
                                ? "Accept new page target"
                                : "Accept page target"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void reviewBrief(brief, "decline")}
                            disabled={Boolean(briefReviewBusy)}
                            className="rounded-md border border-[#34353b] px-3 py-2 text-sm font-medium text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Decline brief
                          </button>
                          <p className="text-xs text-zinc-500">
                            Accepting saves the page choice for a later drafting step. It does not write or publish content.
                          </p>
                        </div>
                      ) : brief.status === "accepted" ? (
                        brief.working_draft ? (
                          <WorkingDraftEditor
                            draft={brief.working_draft}
                            campaignId={selectedCampaignId || ""}
                            onSaved={async (message) => {
                              setBriefReviewMessage(message);
                              if (selectedCampaignId) await loadWorkspace(selectedCampaignId, true);
                            }}
                          />
                        ) : payload.capabilities?.working_drafts_available === true ? (
                          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[#2a2b30] pt-4">
                            <button
                              type="button"
                              onClick={() => void startWorkingDraft(brief)}
                              disabled={Boolean(draftCreateBusy)}
                              className="rounded-md bg-accent-500 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {draftCreateBusy === brief.id ? "Starting…" : "Start empty working draft"}
                            </button>
                            <p className="text-xs text-zinc-500">
                              This copies the accepted headings into an editable workspace. It does not generate or publish wording.
                            </p>
                          </div>
                        ) : (
                          <p className="mt-4 border-t border-[#2a2b30] pt-3 text-sm text-amber-100">
                            The page choice is saved. Working drafts are temporarily unavailable while storage is updated.
                          </p>
                        )
                      ) : null}
                    </article>
                  ))}
                </div>
              )}
            </div>
          </PageSection>
        ) : null}

        {!loading && payload ? (
          <PageSection
            title="Saved website pages"
            summary="Review the clearest saved issues first. A page with no listed issue is not a promise that the page is perfect."
            icon="content"
          >
            <div id="pages" className="scroll-mt-24">
              {payload.pages.length === 0 ? (
                <EmptyState
                  title="No website pages have been saved"
                  summary="Run a website scan or read the connected website before planning page changes."
                  actionLabel="Open Website Health"
                  onAction={() => router.push("/site-health")}
                  icon="website-health"
                />
              ) : (
                <div className="overflow-x-auto border-y border-[#26272c]">
                  <table className="min-w-full border-collapse text-left">
                    <thead className="bg-[#111214]">
                      <tr>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Page</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Saved state</th>
                        <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Needs attention</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payload.pages.map((page) => (
                        <tr key={`${page.source}-${page.id}`} className="border-t border-[#26272c] align-top">
                          <td className="max-w-xl px-4 py-4">
                            <p className="font-medium text-zinc-100">{page.title}</p>
                            <p className="mt-1 break-all text-xs text-zinc-500">{page.url}</p>
                          </td>
                          <td className="whitespace-nowrap px-4 py-4 text-sm text-zinc-300">
                            <p>{publicationLabel(page.publication_state)}</p>
                            <p className="mt-1 text-xs text-zinc-500">{page.source_label} · {formatDate(page.last_checked_at)}</p>
                          </td>
                          <td className="px-4 py-4 text-sm">
                            {page.attention.length ? (
                              <ul className="space-y-1.5 text-amber-100">
                                {page.attention.map((item) => (
                                  <li key={item} className="flex gap-2">
                                    <ProductIcon name="warning" size={15} className="mt-0.5 shrink-0" />
                                    <span>{item}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-zinc-400">No clear issue in this saved check</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </PageSection>
        ) : null}

        {!loading && payload?.work.length ? (
          <PageSection
            title="Saved content work"
            summary="This is the current InsightOS work status. Publishing still requires the separate approved website workflow."
            icon="calendar"
          >
            <ul className="divide-y divide-[#26272c] border-y border-[#26272c]">
              {payload.work.map((item) => (
                <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div>
                    <p className="font-medium text-zinc-100">{item.title}</p>
                    <p className="mt-1 text-xs text-zinc-500">Updated {formatDate(item.updated_at)}</p>
                  </div>
                  <span className="rounded-full border border-[#34353b] px-2.5 py-1 text-xs capitalize text-zinc-300">
                    {item.status}
                  </span>
                </li>
              ))}
            </ul>
          </PageSection>
        ) : null}

        {!loading && payload?.truth.limitations.length ? (
          <details className="border-y border-[#26272c] bg-[#111214] px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-200">What this workspace does not prove</summary>
            <ul className="mt-3 space-y-2 text-sm leading-5 text-zinc-400">
              {payload.truth.limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}
            </ul>
          </details>
        ) : null}
      </section>
    </AppShell>
  );
}
