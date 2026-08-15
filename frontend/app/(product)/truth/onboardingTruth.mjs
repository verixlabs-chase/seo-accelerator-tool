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

function getTaskRecoveryGuidance(task) {
  const taskId = String(task?.id || "");
  const status = String(task?.status || "pending");

  if (status === "done") {
    return {
      owner: "No action needed",
      timing: "Finished",
      missing: null,
      recovery: "This step is complete.",
    };
  }
  if (status === "running") {
    return {
      owner: "InsightOS",
      timing: "Usually under 2 minutes to start",
      missing: null,
      recovery: "Keep this page open while the request finishes.",
    };
  }
  if (status === "pending") {
    return {
      owner: "InsightOS",
      timing: "Starts after the step above",
      missing: null,
      recovery: "Nothing is required from you yet.",
    };
  }

  const failures = {
    location: {
      missing: "Your business location was not saved.",
      recovery: "Check the business name and home market, then save again.",
    },
    campaign: {
      missing: "Your business workspace was not created.",
      recovery: "Check the website address, then save again.",
    },
    "business-profile": {
      missing: "Your services or work areas were not fully saved.",
      recovery: "Check the service and area lists, then save again.",
    },
    crawl: {
      missing: "The website scan did not start.",
      recovery: "Check the website address, then retry the unfinished checks.",
    },
    keyword: {
      missing: "The first search phrase was not saved.",
      recovery: "Confirm the main service and work area, then retry the unfinished checks.",
    },
    ranking: {
      missing: "The first Google position check did not start.",
      recovery: "Retry the unfinished checks. If it fails again, contact support.",
    },
    baseline: {
      missing: "The first website scan has not produced enough evidence to freeze the baseline report.",
      recovery: "Retry the website scan, then retry the baseline analysis. Existing saved work will not be changed.",
    },
  };
  const failure = failures[taskId] || {
    missing: "This setup step did not finish.",
    recovery: "Try this step again. If it still fails, contact support.",
  };

  return {
    owner: "You",
    timing: "About 2 minutes after retrying",
    ...failure,
  };
}

function getStepThreeSummary(tasks, scanDone) {
  const counts = summarizeTaskCounts(tasks);
  const includesBaseline = tasks.some((task) => task.id === "baseline");

  if (scanDone && counts.hasSetupIssues) {
    return {
      title: "Setup finished with issues",
      body: `${counts.completedTasks} of ${tasks.length} setup steps finished. ${counts.failedTasks} need${counts.failedTasks === 1 ? "s" : ""} attention before your first results are fully underway.`,
      next: includesBaseline
        ? "Review the marked step and retry it. Your dashboard and existing saved work remain available."
        : "Go to the dashboard, review the workflow status, and retry the steps that need attention.",
    };
  }

  if (!scanDone || counts.runningTasks > 0 || counts.queuedTasks > 0) {
    return {
      title: includesBaseline
        ? "Setup and baseline analysis are still in progress"
        : "Setup is still in progress",
      body:
        counts.runningTasks > 0
          ? `InsightOS is actively working on ${counts.runningTasks} setup step${counts.runningTasks === 1 ? "" : "s"}, including the mandatory first diagnosis.`
          : counts.queuedTasks > 0
            ? `${counts.queuedTasks} setup step${counts.queuedTasks === 1 ? "" : "s"} are queued to start next.`
            : "InsightOS is still preparing your first checks.",
      next: includesBaseline
        ? "You can stay here, or open the dashboard while the first website scan and baseline report finish."
        : "Stay on this screen until the setup summary below updates.",
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
  getTaskRecoveryGuidance,
  getTaskStatusMeaning,
  parseOwnerServiceAreas,
  parseOwnerServices,
  summarizeTaskCounts,
};
