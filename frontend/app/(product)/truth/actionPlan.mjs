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
