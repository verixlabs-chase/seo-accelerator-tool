export function getApiErrorDetail(json, status) {
  return (
    json?.error?.message ||
    json?.errors?.[0]?.details?.message ||
    json?.errors?.[0]?.message ||
    json?.detail?.message ||
    (typeof json?.detail === "string" ? json.detail : "") ||
    `Request failed (${status})`
  );
}
