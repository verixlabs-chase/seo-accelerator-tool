"use client";

import {
  clearAuthSession,
  getAccessToken,
  getRefreshToken,
  updateAccessToken,
} from "../lib/authStorage";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function platformApi(path, options = {}) {
  async function runRequest(token) {
    return fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(options.headers || {})
      }
    });
  }

  let token = getAccessToken();
  if (!token) {
    throw new Error("No token found. Login first.");
  }

  let response = await runRequest(token);

  if (response.status === 401) {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      clearAuthSession();
      throw new Error("Session expired. Please log in again.");
    }
    const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    const refreshJson = await refreshResponse.json().catch(() => ({}));
    if (!refreshResponse.ok || !refreshJson?.data?.access_token) {
      clearAuthSession();
      throw new Error("Session expired. Please log in again.");
    }
    updateAccessToken(refreshJson.data.access_token);
    token = refreshJson.data.access_token;
    response = await runRequest(token);
  }

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = json?.error?.message || json?.errors?.[0]?.message || `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return json.data;
}
