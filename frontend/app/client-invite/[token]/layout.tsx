import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Set up private report access",
  description: "Activate private read-only access to assigned reports.",
  robots: { index: false, follow: false, nocache: true },
  referrer: "no-referrer",
};

export default function ClientInvitationLayout({ children }: { children: ReactNode }) {
  return children;
}
