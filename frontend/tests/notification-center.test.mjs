import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), "utf8");
}

test("the shared top bar exposes a keyboard-accessible unread notification action", () => {
  const topBar = source("../app/(product)/components/TopBar.tsx");
  const action = source("../app/(product)/components/NotificationAction.tsx");

  assert.match(topBar, /<NotificationAction\s*\/>/);
  assert.match(action, /href="\/notifications"/);
  assert.match(action, /aria-label=\{hasUnread/);
  assert.match(action, /aria-current=/);
  assert.match(action, /unreadCount/);
  assert.match(action, /focus-visible:ring/);
  assert.match(action, /NOTIFICATIONS_CHANGED_EVENT/);
  assert.match(action, /latestRequestRef/);
  assert.match(action, /requestId === latestRequestRef\.current/);
  assert.match(action, /router\.replace\("\/login"\)/);
  assert.match(action, /text-\[#111214\]/);
  assert.doesNotMatch(action, /accent-(?:300|400)/);
});

test("the notification API adapter keeps the REST contract in one adjustable place", () => {
  const api = source("../app/(product)/notifications/notificationApi.ts");

  assert.match(api, /list: "\/notifications"/);
  assert.match(api, /unreadCount: "\/notifications\/unread-count"/);
  assert.match(api, /`\/notifications\/\$\{encodeURIComponent\(notificationId\)\}\/read`/);
  assert.match(api, /`\/notifications\/\$\{encodeURIComponent\(notificationId\)\}\/dismiss`/);
  assert.match(api, /method: "PATCH"/);
  assert.match(api, /method: "POST"/);
  assert.match(api, /items\.filter\(\(item\) => !item\.isRead/);
  assert.match(api, /\[404, 405\]/);
  assert.match(api, /"needs_attention"/);
  assert.match(api, /"action_label"/);
  assert.match(api, /"freshness_at"/);
  assert.match(api, /URLSearchParams/);
  assert.match(api, /total: suppliedTotal/);
  assert.match(api, /limit: suppliedLimit/);
  assert.match(api, /offset: suppliedOffset/);
  assert.match(api, /isSessionExpiredError/);
});

test("notification cards show owner-readable scope, truth, and required actions", () => {
  const page = source("../app/(product)/notifications/page.tsx");
  const intro = source("../app/(product)/components/ProductPageIntro.tsx");

  assert.match(page, /<ProductPageIntro/);
  assert.match(page, /title="See what needs your attention"/);
  assert.match(page, />\s*Organization\s*</);
  assert.match(page, />\s*Location\s*</);
  assert.match(page, />\s*Source\s*</);
  assert.match(page, />\s*Information checked\s*</);
  assert.match(page, />\s*What this means\s*</);
  assert.match(page, />\s*What to do\s*</);
  assert.match(page, /Mark as read/);
  assert.match(page, /"Dismissing…" : "Dismiss"/);
  assert.match(page, /simplifyCustomerCopy/);
  assert.match(page, /sm:grid-cols-2/);
  assert.match(page, /lg:grid-cols-4/);
  assert.match(page, /serverUnreadCount/);
  assert.match(page, /Load older notifications/);
  assert.match(page, /Showing \{items\.length\} of \{total\}/);
  assert.match(page, /loadNotifications\("refresh"\)/);
  assert.match(page, /visibilitychange/);
  assert.match(page, /requestAnimationFrame/);
  assert.match(page, /data-notification-dismiss/);
  assert.match(page, /listHeadingRef/);
  assert.match(page, /await markNotificationRead[\s\S]{0,100}listDataVersionRef\.current \+= 1/);
  assert.match(page, /await dismissNotification[\s\S]{0,100}listDataVersionRef\.current \+= 1/);
  assert.doesNotMatch(page, /!listUpdateError && items\.length === 0/);
  assert.match(page, /text-\[#111214\]/);
  assert.match(page, /router\.replace\("\/login"\)/);
  assert.doesNotMatch(page, /accent-(?:300|400)/);
  assert.match(intro, /"\/notifications"/);
  assert.doesNotMatch(page, /email|digest|notification settings/i);
});

test("the notification page states loading, empty, action failure, and page failure honestly", () => {
  const page = source("../app/(product)/notifications/page.tsx");

  assert.match(page, /state="loading"/);
  assert.match(page, /Checking for notifications/);
  assert.match(page, /state="empty"/);
  assert.match(page, /Nothing needs your attention/);
  assert.match(page, /state="error"/);
  assert.match(page, /Notifications are temporarily unavailable/);
  assert.match(page, /Your saved work has not changed/);
  assert.match(page, /It is still in your list/);
  assert.match(page, /role="alert"/);
  assert.match(page, /aria-live="polite"/);
  assert.match(page, /Try again/);
});
