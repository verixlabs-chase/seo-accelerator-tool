"use client";

import { useState, useEffect, type FormEvent } from "react";
import { platformApi } from "../../platform/api";

type OnboardingCompletion = {
  campaignId: string;
  campaignDomain: string;
  notice: string;
};

type OnboardingWizardProps = {
  onComplete: (payload: OnboardingCompletion) => void;
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

function SetupTaskList({ tasks }: { tasks: SetupTask[] }) {
  return (
    <div className="space-y-3">
      {tasks.map((task) => {
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

export function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Step 1 state
  const [businessName, setBusinessName] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");

  // Step 1 result
  const [campaignId, setCampaignId] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");

  // Step 2 state
  const [workType, setWorkType] = useState("General Services");
  const [serviceArea, setServiceArea] = useState("");

  // Step 3 state
  const [scanStarted, setScanStarted] = useState(false);
  const [scanDone, setScanDone] = useState(false);
  const [setupTasks, setSetupTasks] = useState<SetupTask[]>([
    {
      id: "campaign",
      title: "Save your business profile",
      description: "Create the workspace for your business inside InsightOS.",
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
  ]);

  function updateTask(taskId: string, status: SetupTask["status"]) {
    setSetupTasks((current) =>
      current.map((task) => (task.id === taskId ? { ...task, status } : task)),
    );
  }

  async function handleStep1(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!businessName.trim() || !websiteUrl.trim()) {
      setError("Please enter your business name and website.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      updateTask("campaign", "running");
      const domain = websiteUrl.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
      const created = await platformApi("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          name: businessName.trim(),
          domain,
        }),
      });

      setCampaignId(created.id);
      setCampaignDomain(domain);
      updateTask("campaign", "done");
      setStep(2);
    } catch (err) {
      updateTask("campaign", "error");
      setError(
        err instanceof Error
          ? err.message
          : "We couldn't save your info. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  function handleStep2(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStep(3);
  }

  // Step 3: fire scans on mount
  useEffect(() => {
    if (step !== 3 || scanStarted) return;
    setScanStarted(true);

    async function runScans() {
      setBusy(true);
      setError("");

      try {
        const seedUrl = campaignDomain.startsWith("http")
          ? campaignDomain
          : `https://${campaignDomain}`;

        const keyword = workType.toLowerCase().includes("general")
          ? `${businessName.toLowerCase()} near me`
          : `${workType.toLowerCase()} near me`;

        const locationCode = serviceArea.trim() || "US";

        updateTask("crawl", "running");
        await platformApi("/crawl/schedule", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            crawl_type: "deep",
            seed_url: seedUrl,
          }),
        });
        updateTask("crawl", "done");

        updateTask("keyword", "running");
        await platformApi("/rank/keywords", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            cluster_name: workType.trim() || "Core Terms",
            keyword: keyword,
            location_code: locationCode,
          }),
        });
        updateTask("keyword", "done");

        updateTask("ranking", "running");
        await platformApi("/rank/schedule", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            location_code: locationCode,
          }),
        });
        updateTask("ranking", "done");

        setScanDone(true);
      } catch (err) {
        setSetupTasks((current) =>
          current.map((task) =>
            task.status === "running" ? { ...task, status: "error" } : task,
          ),
        );
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong starting your first results. You can retry from the dashboard."
        );
        setScanDone(true);
      } finally {
        setBusy(false);
      }
    }

    void runScans();
  }, [step, scanStarted, campaignId, campaignDomain, workType, serviceArea, businessName]);

  return (
    <div className="mx-auto max-w-lg py-8">
      <div className="rounded-md border border-[#26272c] bg-[#141518] p-7 shadow-[0_0_30px_rgba(0,0,0,0.4)]">
        <div className="mb-7">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Guided setup
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">
            Set up your business
          </h2>
          <p className="mt-2.5 text-sm leading-6 text-zinc-300">
            We&apos;ll connect your business, start your first checks, and show you when your first results are on the way.
          </p>
        </div>

        <div className="mb-7">
          <StepIndicator
            currentStep={step}
            steps={["Your business", "What you do", "First scan"]}
          />
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-100">
            {error}
          </div>
        )}

        {step === 1 && (
          <form onSubmit={handleStep1} className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4">
              <p className="text-sm font-medium text-white">What this setup will do</p>
              <ul className="mt-2 space-y-2 text-sm leading-6 text-zinc-300">
                <li>Create your business workspace.</li>
                <li>Start your first website scan.</li>
                <li>Add one starter search term and queue your first ranking check.</li>
              </ul>
            </div>
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
              disabled={busy}
              className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "Saving..." : "Continue"}
            </button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleStep2} className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
              We&apos;ll use this to choose a starter tracked search and local area for your first results.
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                What type of work do you do?
              </label>
              <select
                value={workType}
                onChange={(e) => setWorkType(e.target.value)}
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none"
              >
                <option value="General Services">General services</option>
                <option value="Plumbing">Plumbing</option>
                <option value="HVAC">Heating &amp; cooling (HVAC)</option>
                <option value="Electrical">Electrical</option>
                <option value="Roofing">Roofing</option>
                <option value="Landscaping">Landscaping</option>
                <option value="Cleaning">Cleaning</option>
                <option value="Pest Control">Pest control</option>
                <option value="Painting">Painting</option>
                <option value="Remodeling">Remodeling</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-[0.18em] text-zinc-500">
                City or area you serve
              </label>
              <input
                value={serviceArea}
                onChange={(e) => setServiceArea(e.target.value)}
                placeholder="e.g. Austin, TX"
                className="w-full rounded-md border border-[#26272c] bg-[#0b0b0c] px-3 py-2.5 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Optional — defaults to US-wide results if left blank.
              </p>
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
                className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
              >
                Continue
              </button>
            </div>
          </form>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-left">
              <p className="text-sm font-medium text-white">What is happening now</p>
              <p className="mt-2 text-sm leading-6 text-zinc-300">
                InsightOS is creating your first results in the background. You can go to the
                dashboard as soon as setup finishes, and new data will appear as each check
                completes.
              </p>
            </div>

            <SetupTaskList tasks={setupTasks} />

            {!scanDone ? (
              <>
                <div className="flex justify-center">
                  <div className="h-10 w-10 animate-spin rounded-full border-2 border-[#26272c] border-t-accent-500" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-white">
                    Starting your first website and search checks...
                  </p>
                  <p className="mt-1.5 text-sm leading-6 text-zinc-400">
                    This usually takes about 1 to 2 minutes to queue, and results may keep filling in after you reach the dashboard.
                  </p>
                </div>
                <div className="rounded-md border border-[#26272c] bg-[#111214] p-4 text-sm leading-6 text-zinc-300">
                  Next: you&apos;ll land on a daily briefing that shows the latest change, why it matters, and the next recommended action.
                </div>
              </>
            ) : (
              <>
                <div className="flex justify-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full border border-green-500/30 bg-green-500/10">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M5 13l4 4L19 7" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                </div>
                <p className="text-center text-sm font-medium text-white">
                  {error ? "Setup finished with one or more issues." : "Your first results are on the way."}
                </p>
                <p className="text-center text-sm leading-6 text-zinc-400">
                  {error
                    ? "Your business was created, but one or more checks need attention. You can retry them from the dashboard."
                    : "Your dashboard will now show the active business, current progress, and the next recommended step while results fill in."}
                </p>
                <button
                  onClick={() =>
                    onComplete({
                      campaignId,
                      campaignDomain,
                      notice: error
                        ? "Business setup finished, but some first-result checks need attention."
                        : "Business setup finished. Your first website and ranking checks are running now.",
                    })
                  }
                  className="rounded-md border border-accent-500/30 bg-accent-500/10 px-4 py-2 text-sm font-medium text-zinc-100"
                >
                  Go to your dashboard &rarr;
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
