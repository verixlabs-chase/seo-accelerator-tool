import type { ReactNode } from "react";

export type NavItem = {
  href: string;
  label: string;
  badge?: string;
  active?: boolean;
  disabled?: boolean;
  hidden?: boolean;
};

export type TrustSignal = {
  label: string;
  value: string;
  tone?: "info" | "success" | "warning" | "danger";
};

export type RuntimeTruth = {
  classification?: string;
  states?: string[];
  provider_state?: string;
  setup_state?: string;
  operator_state?: string;
  freshness_state?: string;
  summary?: string;
  reasons?: string[];
  generated_at?: string;
};

export type QuickAction = {
  label: string;
  href?: string;
  onClickLabel?: string;
  onClick?: () => void;
};

export type Insight = {
  title: string;
  body: string;
  tone?: "info" | "success" | "warning" | "danger";
  action?: QuickAction;
};

export type ReportSection = {
  title: string;
  summary: string;
  metric?: string;
  visual?: ReactNode;
};
