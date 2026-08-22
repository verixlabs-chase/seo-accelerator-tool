"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  AppShell,
  DataState,
  ProductIcon,
  ProductPageIntro,
  type ProductIconName,
} from "../components";
import { buildProductNav } from "../nav.config";
import { simplifyCustomerCopy } from "../truth/customerLanguage.mjs";
import {
  dismissNotification,
  isSessionExpiredError,
  listNotifications,
  markNotificationRead,
  notifyNotificationsChanged,
  type NotificationTone,
  type ProductNotification,
} from "./notificationApi";

const PAGE_SIZE = 50;

const TONE_STYLES: Record<NotificationTone, string> = {
  info: "border-sky-500/25 bg-sky-500/10 text-sky-300",
  success: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  warning: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  danger: "border-rose-500/25 bg-rose-500/10 text-rose-300",
};

const TONE_ICONS: Record<NotificationTone, ProductIconName> = {
  info: "info",
  success: "check",
  warning: "warning",
  danger: "warning",
};

function customerText(value: string, fallback: string) {
  return simplifyCustomerCopy(value, { fallback }) || fallback;
}

function formatNotificationTime(value: string | null) {
  if (!value) return "Freshness not provided";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Freshness not provided";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function freshnessText(notification: ProductNotification) {
  if (notification.freshnessLabel) {
    return customerText(notification.freshnessLabel, "Freshness not provided");
  }
  return formatNotificationTime(notification.observedAt || notification.createdAt);
}

