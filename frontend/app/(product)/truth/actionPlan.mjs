const EXCLUDED_STATUSES = new Set(["ARCHIVED"]);

function confidenceOf(item) {
  return Number(item?.confidence_score ?? item?.confidence ?? 0);
}

function createdAtOf(item) {
  const value = new Date(item?.created_at || 0).getTime();
  return Number.isNaN(value) ? 0 : value;
}

export function getCanonicalActionKey(item) {
  const actionId = item?.action_plan?.action_id;
  if (actionId) {
    return String(actionId);
  }

  const recommendationType = String(item?.recommendation_type || "");
  if (recommendationType.includes("::")) {
    return recommendationType.split("::").at(-1) || recommendationType;
  }
  return recommendationType || String(item?.id || "unknown-action");
}

export function getRecommendationPortfolio(items, nextLimit = 4) {
  const orderedCandidates = [...(Array.isArray(items) ? items : [])]
    .filter(
      (item) =>
        !EXCLUDED_STATUSES.has(String(item?.status || "")) &&
        item?.recommendation_type !== "strategy_bundle_record",
    )
    .sort((left, right) => {
      const riskDifference = Number(right?.risk_tier || 0) - Number(left?.risk_tier || 0);
      if (riskDifference !== 0) {
        return riskDifference;
      }

      const confidenceDifference = confidenceOf(right) - confidenceOf(left);
      if (confidenceDifference !== 0) {
        return confidenceDifference;
      }

      return createdAtOf(right) - createdAtOf(left);
    });

  const seen = new Set();
  const ordered = orderedCandidates.filter((item) => {
    const key = getCanonicalActionKey(item);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });

  return {
    ordered,
    primary: ordered[0] || null,
    next: ordered.slice(1, 1 + Math.max(0, nextLimit)),
    later: ordered.slice(1 + Math.max(0, nextLimit)),
  };
}

export function getRecommendationRoutines(items) {
  const groups = {
    daily: [],
    weekly: [],
    monthly: [],
    later: [],
  };

  for (const item of getRecommendationPortfolio(items, Number.MAX_SAFE_INTEGER).ordered) {
    const cadence = String(item?.action_plan?.work_item?.cadence || "later");
    const group = Object.prototype.hasOwnProperty.call(groups, cadence)
      ? cadence
      : "later";
    groups[group].push(item);
  }

  return groups;
}

export function getActionTrack(item) {
  const plan = item?.action_plan;
  const explicitTrack =
    plan?.measurement_track || plan?.work_item?.measurement?.measurement_track;
  if (explicitTrack === "google_business_profile") {
    return "google_business_profile";
  }
  if (explicitTrack === "website") {
    return "website";
  }

  const category = String(plan?.category || "");
  const primaryMetricId = String(
    plan?.primary_metric_id || plan?.success_metric_ids?.[0] || "",
  );
  return ["local", "reputation", "google_business_profile"].includes(category) ||
    primaryMetricId.startsWith("local.")
    ? "google_business_profile"
    : "website";
}

export function getActionTrackGroups(items) {
  const groups = {
    website: [],
    google_business_profile: [],
  };
  for (const item of getRecommendationPortfolio(items, Number.MAX_SAFE_INTEGER).ordered) {
    groups[getActionTrack(item)].push(item);
  }
  return groups;
}

export function getPrimaryMeasurement(item) {
  const plan = item?.action_plan;
  const measurement = plan?.work_item?.measurement;
  if (!measurement) {
    return null;
  }
  const metricId = String(
    measurement?.primary_metric_id ||
      plan?.primary_metric_id ||
      measurement?.measurement_contract?.primary_metric_id ||
      plan?.success_metric_ids?.[0] ||
      measurement?.baseline_metrics?.[0]?.metric_id ||
      "",
  );
  const baseline = (measurement?.baseline_metrics || []).find(
    (metric) => String(metric?.metric_id) === metricId,
  ) || null;
  const outcome = (measurement?.outcome_metrics || []).find(
    (metric) => String(metric?.metric_id) === metricId,
  ) || null;
  return {
    metricId,
    baseline,
    outcome,
    resultClassification:
      measurement?.result_classification ||
      measurement?.measurement_contract?.result?.classification ||
      "waiting_for_results",
    checkOnOrAfter:
      measurement?.observation_due_at ||
      measurement?.measurement_contract?.observation?.check_on_or_after ||
      null,
    target: measurement?.measurement_contract?.target || null,
  };
}

export function getWorkProgress(item) {
  const progress = item?.action_plan?.work_item?.progress;
  const completed = Number(progress?.completed_required || 0);
  const total = Number(progress?.required_total || 0);
  return {
    completed,
    total,
    label: total > 0 ? `${completed} of ${total} steps done` : "Plan details coming soon",
    percent: total > 0 ? Math.round((completed / total) * 100) : 0,
  };
}
