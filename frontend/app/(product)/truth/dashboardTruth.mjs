function toTitleCase(value) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function isFailedStatus(value) {
  return ["failed", "error", "cancelled", "canceled"].includes((value || "").toLowerCase());
}

function isPendingStatus(value) {
  return ["queued", "pending", "running", "in_progress", "scheduled", "processing"].includes(
    (value || "").toLowerCase(),
  );
}

function getSetupWorkflowState(campaign, run) {
  if (!campaign) {
    return {
      label: "Business setup",
      status: "Action needed",
      tone: "warning",
      detail: "No business is active yet, so InsightOS cannot start checks or show results.",
      nextStep: "Start guided setup or add your business manually.",
    };
  }

  if (!run) {
    return {
      label: "Business setup",
      status: "In progress",
      tone: "info",
      detail: `${campaign.name || "This business"} is saved, but the first website scan has not run yet.`,
      nextStep: "Run the first website scan to finish setup.",
    };
  }

  return {
    label: "Business setup",
    status: "Complete",
    tone: "success",
    detail: `${campaign.name || "This business"} is active and the first checks have started.`,
    nextStep: "Use the cards below to see what still needs attention.",
  };
}

function getCrawlWorkflowState(run, campaign, formatRelativeTime) {
  if (!campaign) {
    return {
      label: "Website scan",
      status: "Action needed",
      tone: "warning",
      detail: "Add a business first so InsightOS can scan your website.",
      nextStep: "Set up your business to unlock the first scan.",
    };
  }

  if (!run) {
    return {
      label: "Website scan",
      status: "Action needed",
      tone: "warning",
      detail: "No website scan has run yet for the active business.",
      nextStep: "Run the first website scan from the dashboard.",
    };
  }

  if (isFailedStatus(run.status)) {
    return {
      label: "Website scan",
      status: "Needs attention",
      tone: "danger",
      detail: `The latest ${run.crawl_type || "website"} scan failed or stopped before finishing.`,
      nextStep: "Retry the website scan from the manual tools below.",
    };
  }

  if (isPendingStatus(run.status)) {
    return {
      label: "Website scan",
      status: "In progress",
      tone: "info",
      detail: `The latest ${run.crawl_type || "website"} scan is ${toTitleCase(run.status)}. Results may still be filling in.`,
      nextStep: "Wait for this scan to finish before treating the latest numbers as complete.",
    };
  }

  return {
    label: "Website scan",
    status: "Complete",
    tone: "success",
    detail: `The latest ${run.crawl_type || "website"} scan completed ${formatRelativeTime(run.updated_at || run.created_at)}.`,
    nextStep: "Use the latest scan as the baseline for rankings, reports, and follow-up actions.",
  };
}

function getRankingWorkflowState(campaign, trends, topKeyword, truth) {
  if (!campaign) {
    return {
      label: "Search tracking",
      status: "Action needed",
      tone: "warning",
      detail: "Search tracking starts after a business is set up.",
      nextStep: "Complete setup first, then add a search term.",
    };
  }

  if (!topKeyword) {
    return {
      label: "Search tracking",
      status: "Action needed",
      tone: "warning",
      detail: "No tracked search term has produced a ranking snapshot yet.",
      nextStep: "Add a search term and run the first ranking check.",
    };
  }

  if (truth?.classification === "unavailable") {
    return {
      label: "Search tracking",
      status: "Needs attention",
      tone: "danger",
      detail: truth.summary || "Ranking coverage is not reliably available in this runtime.",
      nextStep: "Fix provider setup and run a fresh ranking check before treating stored positions as current.",
    };
  }

  if (truth?.classification === "synthetic") {
    return {
      label: "Search tracking",
      status: "Test-only",
      tone: "warning",
      detail: truth.summary || "The current ranking data is synthetic test data.",
      nextStep: "Do not treat these positions as live market intelligence.",
    };
  }

  if (truth?.freshness_state === "stale") {
    return {
      label: "Search tracking",
      status: "Stale",
      tone: "warning",
      detail: truth.summary || "Stored ranking snapshots exist, but they are not fresh enough to read as current movement.",
      nextStep: "Run a fresh ranking check before acting on gains or drops.",
    };
  }

  return {
    label: "Search tracking",
    status: "Snapshots available",
    tone: truth?.classification === "provider_backed" ? "success" : "info",
    detail: `${trends.length} tracked search${trends.length === 1 ? "" : "es"} available. "${topKeyword.keyword || "Top keyword"}" is the latest leading term, but stored rows should only be treated as live when provider truth is current.`,
    nextStep: "Open the Rankings page to confirm provider quality and snapshot freshness before acting on movement.",
  };
}

