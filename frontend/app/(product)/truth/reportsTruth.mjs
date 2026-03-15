function toTitleCase(value) {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function isFailedStatus(value) {
  return ["failed", "error", "cancelled", "canceled", "max_retries_exceeded"].includes(
    (value || "").toLowerCase(),
  );
}

function isPendingStatus(value) {
  return ["queued", "pending", "running", "in_progress", "scheduled", "processing", "retry_pending"].includes(
    (value || "").toLowerCase(),
  );
}

function getReportWorkflowState(report, campaign) {
  if (!campaign) {
    return {
      label: "Report generation",
      status: "Action needed",
      tone: "warning",
      detail: "Set up a business first so InsightOS can package results into a report.",
      nextStep: "Go back to the dashboard and finish setup.",
    };
  }

  if (!report) {
    return {
      label: "Report generation",
      status: "Action needed",
      tone: "warning",
      detail: "No report has been generated yet for the active business.",
      nextStep: "Generate the first report once scan and ranking data are available.",
    };
  }

  if (report.report_status === "delivered") {
    return {
      label: "Report generation",
      status: "Complete",
      tone: "success",
      detail: `Month ${report.month_number} is complete and has already been delivered.`,
      nextStep: "Generate the next report when you are ready to share another update.",
    };
  }

  if (report.report_status === "generated") {
    return {
      label: "Report generation",
      status: "Ready to send",
      tone: "warning",
      detail: `Month ${report.month_number} is built and ready for review, but it has not been delivered yet.`,
      nextStep: "Review the preview, confirm the recipient, and send it when ready.",
    };
  }

  if (isFailedStatus(report.report_status)) {
    return {
      label: "Report generation",
      status: "Needs attention",
      tone: "danger",
      detail: `Month ${report.month_number} ended in a ${toTitleCase(report.report_status)} state.`,
      nextStep: "Generate the report again after confirming the latest data is ready.",
    };
  }

  if (isPendingStatus(report.report_status)) {
    return {
      label: "Report generation",
      status: "In progress",
      tone: "info",
      detail: `Month ${report.month_number} is ${toTitleCase(report.report_status)} and should not be treated as complete yet.`,
      nextStep: "Wait for generation to finish, then review the final report before sending it.",
    };
  }

  return {
    label: "Report generation",
    status: toTitleCase(report.report_status),
    tone: "info",
    detail: `Month ${report.month_number} is currently ${toTitleCase(report.report_status)}.`,
    nextStep: "Review the report detail before taking the next step.",
  };
}

function getDeliveryWorkflowState(detail, report) {
  const latestEvent = detail?.delivery_events?.[0] || null;

  if (!report) {
    return {
      label: "Delivery",
      status: "Action needed",
      tone: "warning",
      detail: "There is no report selected to send yet.",
      nextStep: "Generate or select a report first.",
    };
  }

  if (!detail?.delivery_events?.length) {
    return {
      label: "Delivery",
      status: report.report_status === "delivered" ? "Complete" : "Action needed",
      tone: report.report_status === "delivered" ? "success" : "warning",
      detail:
        report.report_status === "delivered"
          ? "The report is marked as delivered, but no delivery event detail is available."
          : "No delivery has been recorded yet for the selected report.",
      nextStep:
        report.report_status === "delivered"
          ? "Use the delivery history below if future events appear."
          : "Confirm the recipient email, then send the selected report.",
    };
  }

  if (latestEvent?.delivery_status === "sent") {
    return {
      label: "Delivery",
      status: "Complete",
      tone: "success",
      detail: `The latest delivery to ${latestEvent.recipient} was sent successfully.`,
      nextStep: "Generate a new report when you want to share a newer update.",
    };
  }

  if (latestEvent?.delivery_status === "failed") {
    return {
      label: "Delivery",
      status: "Needs attention",
      tone: "danger",
      detail: `The latest delivery attempt to ${latestEvent.recipient} failed.`,
      nextStep: "Confirm the recipient address and retry sending the selected report.",
    };
  }

  if (isPendingStatus(latestEvent?.delivery_status)) {
    return {
      label: "Delivery",
      status: "In progress",
      tone: "info",
      detail: `The latest delivery to ${latestEvent.recipient} is queued and not confirmed as sent yet.`,
      nextStep: "Wait for the delivery event to finish before treating the report as delivered.",
    };
  }

  return {
    label: "Delivery",
    status: toTitleCase(latestEvent?.delivery_status),
    tone: "info",
    detail: `The latest delivery attempt to ${latestEvent?.recipient || "the selected recipient"} is ${toTitleCase(
      latestEvent?.delivery_status,
    ).toLowerCase()}.`,
    nextStep: "Check the delivery history below before deciding whether to resend.",
  };
}

function getScheduleWorkflowState(schedule, campaign, formatRelativeTime) {
  if (!campaign) {
    return {
      label: "Schedule",
      status: "Action needed",
      tone: "warning",
      detail: "Set up a business first before configuring recurring reports.",
      nextStep: "Finish setup, then return here to configure automation.",
    };
  }

  if (!schedule) {
    return {
      label: "Schedule",
      status: "Action needed",
      tone: "warning",
      detail: "No recurring report schedule has been created yet.",
      nextStep: "Create a schedule if you want reports generated automatically.",
    };
  }

  if (schedule.last_status === "scheduled") {
    return {
      label: "Schedule",
      status: "Active",
      tone: "success",
      detail: `Recurring reports are enabled and the next run is planned for ${schedule.next_run_at ? formatRelativeTime(schedule.next_run_at) : "the configured schedule"}.`,
      nextStep: "Review the next run time below if you need to change cadence or timezone.",
    };
  }

  if (schedule.last_status === "disabled") {
    return {
      label: "Schedule",
      status: "Paused",
      tone: "warning",
      detail: "Recurring report generation is turned off for the active business.",
      nextStep: "Enable the schedule below if you want reports to run automatically again.",
    };
  }

  if (schedule.last_status === "retry_pending") {
    return {
      label: "Schedule",
      status: "Retrying",
      tone: "info",
      detail: "The scheduler is retrying a recent run and should not be treated as stable yet.",
      nextStep: "Wait for the retry to finish, then confirm whether the schedule returns to Active.",
    };
  }

  if (schedule.last_status === "max_retries_exceeded") {
    return {
      label: "Schedule",
      status: "Needs attention",
      tone: "danger",
      detail: "The scheduler exhausted its retries and is not currently dependable.",
      nextStep: "Review the schedule settings below and re-save them after resolving the issue.",
    };
  }

  return {
    label: "Schedule",
    status: toTitleCase(schedule.last_status),
    tone: "info",
    detail: `The schedule is currently ${toTitleCase(schedule.last_status).toLowerCase()}.`,
    nextStep: "Review the settings below if this is not the state you expected.",
  };
}

export {
  getDeliveryWorkflowState,
  getReportWorkflowState,
  getScheduleWorkflowState,
  isFailedStatus,
  isPendingStatus,
};
