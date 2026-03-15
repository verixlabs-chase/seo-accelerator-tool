function getRecommendationStateSummary(status) {
  if (status === "GENERATED") {
    return {
      label: "Recommended",
      status: "Recommended",
      detail: "InsightOS is recommending this action, but nobody has reviewed it yet.",
      nextStep: "Review the rationale and mark it as reviewed if it should stay active.",
      tone: "warning",
    };
  }
  if (status === "VALIDATED") {
    return {
      label: "Reviewed",
      status: "Reviewed",
      detail: "This recommendation has been reviewed and kept in the active queue.",
      nextStep: "Choose it as the next action if you want execution planning to move forward.",
      tone: "info",
    };
  }
  if (status === "APPROVED") {
    return {
      label: "Chosen next",
      status: "Chosen next",
      detail: "This recommendation has been selected as the next action, but it has not been queued for execution yet.",
      nextStep: "Queue it for follow-up when you want the execution side to pick it up.",
      tone: "info",
    };
  }
  if (status === "SCHEDULED") {
    return {
      label: "Queued",
      status: "Queued",
      detail: "This recommendation has moved past planning and is now waiting in the follow-up queue.",
      nextStep: "Monitor the execution inbox to see when the linked execution is approved, run, or blocked.",
      tone: "success",
    };
  }
  if (status === "FAILED") {
    return {
      label: "Needs review",
      status: "Needs review",
      detail: "This recommendation hit a failure state and should not be treated as ready to move forward.",
      nextStep: "Review the linked execution state or clear it from the active queue if it is no longer relevant.",
      tone: "danger",
    };
  }
  if (status === "ARCHIVED") {
    return {
      label: "Cleared",
      status: "Cleared",
      detail: "This recommendation was intentionally removed from the active queue.",
      nextStep: "Return to the active queue if you want to work on something else.",
      tone: "success",
    };
  }

  return {
    label: status || "Unknown",
    status: status || "Unknown",
    detail: "Review the current state before moving this recommendation forward.",
    nextStep: "Use the controls below only after you are comfortable with the evidence.",
    tone: "warning",
  };
}

function getExecutionStateSummary(execution, helpers) {
  const { getMutationCount, canRollbackExecution } = helpers;

  if (execution.status === "pending") {
    return {
      label: "Awaiting approval",
      status: "Awaiting approval",
      detail: "This execution exists, but it cannot run until an operator approves it or rejects it.",
      nextStep: "Approve it to keep it moving, or reject it if it should not run.",
      tone: "warning",
    };
  }
  if (execution.status === "scheduled") {
    return {
      label: "Queued to run",
      status: "Queued to run",
      detail: "This execution is approved and waiting in the queue. It has not completed yet.",
      nextStep: "Use dry run or run now when you are ready, or cancel it before execution.",
      tone: "info",
    };
  }
  if (execution.status === "running") {
    return {
      label: "Running",
      status: "Running",
      detail: "This execution is currently in progress and should not be treated as complete yet.",
      nextStep: "Wait for completion or failure before making a follow-up decision.",
      tone: "info",
    };
  }
  if (execution.status === "completed") {
    const mutationCount = getMutationCount(execution);
    return {
      label: "Completed",
      status: "Completed",
      detail:
        mutationCount > 0
          ? `This execution completed and recorded ${mutationCount} tracked change${mutationCount === 1 ? "" : "s"}.`
          : "This execution completed, but no tracked mutations were recorded.",
      nextStep: canRollbackExecution(execution)
        ? "Review the result carefully and use rollback if the recorded changes need to be reversed."
        : "Review the result summary and timeline to confirm the outcome you expected.",
      tone: "success",
    };
  }
  if (execution.status === "failed") {
    return {
      label: execution.last_error === "manual_rejection" ? "Rejected" : "Failed",
      status: execution.last_error === "manual_rejection" ? "Rejected" : "Failed",
      detail:
        execution.last_error === "manual_rejection"
          ? "This execution was manually rejected and removed from the pending path."
          : `This execution did not complete successfully${execution.last_error ? `: ${execution.last_error.replace(/_/g, " ")}` : "."}`,
      nextStep:
        execution.last_error === "manual_rejection"
          ? "Review the recommendation and decide whether it should stay active or be cleared."
          : "Review the error, fix any blocked setup, then retry when it is safe to do so.",
      tone: "danger",
    };
  }
  if (execution.status === "rolled_back") {
    return {
      label: "Rolled back",
      status: "Rolled back",
      detail: "This execution ran earlier, but its tracked changes were reversed.",
      nextStep: "Review the timeline and result summary before deciding whether to retry or leave it reversed.",
      tone: "warning",
    };
  }

  return {
    label: execution.status || "Unknown",
    status: execution.status || "Unknown",
    detail: "Review the execution timeline for the latest recorded outcome.",
    nextStep: "Use the controls below only after confirming the current state.",
    tone: "warning",
  };
}

function getSetupBlockerSummary(execution, wordpressSetup, liveExecutionDisabledReason, requiresWordPressSetup) {
  if (!execution) {
    return {
      label: "Execution setup",
      status: "Action needed",
      tone: "warning",
      detail: "Select an execution first to review whether anything is blocking live delivery.",
      nextStep: "Choose an execution from the inbox.",
    };
  }

  if (!requiresWordPressSetup(execution.execution_type)) {
    return {
      label: "Execution setup",
      status: "Ready",
      tone: "success",
      detail: "This execution does not depend on WordPress setup gating.",
      nextStep: "Use the execution controls below when you are ready.",
    };
  }

  if (liveExecutionDisabledReason) {
    return {
      label: "Execution setup",
      status: "Blocked",
      tone: "danger",
      detail: liveExecutionDisabledReason,
      nextStep: wordpressSetup?.missing_requirements?.length
        ? "Resolve the missing setup requirements shown below before running this live."
        : "Resolve the setup blocker before attempting a live run.",
    };
  }

  return {
    label: "Execution setup",
    status: "Ready",
    tone: "success",
    detail: "The current execution has the required setup for live delivery.",
    nextStep: "Use dry run first if you want a preview before running it live.",
  };
}

export {
  getExecutionStateSummary,
  getRecommendationStateSummary,
  getSetupBlockerSummary,
};
