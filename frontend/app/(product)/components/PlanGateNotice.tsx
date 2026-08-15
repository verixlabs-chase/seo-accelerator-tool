"use client";

import Link from "next/link";
import {
  canActivateAnotherLocation,
  isLocationAllowanceEnforced,
} from "../truth/locationAllowanceTruth.mjs";

export {
  canActivateAnotherLocation,
  isLocationAllowanceEnforced,
} from "../truth/locationAllowanceTruth.mjs";

export type CommercialLocationPlan = {
  code: string;
  name: string;
  monthly_price: number;
  included_locations: number;
  active_locations: number;
  remaining_locations: number;
  location_allowance_enforced?: boolean;
  over_limit_by?: number;
  can_activate_location?: boolean;
  additional_locations_require_custom_terms?: boolean;
};

export type CommercialPlanUpgrade = {
  plan_code: string;
  plan_name: string;
  monthly_price: number;
  headline: string;
  reasons: string[];
};

export type LocationAllowanceSummary = {
  commercial_catalog_version?: string;
  plan: CommercialLocationPlan;
  upgrade?: CommercialPlanUpgrade | null;
};

type PlanGateNoticeProps = {
  allowance: LocationAllowanceSummary;
  orgRole?: string | null;
  detail?: string;
  className?: string;
};

export function locationUsageLabel(plan: CommercialLocationPlan): string {
  const noun = plan.included_locations === 1 ? "location" : "locations";
  return `${plan.active_locations} of ${plan.included_locations} active ${noun} in use`;
}

export function PlanGateNotice({
  allowance,
  orgRole,
  detail,
  className = "",
}: PlanGateNoticeProps) {
  const { plan, upgrade } = allowance;
  const overLimit = Math.max(0, plan.over_limit_by || 0);
  const isOwner = orgRole === "org_owner";
  const customTerms = !upgrade || plan.additional_locations_require_custom_terms;
  const title = overLimit > 0
    ? "New locations are paused"
    : `${plan.name} location limit reached`;
  const defaultDetail = overLimit > 0
    ? `This workspace has ${plan.active_locations} active locations. Your ${plan.name} plan includes ${plan.included_locations}. Everything already saved stays available, but another location cannot be added or turned back on yet.`
    : `Your ${plan.name} plan includes ${plan.included_locations} active ${plan.included_locations === 1 ? "location" : "locations"}, and ${plan.included_locations === 1 ? "it is" : "they are"} in use. Everything already saved stays available.`;

  return (
    <section
      aria-labelledby="location-plan-limit-heading"
      className={`rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-amber-50 ${className}`.trim()}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-200/75">
        Location allowance
      </p>
      <h4 id="location-plan-limit-heading" className="mt-1.5 text-base font-semibold text-white">
        {title}
      </h4>
      <p className="mt-2 text-sm leading-6 text-amber-50/85">
        {detail || defaultDetail}
      </p>

      {upgrade ? (
        <div className="mt-4 border-t border-amber-200/15 pt-4">
          <p className="text-sm font-semibold text-white">
            {upgrade.plan_code === "multi_location"
              ? `${upgrade.plan_name} includes up to 10 locations`
              : `${upgrade.plan_name} adds more locations with custom terms`}
          </p>
          <ul className="mt-2 space-y-1 text-sm leading-6 text-amber-50/80">
            {upgrade.reasons.slice(0, 3).map((reason) => (
              <li key={reason}>✓ {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {isOwner ? (
          customTerms ? (
            <Link
              href="/help"
              className="inline-flex items-center justify-center rounded-md border border-amber-200/30 bg-amber-50/10 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-amber-50/15"
            >
              Ask about adding locations
            </Link>
          ) : (
            <Link
              href="/settings#plan-and-billing"
              className="inline-flex items-center justify-center rounded-md border border-amber-200/30 bg-amber-50/10 px-3.5 py-2 text-sm font-semibold text-white transition hover:bg-amber-50/15"
            >
              Review {upgrade?.plan_name || "your plan"}
            </Link>
          )
        ) : (
          <p className="text-sm font-medium text-amber-100">
            Ask the workspace owner to review the plan.
          </p>
        )}
        <span className="text-xs text-amber-100/65">
          Archiving a location makes room without deleting its saved history.
        </span>
      </div>
    </section>
  );
}
