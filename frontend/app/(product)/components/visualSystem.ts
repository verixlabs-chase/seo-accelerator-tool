export const CUSTOMER_VISUAL_SYSTEM_V2_ENABLED =
  process.env.NEXT_PUBLIC_CUSTOMER_VISUAL_SYSTEM_V2_ENABLED !== "false";

export const OWNER_JOURNEY_V2_ENABLED =
  process.env.NEXT_PUBLIC_OWNER_JOURNEY_V2_ENABLED !== "false";

export const customerPageOrder = [
  "purpose-and-location",
  "key-result",
  "primary-visual",
  "recommended-action",
  "supporting-details",
  "optional-technical-data",
] as const;
