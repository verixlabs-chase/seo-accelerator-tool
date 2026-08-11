import { platformApi } from "../platform/api";

type ProductEventInput = {
  eventName: string;
  campaignId?: string | null;
  properties?: Record<string, string>;
  idempotencyKey?: string | null;
};

export type ProductFeedbackInput = {
  context:
    | "recommendation_usefulness"
    | "explanation_clarity"
    | "forecast_trust"
    | "automation_confidence"
    | "report_quality";
  subjectType: "recommendation" | "explanation" | "forecast" | "automation" | "report";
  subjectId?: string | null;
  campaignId?: string | null;
  rating: number;
  reasonCode:
    | "useful"
    | "clear"
    | "believable"
    | "not_useful_yet"
    | "unclear"
    | "missing_context"
    | "too_technical"
    | "not_believable";
};

export function analyticsDayKey(): string {
  return new Date().toISOString().slice(0, 10).replaceAll("-", "");
}

export async function trackProductEvent({
  eventName,
  campaignId,
  properties = {},
  idempotencyKey,
}: ProductEventInput): Promise<boolean> {
  try {
    await platformApi("/product-analytics/events", {
      method: "POST",
      body: JSON.stringify({
        event_name: eventName,
        campaign_id: campaignId || null,
        properties,
        idempotency_key: idempotencyKey || null,
      }),
    });
    return true;
  } catch {
    // Measurement must never interrupt the owner's work.
    return false;
  }
}

export async function submitProductFeedback(input: ProductFeedbackInput): Promise<void> {
  await platformApi("/product-analytics/feedback", {
    method: "POST",
    body: JSON.stringify({
      context: input.context,
      subject_type: input.subjectType,
      subject_id: input.subjectId || null,
      campaign_id: input.campaignId || null,
      rating: input.rating,
      reason_code: input.reasonCode,
    }),
  });
}
