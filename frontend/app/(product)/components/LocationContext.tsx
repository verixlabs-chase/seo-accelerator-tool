"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

import { platformApi } from "../../platform/api";
import { trackProductEvent } from "../../lib/productAnalytics";

export type LocationCampaign = {
  id: string;
  name?: string | null;
  domain?: string | null;
  business_location_id?: string | null;
};

type LocationContextValue = {
  campaigns: LocationCampaign[];
  selectedCampaignId: string;
  selectedCampaign: LocationCampaign | null;
  setSelectedCampaignId: Dispatch<SetStateAction<string>>;
  loadingLocations: boolean;
  reloadLocations: () => Promise<void>;
};

const LOCATION_STORAGE_KEY = "insightos:selected-campaign";

const LocationContext = createContext<LocationContextValue | null>(null);

export function LocationProvider({ children }: { children: ReactNode }) {
  const [campaigns, setCampaigns] = useState<LocationCampaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [loadingLocations, setLoadingLocations] = useState(true);

  const reloadLocations = useCallback(async () => {
    setLoadingLocations(true);
    try {
      const response = await platformApi("/campaigns");
      const items = (
        Array.isArray(response)
          ? response
          : Array.isArray(response?.items)
            ? response.items
            : []
      ) as LocationCampaign[];
      setCampaigns(items);
      setSelectedCampaignId((current) => {
        if (items.some((item) => item.id === current)) {
          return current;
        }

        const stored =
          typeof window === "undefined"
            ? ""
            : window.localStorage.getItem(LOCATION_STORAGE_KEY) ?? "";
        if (items.some((item) => item.id === stored)) {
          return stored;
        }

        return items[0]?.id ?? "";
      });
    } finally {
      setLoadingLocations(false);
    }
  }, []);

  useEffect(() => {
    void reloadLocations().catch(() => {
      setCampaigns([]);
    });
  }, [reloadLocations]);

  useEffect(() => {
    if (selectedCampaignId && typeof window !== "undefined") {
      window.localStorage.setItem(LOCATION_STORAGE_KEY, selectedCampaignId);
    }
  }, [selectedCampaignId]);

  const selectedCampaign =
    campaigns.find((campaign) => campaign.id === selectedCampaignId) ?? null;

  const value = useMemo(
    () => ({
      campaigns,
      selectedCampaignId,
      selectedCampaign,
      setSelectedCampaignId,
      loadingLocations,
      reloadLocations,
    }),
    [
      campaigns,
      loadingLocations,
      reloadLocations,
      selectedCampaign,
      selectedCampaignId,
    ],
  );

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useLocationContext() {
  const value = useContext(LocationContext);
  if (!value) {
    throw new Error("useLocationContext must be used inside LocationProvider.");
  }
  return value;
}

export function LocationSelector() {
  const {
    campaigns,
    selectedCampaignId,
    setSelectedCampaignId,
    loadingLocations,
  } = useLocationContext();

  function chooseLocation(nextCampaignId: string) {
    setSelectedCampaignId(nextCampaignId);
    if (nextCampaignId) {
      void trackProductEvent({
        eventName: "workspace.location_switched",
        campaignId: nextCampaignId,
        properties: { selection_origin: "top_bar" },
      });
    }
  }

  return (
    <label className="flex min-w-[220px] items-center gap-2 rounded-md border border-accent-500/30 bg-accent-500/10 px-3 py-1.5 shadow-[0_0_18px_rgba(255,106,26,0.08)]">
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.14em] text-accent-300">
        Viewing
      </span>
      <select
        aria-label="Choose the location shown across the workspace"
        value={selectedCampaignId}
        onChange={(event) => chooseLocation(event.target.value)}
        disabled={loadingLocations || campaigns.length === 0}
        className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-white outline-none disabled:text-zinc-500"
      >
        {campaigns.length === 0 ? (
          <option value="">{loadingLocations ? "Loading locations…" : "No locations yet"}</option>
        ) : null}
        {campaigns.map((campaign) => (
          <option key={campaign.id} value={campaign.id} className="bg-[#111214] text-white">
            {campaign.name || campaign.domain || "Unnamed location"}
          </option>
        ))}
      </select>
    </label>
  );
}
