export type ClientPortalIdentity = {
  display_name: string;
  portal_title: string;
  accent_color: string;
  logo_data_url: string | null;
  platform_attribution_visible: boolean;
};

export const DEFAULT_CLIENT_PORTAL_IDENTITY: ClientPortalIdentity = {
  display_name: "InsightOS",
  portal_title: "Your private client reports",
  accent_color: "#E85D19",
  logo_data_url: null,
  platform_attribution_visible: true,
};

export const LOADING_CLIENT_PORTAL_IDENTITY: ClientPortalIdentity = {
  display_name: "Private reports",
  portal_title: "Your private client reports",
  accent_color: "#71717A",
  logo_data_url: null,
  platform_attribution_visible: false,
};

export function safeClientPortalIdentity(
  identity?: ClientPortalIdentity,
): ClientPortalIdentity {
  if (!identity) return DEFAULT_CLIENT_PORTAL_IDENTITY;
  return {
    display_name:
      identity.display_name?.trim() || DEFAULT_CLIENT_PORTAL_IDENTITY.display_name,
    portal_title:
      identity.portal_title?.trim() || DEFAULT_CLIENT_PORTAL_IDENTITY.portal_title,
    accent_color: /^#[0-9A-Fa-f]{6}$/.test(identity.accent_color)
      ? identity.accent_color
      : DEFAULT_CLIENT_PORTAL_IDENTITY.accent_color,
    logo_data_url: identity.logo_data_url?.startsWith("data:image/png;base64,")
      ? identity.logo_data_url
      : null,
    platform_attribution_visible: identity.platform_attribution_visible !== false,
  };
}
