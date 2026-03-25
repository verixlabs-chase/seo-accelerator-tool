"use client";

const LEGACY_ACCESS_TOKEN_KEY = "access_token";
const LEGACY_REFRESH_TOKEN_KEY = "refresh_token";
const TENANT_ID_KEY = "tenant_id";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

function getSessionStorage() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.sessionStorage;
}

function getLegacyStorage() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage;
}

function migrateLegacySession() {
  const sessionStorage = getSessionStorage();
  const legacyStorage = getLegacyStorage();

  if (!sessionStorage || !legacyStorage) {
    return sessionStorage;
  }

  const legacyTenantId = legacyStorage.getItem(TENANT_ID_KEY);
  const hasTenantId = sessionStorage.getItem(TENANT_ID_KEY);
  if (!hasTenantId && legacyTenantId) {
    sessionStorage.setItem(TENANT_ID_KEY, legacyTenantId);
  }

  sessionStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  legacyStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  legacyStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  legacyStorage.removeItem(TENANT_ID_KEY);

  return sessionStorage;
}

function getStorage() {
  return migrateLegacySession();
}

export function getAccessToken() {
  return "";
}

export function getRefreshToken() {
  return "";
}

export function getTenantId() {
  return getStorage()?.getItem(TENANT_ID_KEY) || "";
}

export function setAuthSession({ tenantId }) {
  const storage = getStorage();

  if (!storage) {
    return;
  }

  if (tenantId) {
    storage.setItem(TENANT_ID_KEY, tenantId);
  } else {
    storage.removeItem(TENANT_ID_KEY);
  }
}

export function updateAccessToken(accessToken) {
  void accessToken;
}

export function clearAuthSession() {
  const sessionStorage = getSessionStorage();
  const legacyStorage = getLegacyStorage();

  sessionStorage?.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  sessionStorage?.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  sessionStorage?.removeItem(TENANT_ID_KEY);
  legacyStorage?.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  legacyStorage?.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  legacyStorage?.removeItem(TENANT_ID_KEY);

  if (typeof window !== "undefined") {
    void fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
      keepalive: true,
    }).catch(() => {});
  }
}
