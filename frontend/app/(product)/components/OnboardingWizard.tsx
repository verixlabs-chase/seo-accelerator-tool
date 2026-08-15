"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { PlatformApiError, platformApi } from "../../platform/api";
import { getTenantId } from "../../lib/authStorage";
import { trackProductEvent } from "../../lib/productAnalytics";
import {
  getStepThreeSummary,
  getTaskRecoveryGuidance,
  getTaskStatusMeaning,
  parseOwnerServiceAreas,
  parseOwnerServices,
  summarizeTaskCounts,
} from "../truth/onboardingTruth.mjs";
import {
  clearOnboardingProgress,
  loadOnboardingProgress,
  saveOnboardingProgress,
} from "../truth/onboardingProgress.mjs";
import { PRODUCT_TOUR_EVENT, requestProductTour } from "../truth/productTour.mjs";
import {
  PlanGateNotice,
  canActivateAnotherLocation,
  isLocationAllowanceEnforced,
  locationUsageLabel,
  type LocationAllowanceSummary,
} from "./PlanGateNotice";

type OnboardingCompletion = {
  campaignId: string;
  campaignDomain: string;
  notice: string;
};

type OnboardingWizardProps = {
  organizationId: string;
  orgRole?: string | null;
  onComplete: (payload: OnboardingCompletion) => void;
};

type ExistingBusinessLocation = {
  id: string;
  name: string;
  domain?: string | null;
  status: string;
  city?: string | null;
  primary_city?: string | null;
  region?: string | null;
};

type ServiceAreaEntry = {
  areaType: "city" | "postal_code" | "county";
  name: string;
  region: string | null;
};

type StepIndicatorProps = {
  currentStep: number;
  steps: string[];
};

