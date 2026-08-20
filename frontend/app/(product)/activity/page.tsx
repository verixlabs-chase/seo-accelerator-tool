"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import { PlatformApiError, platformApi } from "../../platform/api";
import {
  AppShell,
  DataState,
  LoadingCard,
  ProductIcon,
  ProductPageIntro,
  TruthNotice,
  type ProductIconName,
} from "../components";
import { buildProductNav } from "../nav.config";

type ActivityTone = "neutral" | "positive" | "attention";

type ActivityItem = {
  kind: string;
  category: string;
  category_label: string;
  title: string;
  summary: string;
  tone: ActivityTone;
  actor: { label: string; type: "you" | "team_member" | "support" | "system" };
  occurred_at: string;
};

type ActivityCategory = { id: string; label: string };

type ActivityResponse = {
  items: ActivityItem[];
  count: number;
  has_more: boolean;
  next_cursor: string | null;
  selected_category: string | null;
  categories: ActivityCategory[];
  truth: {
    summary: string;
    raw_payloads_exposed: false;
    internal_event_names_exposed: false;
    internal_identifiers_exposed: false;
    provider_diagnostics_included: false;
    unknown_events_excluded: true;
  };
};

type AccessState = "ready" | "upgrade" | "owner" | "error";

const CATEGORY_ICONS: Record<string, ProductIconName> = {
  reports: "reports",
  automations: "connections",
  content: "content",
  connections: "connections",
  team: "locations",
  workspace: "overview",
  reviews: "reviews",
};

function formatActivityTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function toneClasses(tone: ActivityTone) {
  if (tone === "positive") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-300";
  if (tone === "attention") return "border-amber-500/25 bg-amber-500/10 text-amber-300";
  return "border-[#303137] bg-[#17181b] text-zinc-300";
}

export default function ActivityPage() {
  const pathname = usePathname();
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [categories, setCategories] = useState<ActivityCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [accessState, setAccessState] = useState<AccessState>("ready");
  const [errorMessage, setErrorMessage] = useState("");

  const loadActivity = useCallback(
    async (cursor: string | null, append: boolean) => {
      append ? setLoadingMore(true) : setLoading(true);
      if (!append) setErrorMessage("");
      const params = new URLSearchParams({ limit: "30" });
      if (selectedCategory) params.set("category", selectedCategory);
      if (cursor) params.set("cursor", cursor);

      try {
        const response = (await platformApi(
          `/enterprise/activity?${params.toString()}`,
        )) as ActivityResponse;
        setItems((current) => (append ? [...current, ...response.items] : response.items));
        setCategories(response.categories);
        setNextCursor(response.next_cursor);
        setHasMore(response.has_more);
        setAccessState("ready");
      } catch (error) {
        if (error instanceof PlatformApiError) {
          if (error.reasonCode === "organization_activity_upgrade_required") {
            setAccessState("upgrade");
          } else if (error.status === 403) {
            setAccessState("owner");
          } else {
            setAccessState("error");
          }
          setErrorMessage(error.message);
        } else {
          setAccessState("error");
          setErrorMessage("We could not load the saved activity right now.");
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [selectedCategory],
  );

  useEffect(() => {
    setItems([]);
    setNextCursor(null);
    setHasMore(false);
    void loadActivity(null, false);
  }, [loadActivity]);

  return (
    <AppShell
      navItems={navItems}
      trustSignals={[]}
      accountLabel="Enterprise workspace"
      dateRangeLabel="Saved organization activity"
    >
      <div className="mx-auto max-w-6xl space-y-5">
        <ProductPageIntro
          eyebrow="Enterprise"
          title="See who changed what"
          summary="Review important team, connection, reporting, and account changes without exposing private technical details."
        />

        <TruthNotice title="This is a focused workspace history." tone="info">
          It includes meaningful saved actions. Background checks and private provider details are not shown.
        </TruthNotice>

        {loading ? <LoadingCard summary="Loading saved workspace activity." /> : null}

        {!loading && accessState === "upgrade" ? (
          <DataState
            state="unsupported"
            title="Organization activity is available with Enterprise"
            summary="Enterprise keeps important team and workspace changes in one owner-only history."
            action={
              <Link
                href="/settings#plan-and-billing"
                className="inline-flex rounded-md bg-accent-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent-400"
              >
                Review Enterprise options
              </Link>
            }
          />
        ) : null}

        {!loading && accessState === "owner" ? (
          <DataState
            state="unsupported"
            title="Only the workspace owner can view this history"
            summary="Ask the workspace owner if you need help checking a saved organization change."
          />
        ) : null}

        {!loading && accessState === "error" ? (
          <DataState
            state="error"
            title="Workspace activity is temporarily unavailable"
            summary={errorMessage || "Your saved work was not changed. Try loading this page again."}
            action={
              <button
                type="button"
                onClick={() => void loadActivity(null, false)}
                className="rounded-md border border-[#383940] px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/5"
              >
                Try again
              </button>
            }
          />
        ) : null}

        {!loading && accessState === "ready" ? (
          <section aria-labelledby="activity-heading" className="overflow-hidden rounded-xl border border-[#292a2f] bg-[#121316]">
            <div className="border-b border-[#292a2f] px-4 py-4 md:px-5">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <h2 id="activity-heading" className="text-lg font-semibold text-white">
                    Organization activity
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Important saved actions, newest first.
                  </p>
                </div>
                <label className="text-sm font-medium text-zinc-300">
                  Show
                  <select
                    value={selectedCategory}
                    onChange={(event) => setSelectedCategory(event.target.value)}
                    className="ml-2 rounded-md border border-[#383940] bg-[#18191d] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-accent-500"
                  >
                    <option value="">All activity</option>
                    {categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>

            {items.length === 0 ? (
              <DataState
                state="empty"
                title="No tracked activity in this view yet"
                summary="This does not mean nothing happened. Only meaningful saved organization actions appear here."
              />
            ) : (
              <ol className="divide-y divide-[#25262b]">
                {items.map((item, index) => (
                  <li key={`${item.occurred_at}-${item.kind}-${index}`} className="px-4 py-4 md:px-5">
                    <div className="flex items-start gap-3.5">
                      <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg border ${toneClasses(item.tone)}`}>
                        <ProductIcon name={CATEGORY_ICONS[item.category] || "activity"} size={19} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                          <div>
                            <p className="text-sm font-semibold text-zinc-100">{item.title}</p>
                            <p className="mt-1 text-sm leading-5 text-zinc-400">{item.summary}</p>
                          </div>
                          <time className="shrink-0 text-xs text-zinc-500" dateTime={item.occurred_at}>
                            {formatActivityTime(item.occurred_at)}
                          </time>
                        </div>
                        <p className="mt-2 text-xs text-zinc-500">
                          <span className="font-medium text-zinc-300">{item.actor.label}</span>
                          <span aria-hidden="true"> · </span>
                          {item.category_label}
                        </p>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {hasMore ? (
              <div className="border-t border-[#292a2f] px-4 py-4 text-center">
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={() => void loadActivity(nextCursor, true)}
                  className="rounded-md border border-[#383940] px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/5 disabled:cursor-wait disabled:opacity-60"
                >
                  {loadingMore ? "Loading older activity…" : "Load older activity"}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
