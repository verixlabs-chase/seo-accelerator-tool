export function getConnectionStatusView(connection) {
  const status = String(connection?.status || "connected").toLowerCase();
  if (status === "current") {
    return {
      label: "Up to date",
      tone: "success",
      summary: "Automatic Search Console data is available for this location.",
      action: "Check now",
    };
  }
  if (status === "syncing") {
    return {
      label: "Syncing",
      tone: "info",
      summary: "The latest Search Console data is being collected.",
      action: "Sync in progress",
    };
  }
  if (status === "stale") {
    return {
      label: "Needs an update",
      tone: "warning",
      summary: "The saved Search Console data is older than expected.",
      action: "Check now",
    };
  }
  if (status === "reconnect_required") {
    return {
      label: "Reconnect Google",
      tone: "danger",
      summary: "Google access expired or was removed. Reconnect before syncing again.",
      action: "Reconnect Google",
    };
  }
  if (status === "failed") {
    return {
      label: "Needs attention",
      tone: "danger",
      summary: "The last automatic update did not finish. The saved data is still available.",
      action: "Try again",
    };
  }
  if (status === "disconnected") {
    return {
      label: "Disconnected",
      tone: "warning",
      summary: "Automatic Search Console updates are turned off for this location.",
      action: "Connect",
    };
  }
  return {
    label: "Ready for first sync",
    tone: "info",
    summary: "The website is mapped and ready to collect its first Search Console history.",
    action: "Start first sync",
  };
}

export function getConnectionPortfolioSummary(connections, campaignCount) {
  const rows = Array.isArray(connections) ? connections : [];
  const current = rows.filter((item) => getConnectionStatusView(item).tone === "success").length;
  const needsAttention = rows.filter((item) =>
    ["warning", "danger"].includes(getConnectionStatusView(item).tone),
  ).length;
  const unmapped = Math.max(0, Number(campaignCount || 0) - rows.length);

  if (rows.length === 0) {
    return {
      label: "Not connected",
      tone: "warning",
      summary: "Connect Google, then match each location to its Search Console website.",
      current,
      needsAttention,
      unmapped,
    };
  }
  if (needsAttention > 0 || unmapped > 0) {
    return {
      label: "Setup needs attention",
      tone: "warning",
      summary: `${needsAttention} connection${needsAttention === 1 ? "" : "s"} need attention and ${unmapped} location${unmapped === 1 ? "" : "s"} still need a website mapping.`,
      current,
      needsAttention,
      unmapped,
    };
  }
  return {
    label: "Connected",
    tone: "success",
    summary: `${current} location${current === 1 ? "" : "s"} are receiving automatic Search Console data.`,
    current,
    needsAttention,
    unmapped,
  };
}
