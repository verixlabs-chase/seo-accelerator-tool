const PRIORITY = {
  provider_backed: 0,
  generated: 1,
  scheduled: 2,
  in_progress: 1,
  stale: 2,
  minimal_artifact: 3,
  operator_assisted: 3,
  delivery_unverified: 4,
  non_durable: 5,
  heuristic: 4,
  synthetic: 5,
  unavailable: 6,
};

/**
 * @param {{ classification?: string } | null | undefined} truth
 * @returns {"success" | "info" | "warning" | "danger"}
 */
function getRuntimeTruthTone(truth) {
  const classification = truth?.classification || "unknown";

  if (classification === "provider_backed") {
    return "success";
  }
  if (classification === "generated" || classification === "scheduled") {
    return "info";
  }
  if (classification === "in_progress" || classification === "stale") {
    return "info";
  }
  if (classification === "heuristic" || classification === "operator_assisted" || classification === "minimal_artifact") {
    return "warning";
  }
  return "danger";
}

/**
 * @param {{ classification?: string } | null | undefined} truth
 * @returns {string}
 */
function getRuntimeTruthLabel(truth) {
  const classification = truth?.classification || "unknown";

  if (classification === "provider_backed") {
    return "Provider-backed";
  }
  if (classification === "heuristic") {
    return "Heuristic";
  }
  if (classification === "generated") {
    return "Generated";
  }
  if (classification === "scheduled") {
    return "Scheduled";
  }
  if (classification === "synthetic") {
    return "Synthetic";
  }
  if (classification === "operator_assisted") {
    return "Operator-assisted";
  }
  if (classification === "minimal_artifact") {
    return "Minimal artifact";
  }
  if (classification === "delivery_unverified") {
    return "Delivery unverified";
  }
  if (classification === "non_durable") {
    return "Non-durable";
  }
  if (classification === "stale") {
    return "Stale";
  }
  if (classification === "in_progress") {
    return "In progress";
  }
  if (classification === "unavailable") {
    return "Unavailable";
  }
  return "Unknown";
}

/**
 * @param {{ summary?: string } | null | undefined} truth
 * @param {string | undefined} fallback
 * @returns {string}
 */
function getRuntimeTruthSummary(truth, fallback) {
  return truth?.summary || fallback || "Runtime truth details are not available yet.";
}

/**
 * @param {string} label
 * @param {{ classification?: string, summary?: string } | null | undefined} truth
 * @param {string | undefined} fallback
 * @returns {{ label: string, value: string, tone: "success" | "info" | "warning" | "danger" }}
 */
function buildRuntimeTruthSignal(label, truth, fallback) {
  return {
    label,
    value: getRuntimeTruthLabel(truth),
    tone: getRuntimeTruthTone(truth),
  };
}

function pickPrimaryRuntimeTruth(truths) {
  const items = truths.filter(Boolean);
  if (items.length === 0) {
    return null;
  }

  return [...items].sort(
    (left, right) =>
      (PRIORITY[right?.classification || "provider_backed"] || 0) -
      (PRIORITY[left?.classification || "provider_backed"] || 0),
  )[0];
}

export {
  buildRuntimeTruthSignal,
  getRuntimeTruthLabel,
  getRuntimeTruthSummary,
  getRuntimeTruthTone,
  pickPrimaryRuntimeTruth,
};
