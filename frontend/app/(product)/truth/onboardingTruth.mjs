function summarizeTaskCounts(tasks) {
  const completedTasks = tasks.filter((task) => task.status === "done").length;
  const runningTasks = tasks.filter((task) => task.status === "running").length;
  const failedTasks = tasks.filter((task) => task.status === "error").length;
  const queuedTasks = tasks.filter((task) => task.status === "pending").length;
  const hasSetupIssues = failedTasks > 0;
  const hasStartedBackgroundChecks = tasks.some(
    (task) => task.id !== "campaign" && task.status !== "pending",
  );

  return {
    completedTasks,
    runningTasks,
    failedTasks,
    queuedTasks,
    hasSetupIssues,
    hasStartedBackgroundChecks,
  };
}

function parseOwnerServices(value) {
  const seen = new Set();
  return String(value || "")
    .split(/[\n;]+/)
    .map((item) => item.trim().replace(/\s+/g, " "))
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

function parseOwnerServiceAreas(value) {
  const seen = new Set();
  const entries = [];

  for (const rawItem of String(value || "").split(/[\n;]+/)) {
    const item = rawItem.trim().replace(/\s+/g, " ");
    if (!item) {
      continue;
    }

    const postalCode = /^\d{5}(?:-\d{4})?$/.test(item);
    const parts = item.split(",").map((part) => part.trim()).filter(Boolean);
    const name = postalCode ? item : parts[0];
    const region = postalCode ? null : parts.slice(1).join(", ") || null;
    const areaType = postalCode
      ? "postal_code"
      : /\bcounty$/i.test(name)
        ? "county"
        : "city";
    const key = `${areaType}:${name.toLocaleLowerCase()}:${(region || "").toLocaleLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    entries.push({ areaType, name, region });
  }

  return entries;
}

function getTaskStatusMeaning(status) {
  if (status === "done") {
    return "Complete. This part of setup finished.";
  }
  if (status === "running") {
    return "In progress. InsightOS is working on this now.";
  }
  if (status === "error") {
    return "Needs attention. This step did not finish successfully.";
  }
  return "Queued. This step will start automatically during setup.";
}

function getStepThreeSummary(tasks, scanDone) {
  const counts = summarizeTaskCounts(tasks);

  if (!scanDone) {
    return {
      title: "Setup is still in progress",
      body:
        counts.runningTasks > 0
          ? `InsightOS is actively starting ${counts.runningTasks} setup step${counts.runningTasks === 1 ? "" : "s"} right now.`
          : counts.queuedTasks > 0
            ? `${counts.queuedTasks} setup step${counts.queuedTasks === 1 ? "" : "s"} are queued to start next.`
            : "InsightOS is still preparing your first checks.",
      next: "Stay on this screen until the setup summary below updates.",
    };
  }

  if (counts.hasSetupIssues) {
    return {
      title: "Setup finished with issues",
      body: `${counts.completedTasks} of ${tasks.length} setup steps finished. ${counts.failedTasks} need${counts.failedTasks === 1 ? "s" : ""} attention before your first results are fully underway.`,
      next: "Go to the dashboard, review the workflow status, and retry the steps that need attention.",
    };
  }

  return {
    title: "Setup finished successfully",
    body: `${counts.completedTasks} of ${tasks.length} setup steps finished. Your business is saved and the first checks are now running in the background.`,
    next: "Open the dashboard to watch the first scan, rankings, and report workflow fill in.",
  };
}

export {
  getStepThreeSummary,
  getTaskStatusMeaning,
  parseOwnerServiceAreas,
  parseOwnerServices,
  summarizeTaskCounts,
};
