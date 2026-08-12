"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { getTenantId } from "../../lib/authStorage";
import { trackProductEvent } from "../../lib/productAnalytics";
import {
  PRODUCT_TOUR_EVENT,
  PRODUCT_TOUR_PERSONAS,
  finishProductTour,
  readProductTourState,
  requestProductTour,
  saveProductTourState,
} from "../truth/productTour.mjs";
import { useLocationContext } from "./LocationContext";
import { ProductIcon } from "./ProductIcon";

type TourPersona = "solo" | "multi" | "team";

type TourStep = {
  path: string;
  eyebrow: string;
  title: string;
  summary: string;
  action: string;
};

const PERSONAS: Array<{ id: TourPersona; label: string; summary: string }> = [
  {
    id: "solo",
    label: "One business",
    summary: "Focus on the few numbers and actions that matter for one location.",
  },
  {
    id: "multi",
    label: "Several locations",
    summary: "Compare locations, then open one location before taking action.",
  },
  {
    id: "team",
    label: "Team or agency",
    summary: "Organize client work, approvals, and shareable progress.",
  },
];

const TOUR_STEPS: Record<TourPersona, TourStep[]> = {
  solo: [
    {
      path: "/dashboard",
      eyebrow: "Your starting point",
      title: "See what changed first",
      summary: "Overview leads with the latest business result, a visual trend, and the one item that deserves attention.",
      action: "Show my overview",
    },
    {
      path: "/rankings",
      eyebrow: "Customer searches",
      title: "See where your business appears",
      summary: "Search Rankings keeps every tracked phrase tied to this location and shows whether its position moved.",
      action: "Show search rankings",
    },
    {
      path: "/local-visibility",
      eyebrow: "Nearby customers",
      title: "Check different parts of your service area",
      summary: "Local Search maps how one tracked phrase performs from different points around the location.",
      action: "Show local search",
    },
    {
      path: "/opportunities",
      eyebrow: "Take action",
      title: "Work through a measured action plan",
      summary: "Next Steps puts the first useful action on top, gives you a checklist, and returns later to measure the result.",
      action: "Show my next steps",
    },
  ],
  multi: [
    {
      path: "/locations",
      eyebrow: "Your location list",
      title: "Find the locations that need help",
      summary: "Manage Locations compares locations without combining their results, so weak spots stand out.",
      action: "Show my locations",
    },
    {
      path: "/dashboard",
      eyebrow: "One location at a time",
      title: "Use the location switcher before reading results",
      summary: "The Viewing control at the top changes the location used across Overview, Rankings, Local Search, and Next Steps.",
      action: "Show the overview",
    },
    {
      path: "/rankings",
      eyebrow: "Separate search results",
      title: "Compare the right location and phrase",
      summary: "Each location keeps its own tracked phrases, search positions, and history. Switch locations at the top whenever needed.",
      action: "Show search rankings",
    },
    {
      path: "/reports",
      eyebrow: "Share progress",
      title: "Create a report for the selected location",
      summary: "Reports freeze the saved facts for one location so results are not silently blended or changed later.",
      action: "Show reports",
    },
  ],
  team: [
    {
      path: "/locations",
      eyebrow: "Organize the work",
      title: "Group locations before assigning work",
      summary: "Location groups help your team reuse a target list without mixing each business's results.",
      action: "Show locations",
    },
    {
      path: "/opportunities",
      eyebrow: "Review the plan",
      title: "Start with evidence-backed work",
      summary: "Next Steps explains why each item matters, who should handle it, and how its result will be checked.",
      action: "Show next steps",
    },
    {
      path: "/profile-campaigns",
      eyebrow: "Approve bulk work",
      title: "Preview every location before anything runs",
      summary: "Profile Campaigns shows ready and blocked locations first, then requires approval before supported bulk work can run.",
      action: "Show profile campaigns",
    },
    {
      path: "/reports",
      eyebrow: "Client-ready progress",
      title: "Review the facts before sharing",
      summary: "Reports separate completed work from measured results and keep every location's numbers traceable.",
      action: "Show reports",
    },
  ],
};

type TourState = {
  active: boolean;
  persona: TourPersona | null;
  stepIndex: number;
  completedAt?: number | null;
};