function hasTruthState(truth, state) {
  return Array.isArray(truth?.states) && truth.states.includes(state);
}

function getReportWorkflowState(report, campaign, truth) {
  if (!campaign) {
    return {
      label: "Reports",
      status: "Action needed",
      tone: "warning",
      detail: "Reports become available after a business is set up and initial checks have run.",
      nextStep: "Finish setup first, then create the first report.",
    };
  }

  if (!report) {
    return {
      label: "Reports",
      status: "Action needed",
      tone: "warning",
      detail: "No report has been created yet for the active business.",
      nextStep: "Create the first report after your scan and rankings are ready.",
    };
  }

  if (hasTruthState(truth, "delivery_unverified") && report.report_status === "delivered") {
    return {
      label: "Reports",
      status: "Delivery unverified",
      tone: "warning",
      detail: `Month ${report.month_number || "current"} is marked delivered, but this runtime does not verify external delivery.`,
      nextStep: "Open the Reports page and confirm receipt outside the product before treating it as complete.",
    };
  }

  if (report.report_status === "delivered") {
    return {
      label: "Reports",
      status: "Complete",
      tone: "success",
      detail: `Month ${report.month_number || "current"} was delivered and is your latest shared summary.`,
      nextStep: "Run fresh checks before creating the next update.",
    };
  }

  if (report.report_status === "generated") {
    return {
      label: "Reports",
      status: hasTruthState(truth, "minimal_artifact") || hasTruthState(truth, "non_durable") ? "Preview only" : "Action needed",
      tone: "warning",
      detail:
        hasTruthState(truth, "minimal_artifact") || hasTruthState(truth, "non_durable")
          ? `Month ${report.month_number || "current"} was generated as a minimal local artifact and still needs review before any send.`
          : `Month ${report.month_number || "current"} is ready to review, but it has not been sent yet.`,
      nextStep:
        hasTruthState(truth, "minimal_artifact") || hasTruthState(truth, "non_durable")
          ? "Open the Reports page to review the local artifact before deciding whether to send it."
          : "Review the report and send it when you are ready to share progress.",
    };
  }

  if (isFailedStatus(report.report_status)) {
    return {
      label: "Reports",
      status: "Needs attention",
      tone: "danger",
      detail: `The latest report ended in a ${toTitleCase(report.report_status)} state.`,
      nextStep: "Open report controls to retry generation or confirm what happened.",
    };
  }

  if (isPendingStatus(report.report_status)) {
    return {
      label: "Reports",
      status: "In progress",
      tone: "info",
      detail: `Month ${report.month_number || "current"} is ${toTitleCase(report.report_status)}. The latest summary is still being prepared.`,
      nextStep: "Wait for the report to finish before treating it as ready to send.",
    };
  }

  return {
    label: "Reports",
    status: toTitleCase(report.report_status),
    tone: "info",
    detail: `Month ${report.month_number || "current"} is currently ${toTitleCase(report.report_status)}.`,
    nextStep: "Open the Reports page to confirm whether any follow-up is needed.",
  };
}

export {
  getCrawlWorkflowState,
  getRankingWorkflowState,
  getReportWorkflowState,
  getSetupWorkflowState,
  isFailedStatus,
  isPendingStatus,
};
