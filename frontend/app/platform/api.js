"use client";

import { clearAuthSession } from "../lib/authStorage";
import { getApiErrorDetail } from "../lib/apiError.mjs";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? "/api/v1" : "http://localhost:8000/api/v1");

async function authenticatedRequest(path, options = {}) {
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

  return response;
}

async function throwApiError(response) {
  const json = await response.json().catch(() => ({}));
  const detail = getApiErrorDetail(json, response.status);
  throw new PlatformApiError(detail, response.status, json);
}

function apiErrorDetails(json) {
  return (
    json?.errors?.[0]?.details ||
    (typeof json?.detail === "object" ? json.detail : {}) ||
    {}
  );
}

export class PlatformApiError extends Error {
  constructor(message, status, json = {}) {
    super(message);
    this.name = "PlatformApiError";
    this.status = status;
    this.details = apiErrorDetails(json);
    this.reasonCode = this.details?.reason_code || null;
  }
}

export async function platformApi(path, options = {}) {
  const response = await authenticatedRequest(path, options);

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = getApiErrorDetail(json, response.status);
    throw new PlatformApiError(detail, response.status, json);
  }
  return json.data;
}

export async function platformApiFile(path, options = {}) {
  const response = await authenticatedRequest(path, options);
  if (!response.ok) {
    await throwApiError(response);
  }

  return {
    blob: await response.blob(),
    contentType: response.headers.get("Content-Type") || "application/octet-stream",
    contentDisposition: response.headers.get("Content-Disposition") || "",
  };
}
