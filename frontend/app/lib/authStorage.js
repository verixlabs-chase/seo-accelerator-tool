"use client";

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const TENANT_ID_KEY = "tenant_id";

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

  const hasSessionToken = sessionStorage.getItem(ACCESS_TOKEN_KEY);
  const legacyAccessToken = legacyStorage.getItem(ACCESS_TOKEN_KEY);

  if (!hasSessionToken && legacyAccessToken) {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, legacyAccessToken);
    const legacyRefreshToken = legacyStorage.getItem(REFRESH_TOKEN_KEY);
    const legacyTenantId = legacyStorage.getItem(TENANT_ID_KEY);

    if (legacyRefreshToken) {
      sessionStorage.setItem(REFRESH_TOKEN_KEY, legacyRefreshToken);
    }

    if (legacyTenantId) {
      sessionStorage.setItem(TENANT_ID_KEY, legacyTenantId);
    }
  }

  legacyStorage.removeItem(ACCESS_TOKEN_KEY);
  legacyStorage.removeItem(REFRESH_TOKEN_KEY);
  legacyStorage.removeItem(TENANT_ID_KEY);

  return sessionStorage;
}

function getStorage() {
  return migrateLegacySession();
}

export function getAccessToken() {
  return getStorage()?.getItem(ACCESS_TOKEN_KEY) || "";
}

export function getRefreshToken() {
  return getStorage()?.getItem(REFRESH_TOKEN_KEY) || "";
}

export function getTenantId() {
  return getStorage()?.getItem(TENANT_ID_KEY) || "";
}

export function setAuthSession({ accessToken, refreshToken, tenantId }) {
  const storage = getStorage();

  if (!storage) {
    return;
  }

  storage.setItem(ACCESS_TOKEN_KEY, accessToken);
  storage.setItem(REFRESH_TOKEN_KEY, refreshToken);

  if (tenantId) {
    storage.setItem(TENANT_ID_KEY, tenantId);
  } else {
    storage.removeItem(TENANT_ID_KEY);
  }
}

export function updateAccessToken(accessToken) {
  const storage = getStorage();

  if (!storage) {
    return;
  }

  storage.setItem(ACCESS_TOKEN_KEY, accessToken);
}

export function clearAuthSession() {
  const sessionStorage = getSessionStorage();
  const legacyStorage = getLegacyStorage();

  sessionStorage?.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage?.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage?.removeItem(TENANT_ID_KEY);
  legacyStorage?.removeItem(ACCESS_TOKEN_KEY);
  legacyStorage?.removeItem(REFRESH_TOKEN_KEY);
  legacyStorage?.removeItem(TENANT_ID_KEY);
}
