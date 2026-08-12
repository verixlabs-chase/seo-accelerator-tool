"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import QRCode from "qrcode";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AppShell,
  EmptyState,
  KpiCard,
  LoadingCard,
  ProductPageIntro,
  TruthNotice,
  useLocationContext,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi } from "../../platform/api";

type Campaign = {
  id: string;
  name?: string;
  domain?: string;
};

type ReviewItem = {
  id: string;
  source_name: string;
  rating: number;
  body?: string | null;
  author_name?: string | null;
  author_is_anonymous: boolean;
  response_status: string;
  response_text?: string | null;
  response_updated_at?: string | null;
  review_url?: string | null;
  reviewed_at: string;
};

type ReviewSummary = {
  total: number;
  unanswered: number;
  responded: number;
  rating_three_or_lower: number;
  average_rating?: number | null;
  newest_observation_at?: string | null;
};

type ReviewInventory = {
  items: ReviewItem[];
  summary: ReviewSummary;
};

type ReviewResponseDraft = {
  id: string;
  review_id: string;
  status: "human_required" | "ready_for_review" | "approved" | "rejected" | "unavailable";
  risk_class: "standard" | "sensitive";
  sensitive_topics: string[];
  policy_version: string;
  draft_text?: string | null;
  approved_text?: string | null;
  human_reason?: string | null;
  approval_required: boolean;
  posting_enabled: false;
  created_at: string;
};

type ReviewResponsePolicy = {
  mode: "draft_only";
  human_approval_required: true;
  direct_posting_enabled: false;
  automatic_posting_enabled: false;
  ai_configured: boolean;
  maximum_credits_per_draft?: number | null;
};

type ReviewPostingStatus = {
  available: boolean;
  automatic_posting_enabled: false;
  explicit_confirmation_required: true;
  confirmation_version: string;
  confirmation_label: string;
  capability_status: "not_authorized" | "validation_authorized" | "verified" | "revoked";
  reason: string;
  reason_code?: string | null;
};

type ReviewResponseExecution = {
  id: string;
  review_id: string;
  draft_id: string;
  status: "queued" | "posting" | "retrying" | "posted" | "paused" | "blocked" | "failed" | "cancelled";
  attempt_count: number;
  error_code?: string | null;
  error_message?: string | null;
  requested_at: string;
  posted_at?: string | null;
};

type ReviewIntelligenceMetrics = {
  total_reviews: number;
  average_rating?: number | null;
  reviews_last_30_days: number;
  reviews_previous_30_days: number;
  review_pace_change: number;
  unanswered_reviews: number;
  urgent_unanswered_reviews: number;
  response_rate_percent?: number | null;
  median_response_hours?: number | null;
};

type ReviewTrendWeek = {
  week_start: string;
  reviews_received: number;
  average_rating?: number | null;
  positive: number;
  mixed: number;
  negative: number;
};

type ReviewTheme = {
  key: string;
  label: string;
  mentions: number;
  positive_mentions: number;
  mixed_mentions: number;
  negative_mentions: number;
  evidence_review_ids: string[];
  tone: "strength" | "mixed" | "needs_attention";
};

type ReviewAction = {
  id: string;
  priority: "high" | "medium" | "low";
  title: string;
  why: string;
  metric_label: string;
  current_value: number;
  target_value: number;
  evidence_review_ids: string[];
};

type LocationReviewIntelligence = {
  campaign_id: string;
  location_name: string;
  city?: string | null;
  region?: string | null;
  metrics: ReviewIntelligenceMetrics;
  weekly_trend: ReviewTrendWeek[];
  themes: ReviewTheme[];
  actions: ReviewAction[];
};

type PortfolioReviewLocation = LocationReviewIntelligence & {
  attention_score: number;
  outliers: Array<{ code: string; label: string }>;
};

type PortfolioReviewIntelligence = {
  summary: {
    locations: number;
    locations_with_reviews: number;
    locations_needing_attention: number;
    total_reviews: number;
    reviews_last_30_days: number;
    unanswered_reviews: number;
    average_rating?: number | null;
    response_rate_percent?: number | null;
  };
  locations: PortfolioReviewLocation[];
};

type ReviewRequestChannel = "link" | "qr" | "kiosk" | "email" | "sms";

type ReviewRequestReadiness = {
  channels: Record<
    ReviewRequestChannel,
    { available: boolean; label: string; reason: string }
  >;
  review_gating_allowed: false;
  automatic_satisfaction_filtering_allowed: false;
};

type ReviewRequestCampaign = {
  id: string;
  name: string;
  channel: ReviewRequestChannel;
  status: "draft" | "active" | "paused" | "completed" | "cancelled";
  subject?: string | null;
  message_body: string;
  review_url: string;
  share_url: string;
  recipient_summary: {
    total: number;
    eligible: number;
    suppressed: number;
    sent: number;
  };
  result_summary: {
    baseline_review_count: number;
    current_review_count: number;
    new_reviews_since_start: number;
    attribution_state: "time_window_only";
    note: string;
  };
  created_at: string;
};

type ReviewFilter = "all" | "unanswered" | "low" | "responded";
type ReviewView = "location" | "portfolio";

const EMPTY_SUMMARY: ReviewSummary = {
  total: 0,
  unanswered: 0,
  responded: 0,
  rating_three_or_lower: 0,
  average_rating: null,
};

function reviewDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function weekLabel(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function metricValue(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "—";
  return `${value}${suffix}`;
}

function Stars({ rating }: { rating: number }) {
  const filled = Math.max(1, Math.min(5, Math.round(rating)));
  return (
    <span aria-label={`${rating} out of 5 stars`} className="tracking-[0.12em]">
      <span className="text-amber-400">{"★".repeat(filled)}</span>
      <span className="text-zinc-700">{"★".repeat(5 - filled)}</span>
    </span>
  );
}

function LocationReviewInsights({
  intelligence,
  reviews,
}: {
  intelligence: LocationReviewIntelligence | null;
  reviews: ReviewItem[];
}) {
  if (!intelligence) return null;
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-3">
        <KpiCard
          icon="reviews"
          label="Reviews in 30 days"
          value={String(intelligence.metrics.reviews_last_30_days)}
          changeLabel={`${intelligence.metrics.review_pace_change >= 0 ? "+" : ""}${intelligence.metrics.review_pace_change} vs. prior 30 days`}
          changeTone={
            intelligence.metrics.review_pace_change === 0
              ? "neutral"
              : intelligence.metrics.review_pace_change > 0
                ? "positive"
                : "negative"
          }
          summary="New customer reviews received during the latest 30 days."
        />
        <KpiCard
          icon="check"
          label="Reviews answered"
          value={metricValue(intelligence.metrics.response_rate_percent, "%")}
          summary="Share of saved reviews with a confirmed business response."
        />
        <KpiCard
          icon="calendar"
          label="Typical reply time"
          value={metricValue(intelligence.metrics.median_response_hours, " hours")}
          summary="Middle response time across replies with confirmed dates."
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <div className="rounded-md border border-[#26272c] bg-[#141518] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Last 12 weeks</p>
          <h2 className="mt-1.5 text-xl font-semibold text-white">How customer feedback is changing</h2>
          <p className="mt-1 text-sm text-zinc-400">
            Each bar is one week. Green is 4–5 stars, gray is 3 stars, and red is 1–2 stars.
          </p>
          <div className="mt-5 h-64" aria-label="Customer review trend chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={intelligence.weekly_trend} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                <XAxis
                  dataKey="week_start"
                  axisLine={false}
                  tickLine={false}
                  minTickGap={22}
                  tick={{ fill: "#71717a", fontSize: 11 }}
                  tickFormatter={weekLabel}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                  tick={{ fill: "#71717a", fontSize: 11 }}
                />
                <Tooltip
                  labelFormatter={(value) => `Week of ${weekLabel(String(value))}`}
                  contentStyle={{ background: "#101113", border: "1px solid #303138", borderRadius: 6 }}
                />
                <Bar dataKey="positive" name="4–5 star reviews" stackId="reviews" fill="#34d399" />
                <Bar dataKey="mixed" name="3 star reviews" stackId="reviews" fill="#a1a1aa" />
                <Bar
                  dataKey="negative"
                  name="1–2 star reviews"
                  stackId="reviews"
                  fill="#fb7185"
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-md border border-[#26272c] bg-[#141518] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">What to do next</p>
          <h2 className="mt-1.5 text-xl font-semibold text-white">Actions tied to your reviews</h2>
          <div className="mt-4 space-y-3">
            {intelligence.actions.map((action, index) => (
              <article key={action.id} className="border-l-2 border-[#ff6b18] bg-[#101113] px-4 py-3">
                <div className="flex items-start gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#ff6b18] text-xs font-bold text-white">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="font-semibold text-white">{action.title}</h3>
                    <p className="mt-1 text-sm leading-6 text-zinc-300">{action.why}</p>
                    <p className="mt-2 text-xs font-semibold text-zinc-400">
                      {action.metric_label}: {action.current_value} now → goal {action.target_value}
                    </p>
                    {action.evidence_review_ids.length > 0 ? (
                      <details className="mt-2 text-xs text-zinc-500">
                        <summary className="cursor-pointer text-[#ff9b67]">See the customer feedback behind this</summary>
                        <ul className="mt-2 space-y-1.5">
                          {action.evidence_review_ids.map((reviewId) => {
                            const review = reviews.find((item) => item.id === reviewId);
                            return (
                              <li key={reviewId}>
                                {review
                                  ? `${review.rating} stars — ${review.body || "No written comment"}`
                                  : "Saved customer review"}
                              </li>
                            );
                          })}
                        </ul>
                      </details>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-md border border-[#26272c] bg-[#141518] p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">What customers mention</p>
        <h2 className="mt-1.5 text-xl font-semibold text-white">Common feedback from the last 180 days</h2>
        {intelligence.themes.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {intelligence.themes.map((theme) => (
              <article key={theme.key} className="rounded-md border border-[#2d2e34] bg-[#101113] p-4">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-semibold text-white">{theme.label}</h3>
                  <span
                    className={`text-xs font-semibold ${
                      theme.tone === "strength"
                        ? "text-emerald-300"
                        : theme.tone === "needs_attention"
                          ? "text-rose-300"
                          : "text-zinc-400"
                    }`}
                  >
                    {theme.mentions} mention{theme.mentions === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="mt-3 flex gap-4 text-xs text-zinc-400">
                  <span className="text-emerald-300">{theme.positive_mentions} positive</span>
                  <span className="text-rose-300">{theme.negative_mentions} negative</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-zinc-400">
            There is not enough written customer feedback to show recurring subjects yet.
          </p>
        )}
      </section>
    </>
  );
}

function PortfolioReviewOverview({
  portfolio,
  onOpenLocation,
}: {
  portfolio: PortfolioReviewIntelligence;
  onOpenLocation: (campaignId: string) => void;
}) {
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          icon="locations"
          label="Locations"
          value={String(portfolio.summary.locations)}
          summary="Active locations included in this comparison."
        />
        <KpiCard
          icon="reviews"
          label="Reviews in 30 days"
          value={String(portfolio.summary.reviews_last_30_days)}
          summary="New reviews received across every location."
        />
        <KpiCard
          icon="spark"
          label="Average rating"
          value={metricValue(portfolio.summary.average_rating)}
          summary="Combined rating, weighted by each saved customer review."
        />
        <KpiCard
          icon="warning"
          label="Need attention"
          value={String(portfolio.summary.locations_needing_attention)}
          summary="Locations that differ meaningfully from the rest of the business."
          tone={portfolio.summary.locations_needing_attention > 0 ? "highlight" : "default"}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_1.25fr]">
        <div className="rounded-md border border-[#26272c] bg-[#141518] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Location comparison</p>
          <h2 className="mt-1.5 text-xl font-semibold text-white">Reviews received in the last 30 days</h2>
          <div className="mt-5 h-72" aria-label="Reviews by location chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={portfolio.locations} layout="vertical" margin={{ top: 0, right: 12, left: 16, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,0.12)" horizontal={false} />
                <XAxis
                  type="number"
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                  tick={{ fill: "#71717a", fontSize: 11 }}
                />
                <YAxis
                  type="category"
                  dataKey="location_name"
                  axisLine={false}
                  tickLine={false}
                  width={92}
                  tick={{ fill: "#d4d4d8", fontSize: 11 }}
                />
                <Tooltip contentStyle={{ background: "#101113", border: "1px solid #303138", borderRadius: 6 }} />
                <Bar dataKey="metrics.reviews_last_30_days" name="Reviews in 30 days" radius={[0, 4, 4, 0]}>
                  {portfolio.locations.map((location) => (
                    <Cell
                      key={location.campaign_id}
                      fill={location.attention_score > 0 ? "#f59e0b" : "#ff6b18"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-md border border-[#26272c] bg-[#141518] p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Where to focus</p>
          <h2 className="mt-1.5 text-xl font-semibold text-white">Locations ordered by attention needed</h2>
          <div className="mt-4 divide-y divide-[#292a2f]">
            {portfolio.locations.map((location) => (
              <article key={location.campaign_id} className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div>
                  <h3 className="font-semibold text-white">{location.location_name}</h3>
                  <p className="mt-1 text-sm text-zinc-400">
                    {metricValue(location.metrics.average_rating)} stars · {location.metrics.reviews_last_30_days} recent
                    reviews · {location.metrics.unanswered_reviews} waiting for a reply
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {location.outliers.length ? (
                      location.outliers.map((outlier) => (
                        <span
                          key={outlier.code}
                          className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-100"
                        >
                          {outlier.label}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-emerald-300">No meaningful difference needs attention.</span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onOpenLocation(location.campaign_id)}
                  className="rounded-md border border-[#3a3b42] px-3.5 py-2 text-sm font-semibold text-white hover:border-[#ff6b18]/60"
                >
                  Open this location
                </button>
              </article>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function ReviewGrowthTools({
  readiness,
  campaigns,
  working,
  onCreate,
}: {
  readiness: ReviewRequestReadiness | null;
  campaigns: ReviewRequestCampaign[];
  working: boolean;
  onCreate: (input: { channel: "link" | "qr" | "kiosk"; messageBody: string; reviewUrl: string }) => Promise<void>;
}) {
  const [channel, setChannel] = useState<"link" | "qr" | "kiosk">("link");
  const [messageBody, setMessageBody] = useState(
    "Thank you for choosing us. Would you share an honest review? Your feedback helps us improve.",
  );
  const [reviewUrl, setReviewUrl] = useState("");
  const [qrImages, setQrImages] = useState<Record<string, string>>({});
  const [qrWorkingId, setQrWorkingId] = useState("");
  const [qrErrorId, setQrErrorId] = useState("");

  async function prepareQrImage(campaign: ReviewRequestCampaign) {
    setQrWorkingId(campaign.id);
    setQrErrorId("");
    try {
      const image = await QRCode.toDataURL(campaign.share_url, {
        type: "image/png",
        errorCorrectionLevel: "H",
        width: 720,
        margin: 4,
        color: { dark: "#111827", light: "#ffffff" },
      });
      setQrImages((current) => ({ ...current, [campaign.id]: image }));
    } catch {
      setQrErrorId(campaign.id);
    } finally {
      setQrWorkingId("");
    }
  }

  function downloadQrImage(campaign: ReviewRequestCampaign) {
    const image = qrImages[campaign.id];
    if (!image) return;
    const safeName = campaign.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    const link = document.createElement("a");
    link.href = image;
    link.download = `${safeName || "customer-review"}-qr-code.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return (
    <section className="rounded-md border border-[#26272c] bg-[#141518] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Get more honest reviews</p>
          <h2 className="mt-1.5 text-xl font-semibold text-white">Ask every eligible customer the same way</h2>
          <p className="mt-1 text-sm leading-6 text-zinc-400">
            Create one trusted review link for this location. The tool never asks whether a customer is happy and never
            hides the link from unhappy customers.
          </p>
        </div>
        <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
          No review gating
        </span>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {(Object.entries(readiness?.channels || {}) as Array<
          [ReviewRequestChannel, { available: boolean; label: string; reason: string }]
        >).map(([key, item]) => (
          <article key={key} className="rounded-md border border-[#2d2e34] bg-[#101113] p-3.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-white">{item.label}</p>
              <span className={`h-2 w-2 rounded-full ${item.available ? "bg-emerald-400" : "bg-amber-400"}`} />
            </div>
            <p className="mt-2 text-xs leading-5 text-zinc-400">{item.reason}</p>
          </article>
        ))}
      </div>

      <div className="mt-5 grid gap-5 border-t border-[#292a2f] pt-5 xl:grid-cols-[0.9fr_1.1fr]">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onCreate({ channel, messageBody, reviewUrl });
          }}
          className="space-y-4"
        >
          <div>
            <label htmlFor="review-request-type" className="text-sm font-semibold text-white">
              How will you share it?
            </label>
            <select
              id="review-request-type"
              value={channel}
              onChange={(event) => setChannel(event.target.value as "link" | "qr" | "kiosk")}
              className="mt-2 w-full rounded-md border border-[#34353c] bg-[#0e0f11] px-3 py-2.5 text-sm text-white outline-none focus:border-[#ff6b18]/60"
            >
              <option value="link">Copyable link</option>
              <option value="qr">Downloadable QR code</option>
              <option value="kiosk">Checkout or kiosk link</option>
            </select>
          </div>
          <div>
            <label htmlFor="review-request-message" className="text-sm font-semibold text-white">
              Message customers will see
            </label>
            <textarea
              id="review-request-message"
              value={messageBody}
              maxLength={700}
              onChange={(event) => setMessageBody(event.target.value)}
              className="mt-2 min-h-28 w-full rounded-md border border-[#34353c] bg-[#0e0f11] p-3 text-sm leading-6 text-white outline-none focus:border-[#ff6b18]/60"
            />
          </div>
          <div>
            <label htmlFor="review-request-url" className="text-sm font-semibold text-white">
              Google review link <span className="font-normal text-zinc-500">(only if it was not found automatically)</span>
            </label>
            <input
              id="review-request-url"
              type="url"
              placeholder="https://g.page/.../review"
              value={reviewUrl}
              onChange={(event) => setReviewUrl(event.target.value)}
              className="mt-2 w-full rounded-md border border-[#34353c] bg-[#0e0f11] px-3 py-2.5 text-sm text-white outline-none focus:border-[#ff6b18]/60"
            />
          </div>
          <button
            type="submit"
            disabled={working || !messageBody.trim()}
            className="rounded-md bg-[#ff6b18] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {working ? "Saving..." : "Create review link"}
          </button>
        </form>

        <div>
          <p className="text-sm font-semibold text-white">Saved review links</p>
          {campaigns.length ? (
            <div className="mt-2 divide-y divide-[#292a2f] border-y border-[#292a2f]">
              {campaigns.map((campaign) => (
                <article key={campaign.id} className="py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-white">{campaign.name}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {campaign.channel === "link"
                          ? "Copyable link"
                          : campaign.channel === "qr"
                            ? "QR-ready link"
                            : campaign.channel === "kiosk"
                              ? "Checkout link"
                              : campaign.channel}
                        {" · "}
                        {campaign.status}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void navigator.clipboard?.writeText(campaign.share_url)}
                      className="rounded-md border border-[#3a3b42] px-3 py-2 text-xs font-semibold text-white hover:border-[#ff6b18]/60"
                    >
                      Copy review link
                    </button>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-zinc-300">{campaign.message_body}</p>
                  {campaign.channel === "qr" ? (
                    <div className="mt-4 rounded-md border border-[#303138] bg-white p-4 text-zinc-900">
                      <div className="flex flex-wrap items-center gap-4">
                        {qrImages[campaign.id] ? (
                          <img
                            src={qrImages[campaign.id]}
                            alt={`QR code for ${campaign.name}`}
                            width={168}
                            height={168}
                            className="h-[168px] w-[168px] rounded-sm border border-zinc-200"
                          />
                        ) : (
                          <div className="flex h-[168px] w-[168px] items-center justify-center rounded-sm border border-dashed border-zinc-300 bg-zinc-50 px-5 text-center text-xs leading-5 text-zinc-500">
                            Generate the QR image when you are ready to download it.
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">Customer review QR code</p>
                          <p className="mt-1 text-xs leading-5 text-zinc-600">
                            This code opens this location&apos;s saved Google review link. Test the downloaded image with
                            your phone before printing it.
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              type="button"
                              disabled={qrWorkingId === campaign.id}
                              onClick={() => void prepareQrImage(campaign)}
                              className="rounded-md bg-[#111827] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                            >
                              {qrWorkingId === campaign.id
                                ? "Generating..."
                                : qrImages[campaign.id]
                                  ? "Regenerate QR code"
                                  : "Generate QR code"}
                            </button>
                            {qrImages[campaign.id] ? (
                              <button
                                type="button"
                                onClick={() => downloadQrImage(campaign)}
                                className="rounded-md border border-zinc-300 px-3 py-2 text-xs font-semibold text-zinc-900"
                              >
                                Download PNG
                              </button>
                            ) : null}
                          </div>
                          {qrErrorId === campaign.id ? (
                            <p className="mt-2 text-xs font-semibold text-rose-700">
                              The QR image could not be generated. The saved review link is still available.
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div className="mt-3 border-l-2 border-[#34353b] pl-3 text-xs leading-5 text-zinc-400">
                    <span className="font-semibold text-white">{campaign.result_summary.new_reviews_since_start}</span> new
                    reviews since this link was created. {campaign.result_summary.note}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="mt-2 rounded-md border border-dashed border-[#34353c] p-5 text-sm text-zinc-400">
              Create the first link for this location. Existing reviews are saved as the starting point so later changes
              can be shown honestly.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export default function ReviewsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedCampaignId, setSelectedCampaignId } = useLocationContext();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [inventory, setInventory] = useState<ReviewInventory>({
    items: [],
    summary: EMPTY_SUMMARY,
  });
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [view, setView] = useState<ReviewView>("location");
  const [intelligence, setIntelligence] = useState<LocationReviewIntelligence | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioReviewIntelligence | null>(null);
  const [draftsByReview, setDraftsByReview] = useState<Record<string, ReviewResponseDraft>>({});
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});
  const [responsePolicy, setResponsePolicy] = useState<ReviewResponsePolicy | null>(null);
  const [postingStatus, setPostingStatus] = useState<ReviewPostingStatus | null>(null);
  const [executionsByReview, setExecutionsByReview] = useState<Record<string, ReviewResponseExecution>>({});
  const [requestReadiness, setRequestReadiness] = useState<ReviewRequestReadiness | null>(null);
  const [requestCampaigns, setRequestCampaigns] = useState<ReviewRequestCampaign[]>([]);
  const [requestWorking, setRequestWorking] = useState(false);
  const [publishConfirmations, setPublishConfirmations] = useState<Record<string, boolean>>({});
  const [workingReviewId, setWorkingReviewId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadInventory = useCallback(async (campaignId: string) => {
    const [
      response,
      draftResponse,
      policyResponse,
      postingResponse,
      executionResponse,
      intelligenceResponse,
      portfolioResponse,
      requestReadinessResponse,
      requestCampaignResponse,
    ] = await Promise.all([
      platformApi(
        `/reviews/inventory?campaign_id=${encodeURIComponent(campaignId)}&source_type=owned_profile&limit=250`,
        { method: "GET" },
      ) as Promise<ReviewInventory>,
      platformApi(`/reviews/drafts?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<{ items: ReviewResponseDraft[] }>,
      platformApi(`/reviews/response-policy?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<ReviewResponsePolicy>,
      platformApi(`/reviews/posting-status?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<ReviewPostingStatus>,
      platformApi(`/reviews/executions?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<{ items: ReviewResponseExecution[] }>,
      platformApi(`/reviews/intelligence?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }) as Promise<LocationReviewIntelligence>,
      platformApi("/reviews/portfolio", { method: "GET" }) as Promise<PortfolioReviewIntelligence>,
      platformApi("/reviews/request-readiness", { method: "GET" }) as Promise<ReviewRequestReadiness>,
      platformApi(`/reviews/request-campaigns?campaign_id=${encodeURIComponent(campaignId)}`, {
        method: "GET",
      }).catch(() => ({ items: [] })) as Promise<{ items: ReviewRequestCampaign[] }>,
    ]);
    setInventory({
      items: Array.isArray(response?.items) ? response.items : [],
      summary: response?.summary || EMPTY_SUMMARY,
    });
    const nextDrafts: Record<string, ReviewResponseDraft> = {};
    const nextEdits: Record<string, string> = {};
    for (const draft of draftResponse?.items || []) {
      nextDrafts[draft.review_id] = draft;
      nextEdits[draft.id] = draft.approved_text || draft.draft_text || "";
    }
    setDraftsByReview(nextDrafts);
    setDraftEdits(nextEdits);
    setResponsePolicy(policyResponse || null);
    setPostingStatus(postingResponse || null);
    const nextExecutions: Record<string, ReviewResponseExecution> = {};
    for (const execution of executionResponse?.items || []) {
      if (!nextExecutions[execution.review_id]) nextExecutions[execution.review_id] = execution;
    }
    setExecutionsByReview(nextExecutions);
    setIntelligence(intelligenceResponse || null);
    setPortfolio(portfolioResponse || null);
    setRequestReadiness(requestReadinessResponse || null);
    setRequestCampaigns(Array.isArray(requestCampaignResponse?.items) ? requestCampaignResponse.items : []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        await platformApi("/auth/me", { method: "GET" });
        const response = await platformApi("/campaigns", { method: "GET" });
        const items = Array.isArray(response?.items) ? (response.items as Campaign[]) : [];
        if (cancelled) return;
        setCampaigns(items);
        setSelectedCampaignId((current) => {
          if (current && items.some((item) => item.id === current)) return current;
          return items[0]?.id || "";
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Reviews could not be loaded.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadPage();
    return () => {
      cancelled = true;
    };
  }, [setSelectedCampaignId]);

  useEffect(() => {
    if (!selectedCampaignId || loading) return;
    setFilter("all");
    setNotice("");
    void loadInventory(selectedCampaignId).catch((err) => {
      setError(err instanceof Error ? err.message : "Reviews could not be loaded.");
    });
  }, [loadInventory, loading, selectedCampaignId]);

  useEffect(() => {
    if (!selectedCampaignId) return;
    const hasPendingWork = Object.values(executionsByReview).some((item) =>
      ["queued", "posting", "retrying"].includes(item.status),
    );
    if (!hasPendingWork) return;
    const timer = window.setInterval(() => {
      void loadInventory(selectedCampaignId).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [executionsByReview, loadInventory, selectedCampaignId]);

  async function checkForReviews() {
    if (!selectedCampaignId) return;
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      const response = await platformApi(
        `/reviews/sync?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST" },
      );
      setInventory({
        items: Array.isArray(response?.items) ? (response.items as ReviewItem[]) : [],
        summary: (response?.summary as ReviewSummary) || EMPTY_SUMMARY,
      });
      await loadInventory(selectedCampaignId);
      setNotice(response?.job?.message || "The latest saved reviews are shown below.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reviews could not be updated.");
    } finally {
      setRefreshing(false);
    }
  }

  async function createReviewRequestCampaign(input: {
    channel: "link" | "qr" | "kiosk";
    messageBody: string;
    reviewUrl: string;
  }) {
    if (!selectedCampaignId) return;
    setRequestWorking(true);
    setError("");
    setNotice("");
    try {
      await platformApi("/reviews/request-campaigns", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          name: "Customer review link",
          channel: input.channel,
          message_body: input.messageBody,
          review_url: input.reviewUrl.trim() || null,
        }),
      });
      await loadInventory(selectedCampaignId);
      setNotice(
        input.channel === "qr"
          ? "The review link is saved and ready to place in a QR code."
          : input.channel === "kiosk"
            ? "The checkout review link is saved. Show the same link to every eligible customer."
            : "The review link is saved and ready to share with eligible customers.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The review link could not be saved.");
    } finally {
      setRequestWorking(false);
    }
  }

  async function draftReply(reviewId: string, refresh = false) {
    if (!selectedCampaignId) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      const draft = (await platformApi(
        `/reviews/${encodeURIComponent(reviewId)}/drafts?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        { method: "POST", body: JSON.stringify({ refresh }) },
      )) as ReviewResponseDraft;
      setDraftsByReview((current) => ({ ...current, [reviewId]: draft }));
      setDraftEdits((current) => ({
        ...current,
        [draft.id]: draft.approved_text || draft.draft_text || "",
      }));
      if (draft.status === "human_required") {
        setNotice("This review needs a personal reply. No response credit was used.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "A reply draft could not be prepared.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function decideDraft(reviewId: string, draft: ReviewResponseDraft, decision: "approve" | "reject") {
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      const updated = (await platformApi(`/reviews/drafts/${encodeURIComponent(draft.id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          decision,
          approved_text: decision === "approve" ? draftEdits[draft.id] || draft.draft_text || "" : null,
        }),
      })) as ReviewResponseDraft;
      setDraftsByReview((current) => ({ ...current, [reviewId]: updated }));
      setDraftEdits((current) => ({
        ...current,
        [updated.id]: updated.approved_text || updated.draft_text || "",
      }));
      setNotice(
        decision === "approve"
          ? "Approved wording was saved. InsightOS did not post it."
          : "The draft was discarded.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The draft decision could not be saved.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function copyApprovedReply(draft: ReviewResponseDraft) {
    const text = draft.approved_text || "";
    if (!text || !navigator.clipboard) return;
    await navigator.clipboard.writeText(text);
    setNotice("Approved reply copied. You can paste it into your business profile.");
  }

  async function publishApprovedReply(reviewId: string, draft: ReviewResponseDraft) {
    if (!selectedCampaignId || !postingStatus || !publishConfirmations[draft.id]) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      await platformApi(
        `/reviews/drafts/${encodeURIComponent(draft.id)}/publish?campaign_id=${encodeURIComponent(selectedCampaignId)}`,
        {
          method: "POST",
          body: JSON.stringify({
            confirmation_version: postingStatus.confirmation_version,
            confirm_publish_to_google: true,
          }),
        },
      );
      await loadInventory(selectedCampaignId);
      setNotice("Your approved reply is queued for Google. We will show the confirmed result here.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The approved reply could not be queued.");
    } finally {
      setWorkingReviewId("");
    }
  }

  async function controlPublish(
    reviewId: string,
    execution: ReviewResponseExecution,
    action: "pause" | "resume" | "cancel" | "retry",
  ) {
    if (!selectedCampaignId) return;
    setWorkingReviewId(reviewId);
    setError("");
    setNotice("");
    try {
      await platformApi(`/reviews/executions/${encodeURIComponent(execution.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ action }),
      });
      await loadInventory(selectedCampaignId);
      setNotice(
        action === "pause"
          ? "Posting is paused."
          : action === "resume"
            ? "Posting is queued again."
            : action === "cancel"
              ? "Posting was cancelled before Google received it."
              : "Posting is queued to try again.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The posting action could not be completed.");
    } finally {
      setWorkingReviewId("");
    }
  }

  const filteredReviews = useMemo(() => {
    if (filter === "unanswered") {
      return inventory.items.filter((item) => item.response_status === "unanswered");
    }
    if (filter === "responded") {
      return inventory.items.filter((item) => item.response_status === "responded");
    }
    if (filter === "low") {
      return inventory.items.filter((item) => item.rating <= 3);
    }
    return inventory.items;
  }, [filter, inventory.items]);

  const selectedCampaign = campaigns.find((item) => item.id === selectedCampaignId) ?? null;
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Needs a reply",
        value: String(inventory.summary.unanswered),
        tone: inventory.summary.unanswered > 0 ? "warning" : "success",
      },
      {
        label: "3 stars or lower",
        value: String(inventory.summary.rating_three_or_lower),
        tone: inventory.summary.rating_three_or_lower > 0 ? "danger" : "success",
      },
    ],
    [inventory.summary.rating_three_or_lower, inventory.summary.unanswered],
  );

  const filters: Array<{ id: ReviewFilter; label: string; count: number }> = [
    { id: "all", label: "All reviews", count: inventory.summary.total },
    { id: "unanswered", label: "Needs a reply", count: inventory.summary.unanswered },
    { id: "low", label: "3 stars or lower", count: inventory.summary.rating_three_or_lower },
    { id: "responded", label: "Answered", count: inventory.summary.responded },
  ];

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel={
        selectedCampaign
          ? `${selectedCampaign.name || "Unnamed business"} / ${selectedCampaign.domain || "No website"}`
          : "No business selected"
      }
      dateRangeLabel="Latest saved customer reviews"
      topBarActions={
        view === "location" ? (
          <button
            type="button"
            onClick={() => void checkForReviews()}
            disabled={!selectedCampaignId || refreshing}
            className="rounded-md bg-[#ff6b18] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? "Checking..." : "Check for new reviews"}
          </button>
        ) : null
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          eyebrow="Customer reviews"
          title="See what customers said and what needs a reply"
          summary="Keep each location's reviews in one place. Start with unhappy customers and reviews that have not received an answer."
          compact
        />

        <TruthNotice title="Prepare a reply, then review every word before posting.">
          Every suggested reply must be checked and approved by a person. Posting is a separate step
          with its own confirmation. Automatic replies are off.
        </TruthNotice>

        {responsePolicy && !responsePolicy.ai_configured ? (
          <section className="rounded-md border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            Reply drafting is not connected yet. Your reviews remain available and no credits will be used.
          </section>
        ) : null}

        {loading ? <LoadingCard title="Loading customer reviews" summary="Checking the selected location." /> : null}
        {error ? (
          <section className="rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-100">
            {error}
          </section>
        ) : null}
        {notice ? (
          <section className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            {notice}
          </section>
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#292a2f] pb-4">
            <div>
              <p className="text-sm font-semibold text-white">Choose what you want to see</p>
              <p className="mt-1 text-xs text-zinc-500">
                Check one location’s customer feedback or compare every location in the business.
              </p>
            </div>
            <div className="inline-flex rounded-md border border-[#303138] bg-[#101113] p-1" aria-label="Review view">
              <button
                type="button"
                aria-pressed={view === "location"}
                onClick={() => setView("location")}
                className={`rounded px-3 py-1.5 text-sm font-semibold ${
                  view === "location" ? "bg-[#ff6b18] text-white" : "text-zinc-400 hover:text-white"
                }`}
              >
                This location
              </button>
              <button
                type="button"
                aria-pressed={view === "portfolio"}
                onClick={() => setView("portfolio")}
                className={`rounded px-3 py-1.5 text-sm font-semibold ${
                  view === "portfolio" ? "bg-[#ff6b18] text-white" : "text-zinc-400 hover:text-white"
                }`}
              >
                All locations
              </button>
            </div>
          </div>
        ) : null}

        {!loading && campaigns.length === 0 ? (
          <EmptyState
            icon="reviews"
            title="No business is ready yet"
            summary="Set up a business location before collecting its customer reviews."
            actionLabel="Set up a location"
            onAction={() => router.push("/locations")}
          />
        ) : null}

        {!loading && campaigns.length > 0 ? (
          <>
            {view === "location" ? (
              <>
                <LocationReviewInsights intelligence={intelligence} reviews={inventory.items} />
                <ReviewGrowthTools
                  readiness={requestReadiness}
                  campaigns={requestCampaigns}
                  working={requestWorking}
                  onCreate={createReviewRequestCampaign}
                />
              </>
            ) : portfolio ? (
              <PortfolioReviewOverview
                portfolio={portfolio}
                onOpenLocation={(campaignId) => {
                  setSelectedCampaignId(campaignId);
                  setView("location");
                }}
              />
            ) : null}

            <section
              className={`${view === "location" ? "block" : "hidden"} rounded-md border border-[#26272c] bg-[#141518] p-5`}
            >
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Review inbox
                  </p>
                  <h2 className="mt-1.5 text-2xl font-semibold tracking-[-0.03em] text-white">
                    {filteredReviews.length} {filteredReviews.length === 1 ? "review" : "reviews"}
                  </h2>
                </div>
                <div className="flex flex-wrap gap-2" aria-label="Review filters">
                  {filters.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={filter === item.id}
                      onClick={() => setFilter(item.id)}
                      className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                        filter === item.id
                          ? "border-accent-500/40 bg-accent-500/15 text-white"
                          : "border-[#303138] bg-[#101113] text-zinc-400 hover:text-white"
                      }`}
                    >
                      {item.label} <span className="ml-1 text-current/70">{item.count}</span>
                    </button>
                  ))}
                </div>
              </div>

              {filteredReviews.length > 0 ? (
                <div className="mt-5 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                  {filteredReviews.map((review) => (
                    <article key={review.id} className="py-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">
                            {review.author_is_anonymous ? "Anonymous customer" : review.author_name || "Customer"}
                          </p>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                            <Stars rating={review.rating} />
                            <span className="text-zinc-500">{reviewDate(review.reviewed_at)}</span>
                          </div>
                        </div>
                        <span
                          className={`rounded-md border px-2 py-1 text-xs font-semibold ${
                            review.response_status === "responded"
                              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
                              : "border-amber-500/20 bg-amber-500/10 text-amber-100"
                          }`}
                        >
                          {review.response_status === "responded" ? "Answered" : "Needs a reply"}
                        </span>
                      </div>
                      <p className="mt-3 max-w-4xl text-sm leading-6 text-zinc-200">
                        {review.body || "This customer left a star rating without a written comment."}
                      </p>
                      {review.response_text ? (
                        <div className="mt-4 border-l-2 border-emerald-500/40 bg-emerald-500/[0.04] px-4 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-200/70">
                            Your saved response
                          </p>
                          <p className="mt-1.5 text-sm leading-6 text-zinc-300">{review.response_text}</p>
                        </div>
                      ) : null}
                      {review.response_status === "unanswered"
                        ? (() => {
                            const draft = draftsByReview[review.id];
                            const execution = executionsByReview[review.id];
                            const isWorking = workingReviewId === review.id;
                            if (!draft) {
                              const creditLabel = responsePolicy?.maximum_credits_per_draft
                                ? `Up to ${responsePolicy.maximum_credits_per_draft} Insight Credit${
                                    responsePolicy.maximum_credits_per_draft === 1 ? "" : "s"
                                  }`
                                : "Usage is measured before work starts";
                              return (
                                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[#292a2f] pt-4">
                                  <button
                                    type="button"
                                    onClick={() => void draftReply(review.id)}
                                    disabled={isWorking || responsePolicy?.ai_configured === false}
                                    className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {isWorking ? "Preparing wording..." : "Draft a reply"}
                                  </button>
                                  <span className="text-xs text-zinc-500">{creditLabel}. Nothing is posted.</span>
                                </div>
                              );
                            }
                            if (draft.status === "human_required") {
                              return (
                                <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/[0.07] p-4">
                                  <p className="font-semibold text-amber-100">A person should handle this reply</p>
                                  <p className="mt-1 text-sm leading-6 text-zinc-300">{draft.human_reason}</p>
                                  {draft.sensitive_topics.length > 0 ? (
                                    <p className="mt-2 text-xs text-zinc-500">
                                      Safety check: {draft.sensitive_topics.join(", ")}
                                    </p>
                                  ) : null}
                                  {review.review_url ? (
                                    <a
                                      href={review.review_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="mt-3 inline-flex text-sm font-semibold text-[#ff8a4c] hover:text-[#ffa06f]"
                                    >
                                      Open the original review →
                                    </a>
                                  ) : null}
                                </div>
                              );
                            }
                            if (draft.status === "ready_for_review") {
                              return (
                                <div className="mt-4 rounded-md border border-violet-500/20 bg-violet-500/[0.06] p-4">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div>
                                      <p className="font-semibold text-white">Check this suggested reply</p>
                                      <p className="mt-1 text-sm text-zinc-400">
                                        Edit anything that does not sound like your business, then approve or discard it.
                                      </p>
                                    </div>
                                    <span className="rounded-full border border-violet-400/20 px-2.5 py-1 text-[11px] font-semibold text-violet-100">
                                      Not posted
                                    </span>
                                  </div>
                                  <textarea
                                    aria-label={`Reply draft for ${review.author_name || "customer"}`}
                                    value={draftEdits[draft.id] ?? draft.draft_text ?? ""}
                                    maxLength={600}
                                    onChange={(event) =>
                                      setDraftEdits((current) => ({ ...current, [draft.id]: event.target.value }))
                                    }
                                    className="mt-3 min-h-28 w-full resize-y rounded-md border border-[#34353c] bg-[#0e0f11] p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-violet-400/50"
                                  />
                                  <div className="mt-3 flex flex-wrap items-center gap-2">
                                    <button
                                      type="button"
                                      disabled={isWorking || !(draftEdits[draft.id] ?? draft.draft_text ?? "").trim()}
                                      onClick={() => void decideDraft(review.id, draft, "approve")}
                                      className="rounded-md bg-emerald-600 px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      {isWorking ? "Saving..." : "Approve this wording"}
                                    </button>
                                    <button
                                      type="button"
                                      disabled={isWorking}
                                      onClick={() => void decideDraft(review.id, draft, "reject")}
                                      className="rounded-md border border-[#34353c] px-3.5 py-2 text-sm font-semibold text-zinc-200 disabled:opacity-50"
                                    >
                                      Discard draft
                                    </button>
                                    <span className="text-xs text-zinc-500">Approval saves it here only.</span>
                                  </div>
                                </div>
                              );
                            }
                            if (draft.status === "approved") {
                              return (
                                <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] p-4">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <p className="font-semibold text-emerald-100">Approved wording</p>
                                    <span className="rounded-full border border-emerald-500/20 px-2.5 py-1 text-[11px] font-semibold text-emerald-100">
                                      {execution?.status === "posted"
                                        ? "Posted to Google"
                                        : execution?.status === "posting"
                                          ? "Posting now"
                                          : execution?.status === "retrying"
                                            ? "Waiting to try again"
                                            : execution?.status === "queued"
                                              ? "Queued"
                                              : execution?.status === "paused"
                                                ? "Paused"
                                                : execution?.status === "blocked"
                                                  ? "Needs attention"
                                                  : execution?.status === "failed"
                                                    ? "Could not post"
                                                    : execution?.status === "cancelled"
                                                      ? "Cancelled"
                                                      : "Not posted"}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-zinc-200">{draft.approved_text}</p>
                                  {execution?.error_message ? (
                                    <p className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/[0.08] px-3 py-2 text-sm text-amber-100">
                                      {execution.error_message}
                                    </p>
                                  ) : null}
                                  {!execution && postingStatus?.available ? (
                                    <label className="mt-4 flex max-w-2xl cursor-pointer items-start gap-3 rounded-md border border-[#34353c] bg-[#101113] p-3 text-sm leading-6 text-zinc-200">
                                      <input
                                        type="checkbox"
                                        checked={Boolean(publishConfirmations[draft.id])}
                                        onChange={(event) =>
                                          setPublishConfirmations((current) => ({
                                            ...current,
                                            [draft.id]: event.target.checked,
                                          }))
                                        }
                                        className="mt-1 h-4 w-4 accent-[#ff6b18]"
                                      />
                                      <span>{postingStatus.confirmation_label}</span>
                                    </label>
                                  ) : null}
                                  {!execution && postingStatus && !postingStatus.available ? (
                                    <p className="mt-3 text-sm leading-6 text-zinc-400">{postingStatus.reason}</p>
                                  ) : null}
                                  <div className="mt-3 flex flex-wrap items-center gap-3">
                                    {!execution && postingStatus?.available ? (
                                      <button
                                        type="button"
                                        disabled={isWorking || !publishConfirmations[draft.id]}
                                        onClick={() => void publishApprovedReply(review.id, draft)}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                                      >
                                        {isWorking ? "Queuing..." : "Post approved reply to Google"}
                                      </button>
                                    ) : null}
                                    {execution && ["queued", "retrying"].includes(execution.status) ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "pause")}
                                        className="rounded-md border border-amber-500/25 px-3.5 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
                                      >
                                        Pause posting
                                      </button>
                                    ) : null}
                                    {execution?.status === "paused" ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "resume")}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:opacity-50"
                                      >
                                        Resume posting
                                      </button>
                                    ) : null}
                                    {execution && ["queued", "retrying", "paused"].includes(execution.status) ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "cancel")}
                                        className="rounded-md border border-[#34353c] px-3.5 py-2 text-sm font-semibold text-zinc-200 disabled:opacity-50"
                                      >
                                        Cancel
                                      </button>
                                    ) : null}
                                    {execution?.status === "failed" ? (
                                      <button
                                        type="button"
                                        disabled={isWorking}
                                        onClick={() => void controlPublish(review.id, execution, "retry")}
                                        className="rounded-md bg-[#ff6b18] px-3.5 py-2 text-sm font-semibold text-white disabled:opacity-50"
                                      >
                                        Try posting again
                                      </button>
                                    ) : null}
                                    <button
                                      type="button"
                                      onClick={() => void copyApprovedReply(draft)}
                                      className="rounded-md border border-emerald-500/25 px-3.5 py-2 text-sm font-semibold text-emerald-100"
                                    >
                                      Copy approved reply
                                    </button>
                                    <span className="text-xs text-zinc-500">
                                      {execution
                                        ? "Posting history stays attached to this approved reply."
                                        : "Copying does not post or change anything."}
                                    </span>
                                  </div>
                                </div>
                              );
                            }
                            return (
                              <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/[0.06] p-4">
                                <p className="font-semibold text-amber-100">
                                  {draft.status === "rejected" ? "Draft discarded" : "Wording is not available yet"}
                                </p>
                                <p className="mt-1 text-sm leading-6 text-zinc-300">
                                  {draft.human_reason || "You can ask for a fresh draft when you are ready."}
                                </p>
                                <button
                                  type="button"
                                  disabled={isWorking || responsePolicy?.ai_configured === false}
                                  onClick={() => void draftReply(review.id, true)}
                                  className="mt-3 rounded-md border border-amber-500/25 px-3.5 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50"
                                >
                                  {isWorking ? "Preparing wording..." : "Try a fresh draft"}
                                </button>
                              </div>
                            );
                          })()
                        : null}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="mt-5 rounded-md border border-[#2a2b30] bg-[#101113] p-5">
                  <p className="font-semibold text-white">
                    {inventory.summary.total === 0
                      ? "No reviews have been saved for this location yet"
                      : "No reviews match this filter"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-zinc-400">
                    {inventory.summary.total === 0
                      ? "Use Check for new reviews. If this location is not connected, open Data connections and match its business listing first."
                      : "Choose a different filter to see the rest of the review inbox."}
                  </p>
                  {inventory.summary.total === 0 ? (
                    <button
                      type="button"
                      onClick={() => router.push("/settings")}
                      className="mt-3 text-sm font-semibold text-[#ff8a4c] hover:text-[#ffa06f]"
                    >
                      Open data connections →
                    </button>
                  ) : null}
                </div>
              )}
            </section>
          </>
        ) : null}
      </section>
    </AppShell>
  );
}
