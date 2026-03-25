"use client";

import { clearAuthSession } from "../lib/authStorage";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function platformApi(path, options = {}) {
  async function runRequest() {
    return fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });
  }

  let response = await runRequest();

  if (response.status === 401) {
    const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    const refreshJson = await refreshResponse.json().catch(() => ({}));
    if (!refreshResponse.ok || !refreshJson?.data?.access_token) {
      clearAuthSession();
      throw new Error("Session expired. Please log in again.");
    }
    response = await runRequest();
  }

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = json?.error?.message || json?.errors?.[0]?.message || `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return json.data;
}