export default function NotificationsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const [items, setItems] = useState<ProductNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [listUpdateError, setListUpdateError] = useState("");
  const [serverUnreadCount, setServerUnreadCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [busyAction, setBusyAction] = useState("");
  const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState("");
  const itemsRef = useRef<ProductNotification[]>([]);
  const listRequestActiveRef = useRef(false);
  const listDataVersionRef = useRef(0);
  const articleRefs = useRef<Record<string, HTMLElement | null>>({});
  const listHeadingRef = useRef<HTMLHeadingElement | null>(null);

  const loadNotifications = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (listRequestActiveRef.current) return;
    listRequestActiveRef.current = true;
    if (mode === "initial") {
      setLoading(true);
      setErrorMessage("");
    } else {
      setRefreshing(true);
      setListUpdateError("");
    }

    try {
      const dataVersion = listDataVersionRef.current;
      const targetCount =
        mode === "refresh" ? Math.max(PAGE_SIZE, itemsRef.current.length) : PAGE_SIZE;
      const refreshedItems: ProductNotification[] = [];
      let offset = 0;
      let unreadCount = 0;
      let refreshedTotal = 0;

      do {
        const response = await listNotifications({
          limit: Math.min(PAGE_SIZE, targetCount - offset),
          offset,
        });
        refreshedItems.push(...response.items.filter((item) => !item.dismissedAt));
        unreadCount = response.unreadCount;
        refreshedTotal = response.total;
        offset += response.items.length;
        if (response.items.length === 0) break;
      } while (offset < targetCount && offset < refreshedTotal);

      const uniqueItems = Array.from(
        new Map(refreshedItems.map((item) => [item.id, item])).values(),
      );
      if (dataVersion !== listDataVersionRef.current) return;
      itemsRef.current = uniqueItems;
      setItems(uniqueItems);
      setServerUnreadCount(unreadCount);
      setTotal(refreshedTotal);
    } catch (error) {
      if (isSessionExpiredError(error)) {
        router.replace("/login");
        return;
      }
      if (mode === "initial") {
        setErrorMessage(
          "We could not load notifications right now. Your saved work has not changed.",
        );
      } else {
        setListUpdateError(
          "We could not check for newer notifications. The list below has not changed.",
        );
      }
    } finally {
      listRequestActiveRef.current = false;
      if (mode === "initial") setLoading(false);
      else setRefreshing(false);
    }
  }, [router]);

  useEffect(() => {
    void loadNotifications("initial");
  }, [loadNotifications]);

  useEffect(() => {
    function refreshOnFocus() {
      void loadNotifications("refresh");
    }

    function refreshWhenVisible() {
      if (document.visibilityState === "visible") refreshOnFocus();
    }

    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [loadNotifications]);

  const hasMore = items.length < total;

  async function loadMoreNotifications() {
    if (listRequestActiveRef.current || !hasMore) return;
    listRequestActiveRef.current = true;
    setLoadingMore(true);
    setListUpdateError("");

    try {
      const dataVersion = listDataVersionRef.current;
      const response = await listNotifications({
        limit: PAGE_SIZE,
        offset: itemsRef.current.length,
      });
      const mergedItems = Array.from(
        new Map(
          [...itemsRef.current, ...response.items.filter((item) => !item.dismissedAt)].map(
            (item) => [item.id, item],
          ),
        ).values(),
      );
      if (dataVersion !== listDataVersionRef.current) return;
      itemsRef.current = mergedItems;
      setItems(mergedItems);
      setServerUnreadCount(response.unreadCount);
      setTotal(response.total);
    } catch (error) {
      if (isSessionExpiredError(error)) {
        router.replace("/login");
        return;
      }
      setListUpdateError(
        "We could not load older notifications. Your current list has not changed.",
      );
    } finally {
      listRequestActiveRef.current = false;
      setLoadingMore(false);
    }
  }

  async function runNotificationAction(
    notification: ProductNotification,
    action: "read" | "dismiss",
  ) {
    const actionKey = `${action}:${notification.id}`;
    const currentIndex = itemsRef.current.findIndex((item) => item.id === notification.id);
    const adjacentNotificationId =
      itemsRef.current[currentIndex + 1]?.id ?? itemsRef.current[currentIndex - 1]?.id ?? null;
    setBusyAction(actionKey);
    setStatusMessage("");
    setItemErrors((current) => ({ ...current, [notification.id]: "" }));
    listDataVersionRef.current += 1;

    try {
      if (action === "read") {
        const response = await markNotificationRead(notification.id);
        listDataVersionRef.current += 1;
        const nextItems = itemsRef.current.map((item) =>
          item.id === notification.id
            ? { ...item, isRead: true, readAt: new Date().toISOString() }
            : item,
        );
        itemsRef.current = nextItems;
        setItems(nextItems);
        setServerUnreadCount((current) =>
          response.unreadCount ?? Math.max(0, current - (notification.isRead ? 0 : 1)),
        );
        setStatusMessage("Notification marked as read.");
        window.requestAnimationFrame(() => {
          const dismissButton = articleRefs.current[notification.id]?.querySelector<HTMLElement>(
            "[data-notification-dismiss]",
          );
          (dismissButton ?? listHeadingRef.current)?.focus();
        });
      } else {
        const response = await dismissNotification(notification.id);
        listDataVersionRef.current += 1;
        const nextItems = itemsRef.current.filter((item) => item.id !== notification.id);
        itemsRef.current = nextItems;
        setItems(nextItems);
        setServerUnreadCount((current) =>
          response.unreadCount ?? Math.max(0, current - (notification.isRead ? 0 : 1)),
        );
        setTotal((current) => Math.max(0, current - 1));
        setStatusMessage("Notification dismissed.");
        window.requestAnimationFrame(() => {
          const adjacentArticle = adjacentNotificationId
            ? articleRefs.current[adjacentNotificationId]
            : null;
          const nextAction = adjacentArticle?.querySelector<HTMLElement>(
            "a[href], button:not([disabled])",
          );
          (nextAction ?? listHeadingRef.current)?.focus();
        });
      }
      notifyNotificationsChanged();
    } catch (error) {
      if (isSessionExpiredError(error)) {
        router.replace("/login");
        return;
      }
      setItemErrors((current) => ({
        ...current,
        [notification.id]:
          action === "read"
            ? "We could not mark this notification as read. Try again."
            : "We could not dismiss this notification. It is still in your list.",
      }));
    } finally {
      setBusyAction("");
    }
  }

  return (
    <AppShell
      navItems={navItems}
      trustSignals={[]}
      accountLabel="Workspace notifications"
      dateRangeLabel="Newest notices first"
    >
      <div className="mx-auto max-w-6xl space-y-5">
        <ProductPageIntro
          eyebrow="Notifications"
          title="See what needs your attention"
          summary="Review meaningful changes, completed work, and decisions for every location in one quiet list."
        />

        <section
          aria-labelledby="notification-list-heading"
          aria-busy={loading || refreshing || loadingMore}
          className="overflow-hidden rounded-xl border border-[#292a2f] bg-[#121316]"
        >
          <div className="flex flex-col gap-2 border-b border-[#292a2f] px-4 py-4 sm:flex-row sm:items-start sm:justify-between md:px-5">
            <div>
              <h2
                ref={listHeadingRef}
                id="notification-list-heading"
                tabIndex={-1}
                className="text-lg font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
              >
                Current notifications
              </h2>
              <p className="mt-1 text-sm leading-5 text-zinc-400">
                Dismissing a notice removes it from this list. It does not undo saved work.
              </p>
            </div>
            {!loading && !errorMessage ? (
              <p className="shrink-0 text-sm font-medium text-zinc-300" aria-live="polite">
                {serverUnreadCount === 0
                  ? "No unread notifications"
                  : `${serverUnreadCount} unread notification${serverUnreadCount === 1 ? "" : "s"}`}
                {refreshing ? <span className="sr-only"> Checking for updates.</span> : null}
              </p>
            ) : null}
          </div>

          <p className="sr-only" aria-live="polite" aria-atomic="true">
            {statusMessage}
          </p>

          {!loading && listUpdateError ? (
            <div
              role="alert"
              className="flex flex-col gap-2 border-b border-amber-500/20 bg-amber-500/[0.07] px-4 py-3 text-sm text-amber-100 sm:flex-row sm:items-center sm:justify-between md:px-5"
            >
              <p>{listUpdateError}</p>
              <button
                type="button"
                onClick={() => void loadNotifications("refresh")}
                className="shrink-0 self-start rounded-md border border-amber-400/30 px-3 py-1.5 font-semibold text-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 sm:self-auto"
              >
                Check again
              </button>
            </div>
          ) : null}

          {loading ? (
            <DataState
              state="loading"
              title="Checking for notifications"
              summary="We are looking for recent updates and work that may need your attention."
            />
          ) : null}

          {!loading && errorMessage ? (
            <DataState
              state="error"
              title="Notifications are temporarily unavailable"
              summary={errorMessage}
              action={
                <button
                  type="button"
                  onClick={() => void loadNotifications()}
                  className="rounded-md border border-[#383940] px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                >
                  Try again
                </button>
              }
            />
          ) : null}

          {!loading && !errorMessage && items.length === 0 ? (
            <DataState
              state="empty"
              title="Nothing needs your attention"
              summary="New updates and required decisions will appear here when there is something useful to review."
            />
          ) : null}

          {!loading && !errorMessage && items.length > 0 ? (
            <>
              <ol className="divide-y divide-[#25262b]">
              {items.map((notification) => {
                const readActionKey = `read:${notification.id}`;
                const dismissActionKey = `dismiss:${notification.id}`;
                const titleId = `notification-title-${notification.id}`;
                const itemError = itemErrors[notification.id];

                return (
                  <li key={notification.id}>
                    <article
                      ref={(element) => {
                        articleRefs.current[notification.id] = element;
                      }}
                      aria-labelledby={titleId}
                      className={`px-4 py-5 md:px-5 ${notification.isRead ? "bg-transparent" : "bg-white/[0.018]"}`}
                    >
                      <div className="flex items-start gap-3.5">
                        <div
                          className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg border ${TONE_STYLES[notification.tone]}`}
                        >
                          <ProductIcon name={TONE_ICONS[notification.tone]} size={19} />
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span
                                  className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.1em] ${
                                    notification.isRead
                                      ? "border-[#35363c] bg-[#18191c] text-zinc-500"
                                      : "border-accent-500/30 bg-accent-500/10 text-accent-500"
                                  }`}
                                >
                                  {notification.isRead ? "Read" : "New"}
                                </span>
                                <h3 id={titleId} className="text-base font-semibold text-white">
                                  {customerText(notification.title, "Notification needs review")}
                                </h3>
                              </div>
                            </div>
                            {notification.createdAt ? (
                              <time
                                dateTime={notification.createdAt}
                                className="shrink-0 text-xs text-zinc-500"
                              >
                                Added {formatNotificationTime(notification.createdAt)}
                              </time>
                            ) : null}
                          </div>

                          <dl className="mt-4 grid gap-3 rounded-lg border border-[#28292e] bg-[#0f1012] p-3 sm:grid-cols-2 lg:grid-cols-4">
                            <div>
                              <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                Organization
                              </dt>
                              <dd className="mt-1 text-sm text-zinc-200">
                                {notification.organizationName}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                Location
                              </dt>
                              <dd className="mt-1 text-sm text-zinc-200">
                                {notification.locationName || "Organization-wide"}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                Source
                              </dt>
                              <dd className="mt-1 text-sm text-zinc-200">
                                {customerText(notification.sourceLabel, "Source not provided")}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                Information checked
                              </dt>
                              <dd className="mt-1 text-sm text-zinc-200">
                                {freshnessText(notification)}
                              </dd>
                            </div>
                          </dl>

                          <div className="mt-4 grid gap-3 md:grid-cols-2">
                            <div className="rounded-lg border border-[#28292e] bg-[#16171a] p-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">
                                What this means
                              </p>
                              <p className="mt-2 text-sm leading-6 text-zinc-300">
                                {customerText(notification.meaning, "This notice needs your review.")}
                              </p>
                            </div>
                            <div className="rounded-lg border border-accent-500/20 bg-accent-500/[0.07] p-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-accent-500">
                                What to do
                              </p>
                              <p className="mt-2 text-sm leading-6 text-zinc-200">
                                {customerText(
                                  notification.requiredAction,
                                  "No action is needed right now.",
                                )}
                              </p>
                            </div>
                          </div>

                          {itemError ? (
                            <p role="alert" className="mt-3 text-sm text-rose-300">
                              {itemError}
                            </p>
                          ) : null}

                          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                            {notification.actionHref ? (
                              <Link
                                href={notification.actionHref}
                                className="inline-flex min-h-9 items-center justify-center rounded-md bg-accent-500 px-4 py-2 text-sm font-semibold text-[#111214] transition hover:bg-accent-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#121316]"
                              >
                                {customerText(notification.actionLabel || "Open next step", "Open next step")}
                              </Link>
                            ) : null}
                            {!notification.isRead ? (
                              <button
                                type="button"
                                disabled={Boolean(busyAction)}
                                onClick={() => void runNotificationAction(notification, "read")}
                                className="min-h-9 rounded-md border border-[#3a3b42] px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 disabled:cursor-wait disabled:opacity-60"
                              >
                                {busyAction === readActionKey ? "Marking as read…" : "Mark as read"}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              data-notification-dismiss
                              disabled={Boolean(busyAction)}
                              onClick={() => void runNotificationAction(notification, "dismiss")}
                              className="min-h-9 rounded-md border border-transparent px-4 py-2 text-sm font-medium text-zinc-400 transition hover:border-[#33343a] hover:bg-white/[0.03] hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 disabled:cursor-wait disabled:opacity-60"
                            >
                              {busyAction === dismissActionKey ? "Dismissing…" : "Dismiss"}
                            </button>
                          </div>
                        </div>
                      </div>
                    </article>
                  </li>
                );
              })}
              </ol>
              {hasMore || total >= PAGE_SIZE ? (
                <div className="flex flex-col gap-3 border-t border-[#292a2f] px-4 py-4 sm:flex-row sm:items-center sm:justify-between md:px-5">
                  <p className="text-sm text-zinc-400">
                    Showing {items.length} of {total} current notifications.
                  </p>
                  <button
                    type="button"
                    aria-disabled={!hasMore || loadingMore || refreshing || Boolean(busyAction)}
                    onClick={() => {
                      if (hasMore && !loadingMore && !refreshing && !busyAction) {
                        void loadMoreNotifications();
                      }
                    }}
                    className="rounded-md border border-[#3a3b42] px-4 py-2 text-sm font-semibold text-zinc-100 transition hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 aria-disabled:cursor-default aria-disabled:opacity-60"
                  >
                    {loadingMore
                      ? "Loading older notifications…"
                      : hasMore
                        ? "Load older notifications"
                        : "All notifications loaded"}
                  </button>
                </div>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
