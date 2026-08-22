"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getUnreadNotificationCount,
  isSessionExpiredError,
  NOTIFICATIONS_CHANGED_EVENT,
} from "../notifications/notificationApi";
import { ProductIcon } from "./ProductIcon";
import { cn } from "./utils";

export function NotificationAction() {
  const pathname = usePathname();
  const router = useRouter();
  const [unreadCount, setUnreadCount] = useState<number | null>(null);
  const latestRequestRef = useRef(0);

  const loadUnreadCount = useCallback(async () => {
    const requestId = ++latestRequestRef.current;
    try {
      const count = await getUnreadNotificationCount();
      if (requestId === latestRequestRef.current) setUnreadCount(count);
    } catch (error) {
      if (isSessionExpiredError(error)) {
        router.replace("/login");
        return;
      }
      if (requestId !== latestRequestRef.current) return;
      setUnreadCount(null);
    }
  }, [router]);

  useEffect(() => {
    void loadUnreadCount();
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, loadUnreadCount);
    window.addEventListener("focus", loadUnreadCount);
    return () => {
      latestRequestRef.current += 1;
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, loadUnreadCount);
      window.removeEventListener("focus", loadUnreadCount);
    };
  }, [loadUnreadCount]);

  const hasUnread = typeof unreadCount === "number" && unreadCount > 0;
  const countLabel = unreadCount && unreadCount > 99 ? "99+" : String(unreadCount ?? "");

  return (
    <Link
      href="/notifications"
      aria-label={hasUnread ? `Notifications, ${unreadCount} unread` : "Notifications"}
      aria-current={pathname === "/notifications" ? "page" : undefined}
      className={cn(
        "inline-flex min-h-9 items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#101114]",
        pathname === "/notifications"
          ? "border-accent-500/40 bg-accent-500/15 text-white"
          : "border-[#303137] bg-[#151619] text-zinc-200 hover:border-[#45464d] hover:bg-[#1a1b1f]",
      )}
    >
      <ProductIcon name="notifications" size={17} />
      <span>Notifications</span>
      {hasUnread ? (
        <span
          aria-hidden="true"
          className="inline-flex min-w-5 items-center justify-center rounded-full bg-accent-500 px-1.5 py-0.5 text-[11px] font-bold leading-none text-[#111214]"
        >
          {countLabel}
        </span>
      ) : null}
    </Link>
  );
}
