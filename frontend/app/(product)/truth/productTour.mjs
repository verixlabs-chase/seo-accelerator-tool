export const PRODUCT_TOUR_EVENT = "insightos:product-tour:open";
export const PRODUCT_TOUR_VERSION = 1;
export const PRODUCT_TOUR_TTL_MS = 90 * 24 * 60 * 60 * 1000;

export const PRODUCT_TOUR_PERSONAS = ["solo", "multi", "team"];

function normalizedScope(scope) {
  return String(scope || "current").trim() || "current";
}

export function productTourStorageKey(scope) {
  return `insightos:product-tour:v${PRODUCT_TOUR_VERSION}:${normalizedScope(scope)}`;
}

export function createProductTourState(persona = null, nowMs = Date.now()) {
  return {
    version: PRODUCT_TOUR_VERSION,
    active: true,
    persona: PRODUCT_TOUR_PERSONAS.includes(persona) ? persona : null,
    stepIndex: 0,
    updatedAt: nowMs,
    expiresAt: nowMs + PRODUCT_TOUR_TTL_MS,
    completedAt: null,
  };
}

export function readProductTourState(storage, scope, nowMs = Date.now()) {
  if (!storage) return null;
  try {
    const parsed = JSON.parse(storage.getItem(productTourStorageKey(scope)) || "null");
    if (
      !parsed ||
      parsed.version !== PRODUCT_TOUR_VERSION ||
      typeof parsed.expiresAt !== "number" ||
      parsed.expiresAt <= nowMs
    ) {
      storage.removeItem(productTourStorageKey(scope));
      return null;
    }
    return {
      ...parsed,
      persona: PRODUCT_TOUR_PERSONAS.includes(parsed.persona) ? parsed.persona : null,
      stepIndex: Number.isInteger(parsed.stepIndex) && parsed.stepIndex >= 0 ? parsed.stepIndex : 0,
    };
  } catch {
    storage.removeItem(productTourStorageKey(scope));
    return null;
  }
}

export function saveProductTourState(storage, scope, state, nowMs = Date.now()) {
  if (!storage) return state;
  const saved = {
    ...state,
    version: PRODUCT_TOUR_VERSION,
    updatedAt: nowMs,
    expiresAt: nowMs + PRODUCT_TOUR_TTL_MS,
  };
  storage.setItem(productTourStorageKey(scope), JSON.stringify(saved));
  return saved;
}

export function requestProductTour(storage, scope, persona = null, nowMs = Date.now()) {
  const state = createProductTourState(persona, nowMs);
  return saveProductTourState(storage, scope, state, nowMs);
}

export function finishProductTour(storage, scope, state, nowMs = Date.now()) {
  return saveProductTourState(
    storage,
    scope,
    { ...state, active: false, completedAt: nowMs },
    nowMs,
  );
}
