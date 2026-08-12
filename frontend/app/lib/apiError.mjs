const INTERNAL_SEARCH_SUPPLIER_URL = /https?:\/\/[^\s"']*dataforseo[^\s"']*/gi;
const INTERNAL_SEARCH_SUPPLIER_NAME = /data[\s_-]*for[\s_-]*seo/gi;

export function getCustomerSafeApiMessage(value) {
  return String(value || "")
    .replace(INTERNAL_SEARCH_SUPPLIER_URL, "the search data service")
    .replace(INTERNAL_SEARCH_SUPPLIER_NAME, "the search data service");
}

export function getApiErrorDetail(json, status) {
  const detail = (
    json?.error?.message ||
    json?.errors?.[0]?.details?.message ||
    json?.errors?.[0]?.message ||
    json?.detail?.message ||
    (typeof json?.detail === "string" ? json.detail : "") ||
    `Request failed (${status})`
  );
  return getCustomerSafeApiMessage(detail);
}
