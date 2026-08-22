import { PlatformApiError, platformApi } from "../../platform/api";

export const NOTIFICATIONS_CHANGED_EVENT = "insightos:notifications-changed";

export const NOTIFICATION_API_ENDPOINTS = {
  list: "/notifications",
  unreadCount: "/notifications/unread-count",
  read: (notificationId: string) =>
    `/notifications/${encodeURIComponent(notificationId)}/read`,
  dismiss: (notificationId: string) =>
    `/notifications/${encodeURIComponent(notificationId)}/dismiss`,
} as const;

export type NotificationTone = "info" | "success" | "warning" | "danger";

export type ProductNotification = {
  id: string;
  title: string;
  meaning: string;
  requiredAction: string;
  organizationName: string;
  locationName: string | null;
  sourceLabel: string;
  freshnessLabel: string | null;
  observedAt: string | null;
  createdAt: string | null;
  actionHref: string | null;
  actionLabel: string | null;
  tone: NotificationTone;
  isRead: boolean;
  readAt: string | null;
  dismissedAt: string | null;
};

type UnknownRecord = Record<string, unknown>;

export type NotificationListResult = {
  items: ProductNotification[];
  unreadCount: number;
  total: number;
  limit: number;
  offset: number;
};

export type NotificationListOptions = {
  limit?: number;
  offset?: number;
};

