const STORAGE_VERSION = 1;
const MAX_PROGRESS_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const VALID_TASK_STATUSES = new Set(["pending", "running", "done", "error"]);

function getOnboardingProgressKey(organizationId) {
  return `insightos:onboarding-progress:${String(organizationId || "").trim()}`;
}

function normalizeTask(task) {
  if (!task || typeof task !== "object" || typeof task.id !== "string") {
    return null;
  }
  const status = VALID_TASK_STATUSES.has(task.status) ? task.status : "pending";
  return {
    id: task.id,
    title: typeof task.title === "string" ? task.title : "Setup step",
    description: typeof task.description === "string" ? task.description : "",
    // A navigation can interrupt the response that would mark a request done.
    // Do not claim success; let the owner retry only the interrupted work.
    status: status === "running" ? "error" : status,
  };
}

function normalizeOnboardingProgress(value, organizationId, now = Date.now()) {
  if (!value || typeof value !== "object") return null;
  if (value.version !== STORAGE_VERSION) return null;
  if (value.organizationId !== organizationId) return null;
  if (!Number.isFinite(value.savedAt) || now - value.savedAt > MAX_PROGRESS_AGE_MS) {
    return null;
  }

  const tasks = Array.isArray(value.setupTasks)
    ? value.setupTasks.map(normalizeTask).filter(Boolean)
    : [];
  const step = [1, 2, 3].includes(value.step) ? value.step : 1;
  const backgroundTasks = tasks.filter((task) =>
    ["crawl", "keyword", "ranking"].includes(task.id),
  );
  const backgroundWorkStarted = backgroundTasks.some((task) => task.status !== "pending");

  return {
    version: STORAGE_VERSION,
    organizationId,
    savedAt: value.savedAt,
    step,
    businessName: typeof value.businessName === "string" ? value.businessName : "",
    websiteUrl: typeof value.websiteUrl === "string" ? value.websiteUrl : "",
    businessLocationId:
      typeof value.businessLocationId === "string" ? value.businessLocationId : "",
    campaignId: typeof value.campaignId === "string" ? value.campaignId : "",
    campaignDomain:
      typeof value.campaignDomain === "string" ? value.campaignDomain : "",
    servicesInput: typeof value.servicesInput === "string" ? value.servicesInput : "",
    serviceAreasInput:
      typeof value.serviceAreasInput === "string" ? value.serviceAreasInput : "",
    primaryService:
      typeof value.primaryService === "string" ? value.primaryService : "",
    rankingArea: typeof value.rankingArea === "string" ? value.rankingArea : "",
    setupTasks: tasks,
    scanStarted: step === 3 && backgroundWorkStarted,
    scanDone: step === 3 && (Boolean(value.scanDone) || backgroundWorkStarted),
  };
}

function loadOnboardingProgress(storage, organizationId, now = Date.now()) {
  if (!storage || !organizationId) return null;
  const key = getOnboardingProgressKey(organizationId);
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const normalized = normalizeOnboardingProgress(JSON.parse(raw), organizationId, now);
    if (!normalized) storage.removeItem(key);
    return normalized;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

function saveOnboardingProgress(storage, organizationId, progress, now = Date.now()) {
  if (!storage || !organizationId) return false;
  try {
    storage.setItem(
      getOnboardingProgressKey(organizationId),
      JSON.stringify({
        ...progress,
        version: STORAGE_VERSION,
        organizationId,
        savedAt: now,
      }),
    );
    return true;
  } catch {
    return false;
  }
}

function clearOnboardingProgress(storage, organizationId) {
  if (!storage || !organizationId) return;
  try {
    storage.removeItem(getOnboardingProgressKey(organizationId));
  } catch {
    // Setup remains usable when a privacy-restricted browser blocks storage.
  }
}

function hasOnboardingProgress(storage, organizationId, now = Date.now()) {
  return Boolean(loadOnboardingProgress(storage, organizationId, now));
}

export {
  MAX_PROGRESS_AGE_MS,
  clearOnboardingProgress,
  getOnboardingProgressKey,
  hasOnboardingProgress,
  loadOnboardingProgress,
  normalizeOnboardingProgress,
  saveOnboardingProgress,
};