export function GuidedProductTour() {
  const pathname = usePathname();
  const router = useRouter();
  const { campaigns, selectedCampaignId } = useLocationContext();
  const [state, setState] = useState<TourState | null>(null);
  const scope = getTenantId() || "current";

  useEffect(() => {
    const saved = readProductTourState(window.localStorage, scope);
    setState(saved);

    function openTour(event: Event) {
      const requested = (event as CustomEvent<{ persona?: TourPersona }>).detail?.persona;
      const persona = PRODUCT_TOUR_PERSONAS.includes(requested) ? requested : null;
      setState(requestProductTour(window.localStorage, scope, persona));
    }
    window.addEventListener(PRODUCT_TOUR_EVENT, openTour);
    return () => window.removeEventListener(PRODUCT_TOUR_EVENT, openTour);
  }, [scope]);

  const recommendedPersona: TourPersona = campaigns.length > 1 ? "multi" : "solo";
  const steps = state?.persona ? TOUR_STEPS[state.persona] : [];
  const stepIndex = Math.min(state?.stepIndex || 0, Math.max(steps.length - 1, 0));
  const step = steps[stepIndex];
  const progress = useMemo(
    () => (step ? `${stepIndex + 1} of ${steps.length}` : "Choose a tour"),
    [step, stepIndex, steps.length],
  );

  function persist(next: TourState) {
    setState(saveProductTourState(window.localStorage, scope, next));
  }

  function choosePersona(persona: TourPersona) {
    const next = requestProductTour(window.localStorage, scope, persona) as TourState;
    setState(next);
    void trackProductEvent({
      eventName: "tour.started",
      campaignId: selectedCampaignId,
      properties: { persona },
    });
  }

  function stopTour() {
    if (!state) return;
    persist({ ...state, active: false });
  }

  function moveBack() {
    if (!state || !state.persona || stepIndex === 0) return;
    const nextIndex = stepIndex - 1;
    persist({ ...state, stepIndex: nextIndex });
    router.push(TOUR_STEPS[state.persona][nextIndex].path);
  }

  function advance() {
    if (!state || !state.persona || !step) return;
    void trackProductEvent({
      eventName: "tour.step_viewed",
      campaignId: selectedCampaignId,
      properties: { persona: state.persona, step_number: String(stepIndex + 1) },
    });
    if (stepIndex >= steps.length - 1) {
      setState(finishProductTour(window.localStorage, scope, state));
      void trackProductEvent({
        eventName: "tour.completed",
        campaignId: selectedCampaignId,
        properties: { persona: state.persona },
      });
      return;
    }
    const nextIndex = stepIndex + 1;
    persist({ ...state, stepIndex: nextIndex });
    router.push(steps[nextIndex].path);
  }

  function handlePrimaryAction() {
    if (!step) return;
    if (pathname !== step.path) {
      router.push(step.path);
      return;
    }
    advance();
  }

  const primaryActionLabel = !step
    ? "Continue"
    : pathname !== step.path
      ? step.action
      : stepIndex === steps.length - 1
        ? "Finish tour"
        : `Next: ${steps[stepIndex + 1].eyebrow}`;

  if (!state?.active) return null;

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-labelledby="product-tour-title"
      className="fixed bottom-4 right-4 z-[70] w-[calc(100vw-2rem)] max-w-[390px] rounded-lg border border-accent-500/35 bg-[#111214] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.65)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md border border-accent-500/30 bg-accent-500/10 text-accent-300">
            <ProductIcon name="help" size={17} />
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-300">Quick tour</p>
            <p className="mt-0.5 text-xs text-zinc-500">{progress}</p>
          </div>
        </div>
        <button type="button" onClick={stopTour} className="text-xs text-zinc-400 hover:text-white">
          Close
        </button>
      </div>

      {!state.persona ? (
        <div className="mt-5">
          <h2 id="product-tour-title" className="text-xl font-semibold text-white">What kind of work do you manage?</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-400">We will show four useful places. You can stop at any time and restart from Help Center.</p>
          <div className="mt-4 space-y-2">
            {PERSONAS.map((persona) => (
              <button
                key={persona.id}
                type="button"
                onClick={() => choosePersona(persona.id)}
                className={`w-full rounded-md border p-3 text-left transition hover:border-accent-500/40 ${persona.id === recommendedPersona ? "border-accent-500/25 bg-accent-500/5" : "border-[#303137] bg-[#0b0b0c]"}`}
              >
                <span className="flex items-center justify-between gap-3 text-sm font-semibold text-white">
                  {persona.label}
                  {persona.id === recommendedPersona ? <span className="text-[10px] uppercase tracking-[0.12em] text-accent-300">Suggested</span> : null}
                </span>
                <span className="mt-1 block text-xs leading-5 text-zinc-400">{persona.summary}</span>
              </button>
            ))}
          </div>
        </div>
      ) : step ? (
        <div className="mt-5">
          <div className="flex gap-1.5" aria-label={`Tour progress: ${progress}`}>
            {steps.map((_, index) => (
              <span key={index} className={`h-1.5 flex-1 rounded-full ${index <= stepIndex ? "bg-accent-500" : "bg-[#303137]"}`} />
            ))}
          </div>
          <p className="mt-5 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{step.eyebrow}</p>
          <h2 id="product-tour-title" className="mt-1.5 text-xl font-semibold text-white">{step.title}</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-300">{step.summary}</p>
          {pathname !== step.path ? (
            <p className="mt-3 rounded-md border border-[#303137] bg-[#0b0b0c] px-3 py-2 text-xs text-zinc-400">Open {step.action.replace(/^Show (my |the )?/, "").toLowerCase()} from the menu whenever you want to explore it.</p>
          ) : null}
          <div className="mt-5 flex items-center justify-between gap-3">
            <button type="button" onClick={moveBack} disabled={stepIndex === 0} className="text-sm text-zinc-400 hover:text-white disabled:invisible">Back</button>
            <button type="button" onClick={handlePrimaryAction} className="rounded-md border border-accent-500/40 bg-accent-500 px-4 py-2 text-sm font-semibold text-white hover:bg-accent-400">
              {primaryActionLabel} →
            </button>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
