import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Your private reports",
  description: "Private reports shared with your client sign-in.",
  robots: { index: false, follow: false, nocache: true },
  referrer: "no-referrer",
};

export default function ClientReportsLayout({ children }: { children: ReactNode }) {
  return children;
}
