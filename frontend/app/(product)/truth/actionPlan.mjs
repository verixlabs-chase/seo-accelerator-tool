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
