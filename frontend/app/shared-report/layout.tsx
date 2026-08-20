import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Private client report | InsightOS",
  description: "A private, time-limited InsightOS client report.",
  robots: { index: false, follow: false, nocache: true },
  referrer: "no-referrer",
};

export default function SharedReportLayout({ children }: { children: ReactNode }) {
  return children;
}
