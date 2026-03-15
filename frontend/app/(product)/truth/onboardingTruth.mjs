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

export { getStepThreeSummary, getTaskStatusMeaning, summarizeTaskCounts };