function StepIndicator({ currentStep, steps }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-2">
      {steps.map((label, index) => {
        const stepNum = index + 1;
        const isActive = stepNum === currentStep;
        const isDone = stepNum < currentStep;
        return (
          <div key={label} className="flex items-center gap-2">
            {index > 0 && (
              <div
                className={`h-px w-6 ${isDone ? "bg-accent-500" : "bg-[#26272c]"}`}
              />
            )}
            <div className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  isActive
                    ? "border border-accent-500 bg-accent-500/20 text-accent-500"
                    : isDone
                      ? "bg-accent-500 text-white"
                      : "border border-[#26272c] bg-[#141518] text-zinc-500"
                }`}
              >
                {isDone ? "\u2713" : stepNum}
              </span>
              <span
                className={`text-sm ${isActive ? "font-medium text-white" : "text-zinc-500"}`}
              >
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

type SetupTask = {
  id: string;
  title: string;
  description: string;
  status: "pending" | "running" | "done" | "error";
};

type BackgroundSetupTaskId = "crawl" | "keyword" | "ranking";

type BaselineStatus = {
  state: "collecting" | "blocked" | "ready" | "limited" | "ready_to_generate";
  completion_satisfied: boolean;
  message: string;
  baseline?: {
    report_id: string;
    status: "ready" | "limited";
    scores: { overall?: number | null };
    diagnosis: { headline?: string; summary?: string };
  } | null;
};

const DEFAULT_SETUP_TASKS: SetupTask[] = [
  {
    id: "location",
    title: "Create your business location",
    description: "Keep this location's services, markets, and results separate.",
    status: "pending",
  },
  {
    id: "campaign",
    title: "Save your business profile",
    description: "Create the workspace for your business inside InsightOS.",
    status: "pending",
  },
  {
    id: "business-profile",
    title: "Save what you do and where you work",
    description: "Use your confirmed services and service areas to keep search ideas relevant.",
    status: "pending",
  },
  {
    id: "crawl",
    title: "Start your website scan",
    description: "Queue the first technical scan so the dashboard has website health data.",
    status: "pending",
  },
  {
    id: "keyword",
    title: "Add a starter search term",
    description: "Create the first tracked search so visibility can be measured.",
    status: "pending",
  },
  {
    id: "ranking",
    title: "Run your first ranking check",
    description: "Queue the first ranking snapshot for your business area.",
    status: "pending",
  },
  {
    id: "baseline",
    title: "Create your baseline analysis and first diagnosis",
    description: "Freeze the first website, organic visibility, traffic, and performance evidence into a detailed report with scores and prioritized fixes.",
    status: "pending",
  },
];

function SetupTaskList({ tasks }: { tasks: SetupTask[] }) {
  return (
    <div className="space-y-3">
      {tasks.map((task) => {
        const guidance = getTaskRecoveryGuidance(task);
        const tone =
          task.status === "done"
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
            : task.status === "running"
              ? "border-accent-500/20 bg-accent-500/10 text-zinc-100"
              : task.status === "error"
                ? "border-rose-500/20 bg-rose-500/10 text-rose-100"
                : "border-[#26272c] bg-[#111214] text-zinc-300";

        const label =
          task.status === "done"
            ? "Done"
            : task.status === "running"
              ? "In progress"
              : task.status === "error"
                ? "Needs attention"
                : "Queued";

        return (
          <div key={task.id} className={`rounded-md border p-3 ${tone}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{task.title}</p>
                <p className="mt-1 text-sm opacity-80">{task.description}</p>
                <p className="mt-2 text-xs uppercase tracking-[0.14em] opacity-70">
                  {getTaskStatusMeaning(task.status)}
                </p>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs opacity-80">
                  <span>Who acts: {guidance.owner}</span>
                  <span>Timing: {guidance.timing}</span>
                </div>
                {task.status === "error" && (
                  <div className="mt-3 border-t border-current/15 pt-3 text-sm leading-6">
                    <p><span className="font-semibold">What is missing:</span> {guidance.missing}</p>
                    <p><span className="font-semibold">How to recover:</span> {guidance.recovery}</p>
                  </div>
                )}
              </div>
              <span className="shrink-0 rounded-full border border-current/20 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]">
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function OnboardingWizard({ organizationId, orgRole, onComplete }: OnboardingWizardProps) {
  const router = useRouter();
  const [progressRestored, setProgressRestored] = useState(false);
  const [restoredNotice, setRestoredNotice] = useState("");
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [locationAllowance, setLocationAllowance] = useState<LocationAllowanceSummary | null>(null);
  const [locationContextLoading, setLocationContextLoading] = useState(true);
  const [locationContextError, setLocationContextError] = useState("");
  const [locationAllowanceDetail, setLocationAllowanceDetail] = useState("");
  const [existingLocations, setExistingLocations] = useState<ExistingBusinessLocation[]>([]);
  const [existingLocationsLoaded, setExistingLocationsLoaded] = useState(false);

  // Step 1 state
  const [businessName, setBusinessName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");

  // Step 1 result
  const [businessLocationId, setBusinessLocationId] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");

  // Step 2 state
  const [servicesInput, setServicesInput] = useState("");
  const [serviceAreasInput, setServiceAreasInput] = useState("");
  const [primaryService, setPrimaryService] = useState("");
  const [rankingArea, setRankingArea] = useState("");

  // Step 3 state
  const [scanStarted, setScanStarted] = useState(false);
  const [scanDone, setScanDone] = useState(false);
  const [setupTasks, setSetupTasks] = useState<SetupTask[]>(DEFAULT_SETUP_TASKS);
  const [baselineStatus, setBaselineStatus] = useState<BaselineStatus | null>(null);
  const baselineRequestActive = useRef(false);

  useEffect(() => {
    if (!organizationId) return;
    const saved = loadOnboardingProgress(window.localStorage, organizationId);
    if (saved) {
      setStep(saved.step);
      setBusinessName(saved.businessName);
      setWebsiteUrl(saved.websiteUrl);
      setBusinessLocationId(saved.businessLocationId);
      setCampaignId(saved.campaignId);
      setCampaignDomain(saved.campaignDomain);
      setServicesInput(saved.servicesInput);
      setServiceAreasInput(saved.serviceAreasInput);
      setPrimaryService(saved.primaryService);
      setRankingArea(saved.rankingArea);
      setSetupTasks(
        saved.setupTasks.length === DEFAULT_SETUP_TASKS.length
          ? saved.setupTasks
          : DEFAULT_SETUP_TASKS,
      );
      setScanStarted(saved.scanStarted);
      setScanDone(saved.scanDone);
      setRestoredNotice(
        saved.step === 3
          ? "Your setup progress was restored. Completed work is still marked complete, and any interrupted check can be retried without starting over."
          : "Your setup answers were restored. Continue where you left off.",
      );
    }
    setProgressRestored(true);
  }, [organizationId]);

  useEffect(() => {
    if (!progressRestored || !organizationId) return;
    saveOnboardingProgress(window.localStorage, organizationId, {
      step,
      businessName,
      websiteUrl,
      businessLocationId,
      campaignId,
      campaignDomain,
      servicesInput,
      serviceAreasInput,
      primaryService,
      rankingArea,
      setupTasks,
      scanStarted,
      scanDone,
    });
  }, [
    businessLocationId,
    businessName,
    campaignDomain,
    campaignId,
    organizationId,
    primaryService,
    progressRestored,
    rankingArea,
    scanDone,
    scanStarted,
    serviceAreasInput,
    servicesInput,
    setupTasks,
    step,
    websiteUrl,
  ]);

  const updateTask = useCallback((taskId: string, status: SetupTask["status"]) => {
    setSetupTasks((current) =>
      current.map((task) => (task.id === taskId ? { ...task, status } : task)),
    );
  }, []);

  const refreshBaseline = useCallback(async () => {
    if (!campaignId || baselineRequestActive.current) return;
    baselineRequestActive.current = true;
    updateTask("baseline", "running");
    try {
      const result = (await platformApi(
        `/onboarding/baseline/${encodeURIComponent(campaignId)}`,
        { method: "POST" },
      )) as BaselineStatus;
      setBaselineStatus(result);
      if (result.completion_satisfied && result.baseline) {
        updateTask("baseline", "done");
      } else if (result.state === "blocked") {
        updateTask("baseline", "error");
      } else {
        updateTask("baseline", "running");
      }
    } catch (err) {
      setBaselineStatus({
        state: "blocked",
        completion_satisfied: false,
        message: err instanceof Error ? err.message : "The baseline analysis could not be checked.",
        baseline: null,
      });
      updateTask("baseline", "error");
    } finally {
      baselineRequestActive.current = false;
    }
  }, [campaignId, updateTask]);

  const loadLocationContext = useCallback(async () => {
    if (!organizationId) return;
    setLocationContextLoading(true);
    setLocationContextError("");
    const [allowanceResult, locationsResult] = await Promise.allSettled([
      platformApi("/usage/credits", { method: "GET" }) as Promise<LocationAllowanceSummary>,
      platformApi(
        `/organizations/${encodeURIComponent(organizationId)}/business-locations`,
        { method: "GET" },
      ) as Promise<{ items?: ExistingBusinessLocation[] }>,
    ]);

    if (allowanceResult.status === "fulfilled") {
      setLocationAllowance(allowanceResult.value);
    } else {
      setLocationAllowance(null);
    }

    if (locationsResult.status === "fulfilled") {
      const activeLocations = (locationsResult.value?.items || []).filter(
        (item) => item.status === "active",
      );
      setExistingLocations(activeLocations);
      setExistingLocationsLoaded(true);
      if (activeLocations.length === 1) {
        const recovered = activeLocations[0];
        setBusinessLocationId((current) => current || recovered.id);
        setBusinessName((current) => current || recovered.name);
        setWebsiteUrl((current) => current || recovered.domain || "");
        setSetupTasks((current) =>
          current.map((task) =>
            task.id === "location" ? { ...task, status: "done" } : task,
          ),
        );
        setRestoredNotice((current) =>
          current || `We found ${recovered.name}, which was saved during an earlier setup. Continue here instead of creating it again.`,
        );
      }
    } else {
      setExistingLocations([]);
      setExistingLocationsLoaded(false);
    }

    if (
      allowanceResult.status === "rejected" ||
      locationsResult.status === "rejected"
    ) {
      setLocationContextError(
        "We could not confirm your saved locations and plan allowance. Nothing already saved was changed. Check again before adding a new location.",
      );
    }
    setLocationContextLoading(false);
  }, [organizationId]);

  useEffect(() => {
    if (!progressRestored || !organizationId) return;
    void loadLocationContext();
  }, [loadLocationContext, organizationId, progressRestored]);

  function chooseExistingLocation(locationId: string) {
    const location = existingLocations.find((item) => item.id === locationId);
    setBusinessLocationId(locationId);
    setLocationAllowanceDetail("");
    if (location) {
      setBusinessName(location.name);
      setWebsiteUrl(location.domain || "");
      updateTask("location", "done");
      return;
    }
    updateTask("location", "pending");
  }

  const {
    completedTasks,
    runningTasks,
    failedTasks,
    queuedTasks,
    hasSetupIssues,
    hasStartedBackgroundChecks,
  } = summarizeTaskCounts(setupTasks);
  const stepThreeSummary = getStepThreeSummary(setupTasks, scanDone);
  const needsNewLocation = !businessLocationId;
  const canCreateLocation = Boolean(
    existingLocationsLoaded &&
    locationAllowance &&
    canActivateAnotherLocation(locationAllowance),
  );
  const newLocationCheckUnavailable = Boolean(
    locationContextLoading ||
    !existingLocationsLoaded ||
    !locationAllowance,
  );

  function handleStep1(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!businessName.trim() || !websiteUrl.trim()) {
      setError("Please enter your business name and website.");
      return;
    }
    if (needsNewLocation && !canCreateLocation) {
      setLocationAllowanceDetail(
        locationAllowance
          ? `Your ${locationAllowance.plan.name} plan has no open active-location slots. Nothing already saved was changed.`
          : "Check your saved locations and plan before adding a new location.",
      );
      return;
    }
    setError("");
    void trackProductEvent({
      eventName: "onboarding.started",
      properties: { entry_point: "workspace_setup" },
      idempotencyKey: `onboarding.started:${organizationId}`,
    });
    setStep(2);
  }

  async function handleStep2(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const services = parseOwnerServices(servicesInput) as string[];
    const serviceAreas = parseOwnerServiceAreas(serviceAreasInput) as ServiceAreaEntry[];
    if (services.length === 0) {
      setError("Add at least one service customers can hire you for.");
      return;
    }
    if (serviceAreas.length === 0) {
      setError("Add at least one city, county, or ZIP code you serve.");
      return;
    }
    if (!organizationId) {
      setError("Your organization could not be identified. Reload the page and try again.");
      return;
    }
    if (!businessLocationId && !canCreateLocation) {
      setLocationAllowanceDetail(
        locationAllowance
          ? `Your ${locationAllowance.plan.name} plan has no open active-location slots. Your setup answers are still here.`
          : "Your setup answers are still here. Check your saved locations and plan before adding a new location.",
      );
      return;
    }

    setBusy(true);
    setError("");
    const domain = websiteUrl.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
    const firstArea = serviceAreas[0];

    try {
      let activeLocationId = businessLocationId;
      if (!activeLocationId) {
        updateTask("location", "running");
        const createdLocation = await platformApi(
          `/organizations/${encodeURIComponent(organizationId)}/business-locations`,
          {
            method: "POST",
            body: JSON.stringify({
              name: businessName.trim(),
              domain,
              primary_city: firstArea.areaType === "postal_code" ? null : firstArea.name,
              city: firstArea.areaType === "city" ? firstArea.name : null,
              region: firstArea.region,
              postal_code: firstArea.areaType === "postal_code" ? firstArea.name : null,
              country_code: "US",
            }),
          },
        );
        activeLocationId = createdLocation?.business_location?.id || "";
        if (!activeLocationId) {
          throw new Error("We couldn't create this business location.");
        }
        setBusinessLocationId(activeLocationId);
        updateTask("location", "done");
        await loadLocationContext();
      }

      let activeCampaignId = campaignId;
      if (!activeCampaignId) {
        updateTask("campaign", "running");
        const createdCampaign = await platformApi("/campaigns", {
          method: "POST",
          body: JSON.stringify({
            name: businessName.trim(),
            domain,
            business_location_id: activeLocationId,
          }),
        });
        activeCampaignId = createdCampaign?.id || "";
        if (!activeCampaignId) {
          throw new Error("We couldn't create this business workspace.");
        }
        setCampaignId(activeCampaignId);
        setCampaignDomain(domain);
        updateTask("campaign", "done");
      }

      updateTask("business-profile", "running");
      for (const service of services) {
        await platformApi("/business-services", {
          method: "POST",
          body: JSON.stringify({ campaign_id: activeCampaignId, name: service }),
        });
      }
      for (const area of serviceAreas) {
        await platformApi("/business-service-areas", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: activeCampaignId,
            area_type: area.areaType,
            name: area.name,
            region: area.region,
            country_code: "US",
            relationship: "included",
          }),
        });
      }
      updateTask("business-profile", "done");
      setPrimaryService(services[0]);
      setRankingArea([firstArea.name, firstArea.region].filter(Boolean).join(", "));
      setStep(3);
    } catch (err) {
      if (
        err instanceof PlatformApiError &&
        err.reasonCode === "active_location_allowance_exhausted"
      ) {
        updateTask("location", "pending");
        setLocationAllowanceDetail(err.message);
        setError("");
        await loadLocationContext();
        return;
      }
      setSetupTasks((current) =>
        current.map((task) =>
          task.status === "running" ? { ...task, status: "error" } : task,
        ),
      );
      setError(
        err instanceof Error
          ? err.message
          : "We couldn't save your services and service areas. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const runFirstChecks = useCallback(
    async (taskIds: BackgroundSetupTaskId[]) => {
      setBusy(true);
      setError("");
      setScanDone(false);

      const seedUrl = campaignDomain.startsWith("http")
        ? campaignDomain
        : `https://${campaignDomain}`;
      const keyword = `${primaryService.toLowerCase()} near me`;
      const locationCode = rankingArea || "US";
      const requests: Record<BackgroundSetupTaskId, () => Promise<unknown>> = {
        crawl: () => platformApi("/crawl/schedule", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            crawl_type: "deep",
            seed_url: seedUrl,
          }),
        }),
        keyword: () => platformApi("/rank/keywords", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            cluster_name: primaryService || "Core Services",
            keyword,
            location_code: locationCode,
          }),
        }),
        ranking: () => platformApi("/rank/schedule", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            location_code: locationCode,
          }),
        }),
      };
      const failedTaskIds: BackgroundSetupTaskId[] = [];

      for (const taskId of taskIds) {
        updateTask(taskId, "running");
        try {
          await requests[taskId]();
          updateTask(taskId, "done");
        } catch {
          failedTaskIds.push(taskId);
          updateTask(taskId, "error");
        }
      }

      if (failedTaskIds.length > 0) {
        setError(
          `${failedTaskIds.length} first check${failedTaskIds.length === 1 ? "" : "s"} did not start. Review the marked step${failedTaskIds.length === 1 ? "" : "s"}, then use Retry unfinished checks.`,
        );
      }
      setScanDone(true);
      setBusy(false);
      void refreshBaseline();
    },
    [campaignDomain, campaignId, primaryService, rankingArea, refreshBaseline, updateTask],
  );

  // Step 3: fire scans on mount
  useEffect(() => {
    if (step !== 3 || scanStarted) return;
    setScanStarted(true);
    void runFirstChecks(["crawl", "keyword", "ranking"]);
  }, [step, scanStarted, runFirstChecks]);

  const baselineTaskStatus =
    setupTasks.find((task) => task.id === "baseline")?.status || "pending";
  const baselineComplete = baselineTaskStatus === "done";

  useEffect(() => {
    if (
      step === 3 &&
      scanDone &&
      campaignId &&
      !baselineComplete &&
      baselineStatus === null
    ) {
      void refreshBaseline();
    }
  }, [baselineComplete, baselineStatus, campaignId, refreshBaseline, scanDone, step]);

  useEffect(() => {
    if (
      step !== 3 ||
      !scanDone ||
      !campaignId ||
      baselineComplete ||
      baselineTaskStatus === "error"
    ) {
      return;
    }
    const timer = window.setInterval(() => void refreshBaseline(), 6000);
    return () => window.clearInterval(timer);
  }, [
    baselineComplete,
    baselineTaskStatus,
    campaignId,
    refreshBaseline,
    scanDone,
    step,
  ]);

  const retryableTaskIds = setupTasks
    .filter(
      (task): task is SetupTask & { id: BackgroundSetupTaskId } =>
        (["crawl", "keyword", "ranking"] as string[]).includes(task.id) &&
        (task.status === "error" || task.status === "pending"),
    )
    .map((task) => task.id);

  function finishSetup(destination: "dashboard" | "connections") {
    if (!baselineComplete) return;
    void trackProductEvent({
      eventName: "onboarding.completed",
      campaignId,
      properties: {
        result_status: hasSetupIssues ? "partial" : "success",
        next_destination: destination,
      },
      idempotencyKey: `onboarding.completed:${campaignId}`,
    });
    clearOnboardingProgress(window.localStorage, organizationId);
    if (destination === "dashboard" && !hasSetupIssues) {
      requestProductTour(window.localStorage, getTenantId() || organizationId);
      window.dispatchEvent(new CustomEvent(PRODUCT_TOUR_EVENT));
    }
    onComplete({
      campaignId,
      campaignDomain,
      notice: hasSetupIssues
        ? "Business setup finished, but one or more first checks need attention on the dashboard."
        : "Business setup finished. Your immutable baseline report and first diagnosis are ready.",
    });
    if (destination === "connections") {
      router.push(`/settings?setup=connections&campaign_id=${encodeURIComponent(campaignId)}`);
    }
  }

  function leaveWhileBaselineRuns() {
    onComplete({
      campaignId,
      campaignDomain,
      notice: "Your dashboard is available while the mandatory baseline finishes. Setup will reopen until the first diagnosis is ready.",
    });
  }

  return (
    <div className="mx-auto max-w-2xl py-8">
      <div className="rounded-md border border-[#26272c] bg-[#141518] p-7 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
        <div className="mb-7">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Guided setup
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            Set up your business
          </h2>
          <p className="mt-2.5 text-sm leading-6 text-zinc-300">
            We&apos;ll save your business, run the first checks, and create a mandatory baseline report with your starting issues, organic metrics, score explanations, diagnosis, and prioritized fixes.
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">
            Your non-sensitive setup progress is saved on this device for 30 days, so you can leave this page and continue later.
          </p>
        </div>

        <div className="mb-7">
          <StepIndicator
            currentStep={step}
            steps={["Your business", "Services and areas", "First checks"]}
          />
        </div>

        {restoredNotice && (
          <div className="mb-4 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-100">
            {restoredNotice}
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-100">
            {error}
          </div>
        )}

        <div className="mb-4 border-l-2 border-accent-500/45 pl-3 text-xs leading-5 text-zinc-300">
          {locationAllowance ? (
            <>
              <span className="font-semibold text-white">
                {locationUsageLabel(locationAllowance.plan)}.
              </span>{" "}
              {canActivateAnotherLocation(locationAllowance)
                ? isLocationAllowanceEnforced(locationAllowance)
                  ? `${locationAllowance.plan.remaining_locations} still available on ${locationAllowance.plan.name}.`
                  : "You can continue setting up this location."
                : "No open active-location slots."}
            </>
          ) : locationContextLoading ? (
            "Checking your saved locations and plan..."
          ) : (
            "Your saved locations and plan need to be checked again."
          )}
        </div>

        {needsNewLocation && locationContextError ? (
          <div role="status" className="mb-4 rounded-md border border-sky-500/25 bg-sky-500/10 p-3 text-sm leading-6 text-sky-100">
            <p>{locationContextError}</p>
            <button
              type="button"
              className="mt-3 rounded-md border border-sky-200/25 bg-sky-50/10 px-3 py-1.5 text-xs font-semibold text-white"
              onClick={() => void loadLocationContext()}
            >
              Check again
            </button>
          </div>
        ) : null}

        {needsNewLocation && locationAllowance && !canCreateLocation ? (
          <PlanGateNotice
            allowance={locationAllowance}
            orgRole={orgRole}
            detail={locationAllowanceDetail || undefined}
            className="mb-4"
          />
        ) : null}

        {step === 1 && (
          <form onSubmit={handleStep1} className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <p className="text-sm font-medium text-white">What this setup will do</p>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-zinc-300">
                <li>Create your business workspace.</li>
                <li>Save the services you offer and the places you serve.</li>
                <li>Queue your first website scan.</li>
                <li>Add one starter search term and queue your first ranking check.</li>
              </ul>
              <p className="mt-3 text-xs leading-5 text-zinc-500">
                Setup finishes when these requests are accepted. Your first results may keep filling in after you land on the dashboard.
              </p>
            </div>
            {existingLocations.length > 0 ? (
              <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4">
                <label className="block text-xs font-semibold uppercase tracking-[0.16em] text-emerald-100/75">
                  Continue a saved location
                  <select
                    value={businessLocationId}
                    onChange={(event) => chooseExistingLocation(event.target.value)}
                    className="mt-2 w-full rounded-md border border-emerald-200/20 bg-[#0b0b0c] px-3 py-2.5 text-sm font-normal normal-case tracking-normal text-zinc-100 outline-none"
                  >
                    <option value="" disabled={!canCreateLocation}>
                      {canCreateLocation
                        ? "Set up a different new location"
                        : "Choose a saved location"}
                    </option>
                    {existingLocations.map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name}
                        {location.city || location.primary_city
                          ? ` · ${location.city || location.primary_city}${location.region ? `, ${location.region}` : ""}`
                          : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="mt-2 text-xs leading-5 text-emerald-100/75">
                  Choose a location that was already saved to continue its setup without creating a duplicate.
                </p>
              </div>
            ) : null}
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                Business name
              </label>
              <input
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="e.g. Smith's Plumbing"
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                Website
              </label>
              <input
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="e.g. smithsplumbing.com"
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              />
            </div>
            <button
              type="submit"
              disabled={busy || (needsNewLocation && !canCreateLocation)}
              aria-describedby="onboarding-location-availability"
              className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "Saving..." : "Continue"}
            </button>
            <p id="onboarding-location-availability" className="text-xs leading-5 text-zinc-500">
              {needsNewLocation
                ? newLocationCheckUnavailable
                  ? "Adding a new location stays paused until the plan check succeeds."
                  : canCreateLocation
                    ? "This setup will use one active location from your plan."
                    : "Choose a saved location above or review your plan before continuing."
                : "This setup will continue the saved location selected above."}
            </p>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleStep2} className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
              Tell us what customers hire you for and where you take jobs. We&apos;ll use these answers to remove unrelated search ideas before you have to review them.
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                Services customers can hire you for
              </label>
              <textarea
                value={servicesInput}
                onChange={(e) => setServicesInput(e.target.value)}
                rows={4}
                placeholder={"Junk removal\nAppliance removal\nGarage cleanouts"}
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              />
              <p className="mt-1 text-xs leading-5 text-zinc-500">
                Add one service per line. Include important services even if they are missing from your website.
              </p>
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                Cities, counties, or ZIP codes you serve
              </label>
              <textarea
                value={serviceAreasInput}
                onChange={(e) => setServiceAreasInput(e.target.value)}
                rows={4}
                placeholder={"Reno, NV\nSparks, NV\n89501"}
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              />
              <p className="mt-1 text-xs leading-5 text-zinc-500">
                Add one place per line. The first place becomes this location&apos;s home market.
              </p>
            </div>
            <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm leading-6 text-emerald-100">
              Your answers will be treated as confirmed. If the website scan finds more services or places later, you&apos;ll review them before they affect your search ideas.
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-md border border-[#26272c] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-300"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={busy || (needsNewLocation && !canCreateLocation)}
                className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "Saving your answers..." : "Save and start checks"}
              </button>
            </div>
          </form>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-left">
              <p className="text-sm font-medium text-white">What is happening now</p>
              <p className="mt-2 text-sm leading-6 text-zinc-300">
                InsightOS is saving your setup and starting the first background checks. This screen shows which steps are complete, which are still running, and whether anything needs attention before you move on.
              </p>
            </div>

            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Complete
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">{completedTasks}</p>
                  <p className="mt-1 text-xs text-zinc-400">Finished successfully</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    In progress
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">{runningTasks}</p>
                  <p className="mt-1 text-xs text-zinc-400">Working now</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Queued
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">{queuedTasks}</p>
                  <p className="mt-1 text-xs text-zinc-400">Waiting to start</p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#141518] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                    Needs attention
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">{failedTasks}</p>
                  <p className="mt-1 text-xs text-zinc-400">Did not finish</p>
                </div>
              </div>
            </div>

            <SetupTaskList tasks={setupTasks} />

            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <p className="text-sm font-medium text-white">{stepThreeSummary.title}</p>
              <p className="mt-2 text-sm leading-6 text-zinc-300">{stepThreeSummary.body}</p>
              <p className="mt-3 text-sm font-medium text-zinc-100">Next: {stepThreeSummary.next}</p>
            </div>

            {!scanDone || !baselineComplete ? (
              <>
                {baselineTaskStatus !== "error" ? (
                  <div className="flex justify-center">
                    <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#26272c] border-t-accent-500" />
                  </div>
                ) : null}
                <div className="text-center">
                  <p className="text-sm font-medium text-white">
                    {baselineTaskStatus === "error"
                      ? "The baseline needs attention before setup can be completed."
                      : scanDone
                        ? "Building your baseline analysis and first diagnosis..."
                        : hasStartedBackgroundChecks
                      ? "Your first checks are being started now..."
                      : "Preparing your first checks..."}
                  </p>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-400">
                    {baselineStatus?.message || "The report freezes the first website scan and every trustworthy organic metric available at the cutoff. Missing optional connections are labeled—not scored as zero."}
                  </p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
                  <p className="font-medium text-white">Why this is required</p>
                  <p className="mt-2">
                    This immutable starting point makes every later ranking, traffic, website, and conversion change comparable to what existed before InsightOS recommended any work.
                  </p>
                </div>
                {baselineTaskStatus === "error" ? (
                  <button
                    type="button"
                    onClick={() => void refreshBaseline()}
                    className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-100"
                  >
                    Retry baseline analysis
                  </button>
                ) : null}
                {scanDone ? (
                  <button
                    type="button"
                    onClick={leaveWhileBaselineRuns}
                    className="rounded-md border border-[#303137] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200"
                  >
                    Open dashboard while baseline finishes
                  </button>
                ) : null}
              </>
            ) : (
              <>
                <div className="flex justify-center">
                  <div
                    className={`flex h-12 w-12 items-center justify-center rounded-full ${
                      hasSetupIssues
                        ? "border border-amber-500/30 bg-amber-500/10"
                        : "border border-green-500/30 bg-green-500/10"
                    }`}
                  >
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d={hasSetupIssues ? "M12 8v5m0 3h.01M10.29 3.86l-7.4 12.82A2 2 0 004.62 19h14.76a2 2 0 001.73-2.99l-7.4-12.82a2 2 0 00-3.46 0z" : "M5 13l4 4L19 7"}
                        stroke={hasSetupIssues ? "#f59e0b" : "#22c55e"}
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                </div>
                <p className="text-center text-sm font-medium text-white">
                  {hasSetupIssues ? "Setup finished with one or more issues." : "Setup finished successfully."}
                </p>
                <p className="text-center text-sm leading-6 text-zinc-400">
                  {hasSetupIssues
                    ? "Your business was created, but one or more first checks did not finish cleanly. The dashboard will show exactly what needs attention and what to retry."
                    : `${baselineStatus?.baseline?.diagnosis?.summary || "Your business, services, and first evidence are saved."} Your detailed baseline report is available in Reports.`}
                </p>
                {hasSetupIssues && retryableTaskIds.length > 0 && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void runFirstChecks(retryableTaskIds)}
                    className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busy ? "Retrying unfinished checks..." : "Retry unfinished checks"}
                  </button>
                )}
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
                  <p className="font-medium text-white">What happens next</p>
                  <p className="mt-2">
                    {hasSetupIssues
                      ? "Go to the dashboard now. Start with the workflow status cards, then retry any step marked as needing attention."
                      : "Open Reports to review the frozen issues, metrics, score explanations, and prioritized fixes. Later reports can compare against this exact starting point."}
                  </p>
                </div>
                {hasSetupIssues && (
                  <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
                    <p className="font-medium text-white">Still stuck?</p>
                    <p className="mt-2">
                      Email <a className="text-accent-400 underline underline-offset-4" href="mailto:support@verixlabs.com?subject=InsightOS%20setup%20help">support@verixlabs.com</a> with your business name and the step marked Needs attention. Never send a password or API key.
                    </p>
                  </div>
                )}
                <div className="flex flex-wrap gap-3">
                  {!hasSetupIssues && baselineStatus?.baseline?.report_id ? (
                    <button
                      type="button"
                      onClick={() => router.push("/reports")}
                      className="rounded-md border border-[#303137] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200"
                    >
                      Review baseline report
                    </button>
                  ) : null}
                  {!hasSetupIssues ? (
                    <button
                      type="button"
                      onClick={() => finishSetup("connections")}
                      className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
                    >
                      Connect your Google data next &rarr;
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => finishSetup("dashboard")}
                    className="rounded-md border border-[#303137] bg-[#141518] px-4 py-2 text-sm font-medium text-zinc-200"
                  >
                    {hasSetupIssues ? "Open dashboard and fix issues" : "Open dashboard"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