export type NotificationMutationResult = {
  unreadCount: number | null;
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function firstString(record: UnknownRecord, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function countValue(value: unknown): number | null {
  const numberValue = typeof value === "string" ? Number(value) : value;
  return typeof numberValue === "number" && Number.isFinite(numberValue)
    ? Math.max(0, Math.floor(numberValue))
    : null;
}

function firstCount(record: UnknownRecord, ...keys: string[]) {
  for (const key of keys) {
    const count = countValue(record[key]);
    if (count !== null) return count;
  }
  return null;
}

function safeActionHref(value: string) {
  return value.startsWith("/") && !value.startsWith("//") ? value : null;
}

function notificationTone(value: string): NotificationTone {
  const normalized = value.toLowerCase();
  if (["critical", "danger", "error", "urgent"].includes(normalized)) return "danger";
  if (["high", "warning", "attention", "needs_attention", "needs attention"].includes(normalized)) {
    return "warning";
  }
  if (["success", "positive", "resolved", "complete", "completed"].includes(normalized)) {
    return "success";
  }
  return "info";
}

function normalizeNotification(value: unknown, index: number): ProductNotification | null {
  const raw = asRecord(value);
  const scope = asRecord(raw.scope);
  const organization = asRecord(raw.organization);
  const location = asRecord(raw.location);
  const source = asRecord(raw.source);
  const action = asRecord(raw.action);
  const id = firstString(raw, "id", "notification_id");

  if (!id) return null;

  const status = firstString(raw, "status", "state").toLowerCase();
  const readAt = firstString(raw, "read_at", "readAt") || null;
  const dismissedAt = firstString(raw, "dismissed_at", "dismissedAt") || null;
  const rawHref =
    firstString(raw, "action_href", "action_url", "action_path", "recovery_url") ||
    firstString(action, "href", "url", "path");
  const organizationName =
    firstString(raw, "organization_name", "organization_label", "org_name", "org_label") ||
    firstString(organization, "name", "label") ||
    firstString(scope, "organization_name", "organization_label") ||
    "Current organization";
  const locationName =
    firstString(raw, "location_name", "location_label", "business_location_name", "campaign_name") ||
    firstString(location, "name", "label") ||
    firstString(scope, "location_name", "location_label") ||
    null;
  const sourceLabel =
    firstString(raw, "source_label", "source_name") ||
    (typeof raw.source === "string" ? raw.source.trim() : "") ||
    firstString(source, "label", "name") ||
    "Source not provided";
  const meaning =
    firstString(raw, "meaning", "summary", "body", "message") ||
    "This notice needs your review.";

  return {
    id,
    title: firstString(raw, "title", "headline", "subject") || `Notification ${index + 1}`,
    meaning,
    requiredAction:
      firstString(
        raw,
        "required_action",
        "requiredAction",
        "next_action",
        "action_summary",
        "action_label",
      ) ||
      firstString(action, "summary", "description") ||
      "No action is needed right now.",
    organizationName,
    locationName,
    sourceLabel,
    freshnessLabel:
      firstString(raw, "freshness_label", "freshness", "data_freshness") ||
      firstString(source, "freshness_label", "freshness") ||
      null,
    observedAt:
      firstString(raw, "freshness_at", "observed_at", "source_observed_at", "evidence_at") ||
      firstString(source, "observed_at", "checked_at") ||
      null,
    createdAt: firstString(raw, "created_at", "createdAt", "occurred_at") || null,
    actionHref: rawHref ? safeActionHref(rawHref) : null,
    actionLabel:
      firstString(raw, "action_label", "required_action_label") ||
      firstString(action, "label", "title") ||
      null,
    tone: notificationTone(firstString(raw, "severity", "tone", "priority")),
    isRead:
      raw.is_read === true ||
      raw.read === true ||
      Boolean(readAt) ||
      ["read", "dismissed", "resolved"].includes(status),
    readAt,
    dismissedAt,
  };
}

function notificationItems(payload: unknown) {
  if (Array.isArray(payload)) return payload;
  const record = asRecord(payload);
  if (Array.isArray(record.items)) return record.items;
  if (Array.isArray(record.notifications)) return record.notifications;
  if (Array.isArray(record.results)) return record.results;
  return [];
}

export async function listNotifications(
  options: NotificationListOptions = {},
): Promise<NotificationListResult> {
  const params = new URLSearchParams();
  if (typeof options.limit === "number") {
    params.set("limit", String(Math.min(100, Math.max(1, Math.floor(options.limit)))));
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(Math.max(0, Math.floor(options.offset))));
  }
  const query = params.toString();
  const response = await platformApi(
    `${NOTIFICATION_API_ENDPOINTS.list}${query ? `?${query}` : ""}`,
  );
  const responseRecord = asRecord(response);
  const items = notificationItems(response)
    .map(normalizeNotification)
    .filter((item): item is ProductNotification => Boolean(item));
  const suppliedUnreadCount = firstCount(responseRecord, "unread_count", "unreadCount");
  const suppliedTotal = firstCount(responseRecord, "total");
  const suppliedLimit = firstCount(responseRecord, "limit");
  const suppliedOffset = firstCount(responseRecord, "offset");

  return {
    items,
    unreadCount: suppliedUnreadCount ?? items.filter((item) => !item.isRead && !item.dismissedAt).length,
    total: suppliedTotal ?? items.length,
    limit: suppliedLimit ?? options.limit ?? items.length,
    offset: suppliedOffset ?? options.offset ?? 0,
  };
}

export async function getUnreadNotificationCount() {
  try {
    const response = await platformApi(NOTIFICATION_API_ENDPOINTS.unreadCount);
    const record = asRecord(response);
    const count =
      countValue(response) ?? firstCount(record, "unread_count", "unreadCount", "count");
    if (count !== null) return count;
  } catch (error) {
    if (!(error instanceof PlatformApiError) || ![404, 405].includes(error.status)) {
      throw error;
    }
  }

  const result = await listNotifications({ limit: 1, offset: 0 });
  return result.unreadCount;
}

async function updateNotification(path: string): Promise<NotificationMutationResult> {
  let response: unknown;
  try {
    response = await platformApi(path, { method: "PATCH" });
  } catch (error) {
    if (!(error instanceof PlatformApiError) || error.status !== 405) throw error;
    response = await platformApi(path, { method: "POST" });
  }
  const responseRecord = asRecord(response);
  return {
    unreadCount: firstCount(responseRecord, "unread_count", "unreadCount", "count"),
  };
}

export function markNotificationRead(notificationId: string) {
  return updateNotification(NOTIFICATION_API_ENDPOINTS.read(notificationId));
}

export function dismissNotification(notificationId: string) {
  return updateNotification(NOTIFICATION_API_ENDPOINTS.dismiss(notificationId));
}

export function notifyNotificationsChanged() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
  }
}

export function isSessionExpiredError(error: unknown) {
  return (
    error instanceof Error &&
    /Session expired|No active session|No token found/i.test(error.message)
  );
}
