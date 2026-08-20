"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import {
  AppShell,
  EmptyState,
  LoadingCard,
  OwnerDecisionPanel,
  ProductPageIntro,
  TruthNotice,
  type TrustSignal,
} from "../components";
import { buildProductNav } from "../nav.config";
import { platformApi, platformApiFile } from "../../platform/api";
import { getTenantId } from "../../lib/authStorage";
import { getConnectionStatusView } from "../truth/dataConnectionsTruth.mjs";
import { requestProductTour } from "../truth/productTour.mjs";

type Me = {
  organization_id?: string;
  org_role?: string;
  organization_status?: string;
};

type AuthSessionSummary = {
  id: string;
  organization_id?: string | null;
  status: "active";
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};

type Campaign = {
  id: string;
  name: string;
  domain: string;
  setup_state: string;
  business_location_id?: string | null;
};

type SearchConsoleResource = {
  id: string;
  name: string;
  permission_level: string;
  resource_scope: string;
};

type BusinessProfileResource = {
  id: string;
  name: string;
  account_name: string;
  account_role: string;
  permission_level: string;
  verified: boolean;
  address: string;
  website: string;
  phone: string;
  primary_category: string;
};

type AnalyticsResource = {
  id: string;
  name: string;
  account_name: string;
  property_type: string;
  can_edit: boolean;
  resource_scope: string;
};

type DataConnection = {
  id: string;
  provider_name: string;
  business_location_id: string;
  business_location_name?: string | null;
  campaign_id: string;
  campaign_name?: string | null;
  campaign_domain?: string | null;
  external_resource_id: string;
  external_resource_name?: string | null;
  resource_scope: string;
  status: string;
  last_success_at?: string | null;
  next_sync_at?: string | null;
  last_error_message?: string | null;
  source_truth: string;
  website_event_key_configured?: boolean;
  website_event_key_created_at?: string | null;
};

type WebsiteEventKey = {
  token: string;
  event_path: string;
  created_at: string;
};

type ConnectionsPayload = {
  google_oauth: {
    connected: boolean;
    approved_access?: {
      search_console: boolean;
      business_profile: boolean;
      website_analytics: boolean;
    };
    updated_at?: string | null;
  };
  connections: DataConnection[];
  health: ConnectionHealth;
};

type ConnectionHealthItem = {
  id: string;
  connection_id?: string | null;
  provider_name: string;
  label: string;
  status: string;
  display_state: "healthy" | "updating" | "needs_attention" | "needs_setup";
  summary: string;
  location_id: string;
  location_name: string;
  campaign_id: string;
  campaign_name: string;
  last_success_at?: string | null;
  newest_usable_data_date?: string | null;
  current_failure?: string | null;
  affected_features: string[];
  recovery_action: {
    kind: "none" | "wait" | "reconnect" | "map" | "sync";
    label: string;
    href?: string | null;
    connection_id?: string;
  };
};

type ConnectionHealth = {
  checked_at: string;
  summary: {
    headline: string;
    next_step: string;
    locations: number;
    sources: number;
    healthy: number;
    updating: number;
    needs_attention: number;
    needs_setup: number;
  };
  items: ConnectionHealthItem[];
};

type UsageAllowance = {
  plan: {
    code: string;
    name: string;
    monthly_price: number;
    included_locations: number;
    active_locations: number;
    remaining_locations: number;
    location_allowance_enforced?: boolean;
    additional_locations_require_custom_terms: boolean;
  };
  period: {
    start: string;
    end: string;
    resets_at: string;
  };
  credits: {
    name: string;
    monthly: number;
    used: number;
    reserved: number;
    remaining: number;
    percent_committed: number;
    warning_level?: number | null;
    blocked: boolean;
  };
  connected_account_actions: number;
  recovery_actions: string[];
  recent_activity: Array<{
    id: string;
    label: string;
    result: string;
    credits: number;
    state: "completed" | "reserved" | "returned" | "connected_account";
    created_at: string;
  }>;
  action_prices: Array<{
    code: string;
    label: string;
    result: string;
    credits: number;
    price_type: "up_to" | "per_item" | "fixed_ceiling";
  }>;
  important_note: string;
  commercial_catalog_version: string;
  capabilities: Array<{
    code: string;
    label: string;
    summary: string;
    available: boolean;
    required_plan: string;
  }>;
  external_automation?: {
    plan_eligible: boolean;
    gateway_enabled: boolean;
    automatic_actions_enabled: false;
    required_plan: string;
    state: "plan_upgrade_required" | "gateway_not_available" | "available";
    summary: string;
    planned_connection_options: string[];
    outbound_contract?: {
      schema_version: string;
      connection_setup_enabled: boolean;
      delivery_enabled: boolean;
      supported_events: Array<{
        code: string;
        label: string;
        summary: string;
      }>;
    };
  };
  upgrade?: {
    plan_code: string;
    plan_name: string;
    monthly_price: number;
    headline: string;
    reasons: string[];
  } | null;
};

type BillingSummary = {
  provider_configured: boolean;
  plan_code: string;
  plan_name: string;
  status: string;
  status_label: string;
  portal_available: boolean;
  checkout_available: boolean;
  available_checkout_plans: string[];
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  recovery_message?: string | null;
  checkout_confirmation?: {
    client_request_id?: string | null;
    session_id?: string | null;
    requested_plan_code?: string | null;
    checkout_completed: boolean;
    subscription_active: boolean;
  } | null;
  pending_checkout?: {
    client_request_id: string | null;
    session_id: string | null;
    requested_plan_code: string | null;
    expires_at: string | null;
    active: boolean;
  } | null;
};

type AutomationMonthlyDeliveryUsage = {
  period_start: string;
  period_end: string;
  total_events: number;
  product_events: number;
  test_events: number;
  attempts: number;
  accepted: number;
  waiting_or_retrying: number;
  needs_recovery: number;
  stopped: number;
  usage_only: true;
  allowance_enforced: false;
};

type AutomationDelivery = {
  id: string;
  event_id: string;
  event_type: string;
  status: "pending" | "delivered" | "failed" | "dead_letter" | "cancelled";
  delivery_kind: "test" | "product";
  attempt_count: number;
  max_attempts: number;
  recovery_count: number;
  last_reason_code?: string | null;
  last_response_status?: number | null;
  last_attempt_at?: string | null;
  delivered_at?: string | null;
  next_attempt_at?: string | null;
  dead_lettered_at?: string | null;
  can_retry: boolean;
  can_recover: boolean;
  job_status?: string | null;
};

type AutomationConnection = {
  id: string;
  name: string;
  provider: "zapier" | "make" | "pipedream" | "n8n";
  provider_label: string;
  status: "pending" | "active" | "unhealthy" | "paused" | "disconnected";
  endpoint_host: string;
  event_types: string[];
  verification_status: "not_tested" | "verified" | "failed";
  signing_secret_version: number;
  last_tested_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  paused_at?: string | null;
  destination_url_saved: boolean;
  destination_url_revealed: false;
  last_delivery?: AutomationDelivery | null;
  dead_letter_count: number;
  recoverable_deliveries: AutomationDelivery[];
  automatic_delivery_enabled: boolean;
  automatic_actions_enabled: false;
  monthly_delivery_usage: AutomationMonthlyDeliveryUsage;
  conformance_proof: {
    state: "not_tested" | "test_accepted" | "product_event_accepted" | "needs_attention";
    label: string;
    summary: string;
    evidence_at?: string | null;
    production_proven: boolean;
  };
};

type AutomationStarterRecipe = {
  code: string;
  version: "insightos.automation.recipes.v1";
  label: string;
  summary: string;
  external_result: string;
  event_types: string[];
  outbound_only: true;
  human_approval_preserved: true;
  automatic_actions_enabled: false;
};

type AutomationProviderSetup = {
  code: "zapier" | "make" | "pipedream" | "n8n";
  version: "insightos.automation.provider-setup.v3";
  label: string;
  webhook_source: string;
  production_url_note: string;
  setup_steps: string[];
  official_docs_url: string;
  account_note: string;
  test_confirmation: string;
  recovery_note: string;
  payload_path: string;
  headers_path: string;
  route_field: string;
  workflow_steps: string[];
  field_map: Array<{ source: string; purpose: string }>;
  signature_contract: {
    algorithm: "HMAC-SHA256";
    signature_header: "X-InsightOS-Signature";
    timestamp_header: "X-InsightOS-Timestamp";
    event_id_header: "X-InsightOS-Event-ID";
    signed_input: "{timestamp}.{exact_raw_request_body}";
    signature_prefix: "v1=";
    replay_window_seconds: 300;
  };
  template_status: "connection_kit_ready";
  customer_account_required: true;
  customer_supplies_webhook_url: true;
  signed_events_required: true;
  inbound_actions_enabled: false;
};

type AutomationConnectionsPayload = {
  items: AutomationConnection[];
  monthly_delivery_usage: AutomationMonthlyDeliveryUsage;
  supported_providers: Array<{ code: "zapier" | "make" | "pipedream" | "n8n"; label: string }>;
  supported_events: Array<{ code: string; label: string; summary: string }>;
  live_event_types: string[];
  recipe_catalog_version: "insightos.automation.recipes.v1";
  starter_recipes: AutomationStarterRecipe[];
  provider_setup_version: "insightos.automation.provider-setup.v3";
  provider_setup: AutomationProviderSetup[];
  automatic_actions_enabled: false;
  truth: string;
};

type AutomationServiceAccount = {
  id: string;
  name: string;
  status: "active" | "revoked";
  location_id: string;
  location_name: string;
  location_ids: string[];
  location_count: number;
  allowed_commands: Array<"report.retrieve" | "report.generate_saved" | "recommendation.retrieve" | "recommendation.request_review" | "connection.refresh_saved" | "listing.check_public" | "content.create_working_draft" | "content.request_draft_review" | "review.retrieve" | "review.create_response_draft">;
  token_hint: string;
  token_version: number;
  expires_at: string;
  last_used_at?: string | null;
  last_rotated_at?: string | null;
  created_at: string;
  revoked_at?: string | null;
  command_count: number;
  token_revealed: false;
};

type AutomationConnectorCatalog = {
  version: "insightos.automation.connectors.v1";
  truth: { state: "compatibility_only"; summary: string };
  items: Array<{
    code: "zapier" | "make" | "n8n" | "pipedream" | "https";
    name: string;
    setup: string;
    setup_steps: [string, string, string, string];
    authentication: "Private Bearer credential";
    connection_guide_available: true;
    openapi_import_available: true;
    conformance_check_available: true;
    customer_connection_required: true;
    production_connection_proven: false;
    starter_available: boolean;
  }>;
};

function isAutomationConformanceProvider(
  code: AutomationConnectorCatalog["items"][number]["code"],
): code is "zapier" | "make" | "n8n" | "pipedream" {
  return code !== "https";
}

type AutomationCommandReceipt = {
  id: string;
  schema_version: "insightos.automation.command.v1";
  command_type: "report.retrieve" | "report.generate_saved" | "recommendation.retrieve" | "recommendation.request_review" | "connection.refresh_saved" | "listing.check_public" | "content.create_working_draft" | "content.request_draft_review" | "review.retrieve" | "review.create_response_draft";
  idempotency_key: string;
  correlation_id: string;
  location_id: string;
  status: "succeeded" | "denied";
  denial_reason_code?: string | null;
  result: {
    message: string;
    resource?: { type: "report" | "recommendation"; id: string; href: string } | null;
    artifacts: Array<{ id: string; type: string; ready: boolean; download_path?: string }>;
  };
  created_at: string;
  completed_at: string;
};

type AutomationConformanceKit = {
  version: "insightos.automation.conformance.v1";
  provider: "zapier" | "make" | "pipedream" | "n8n";
  provider_label: string;
  test_only: true;
  cannot_enable_live_delivery: true;
  fixture_signing_secret: string;
  request: {
    method: "POST";
    content_type: "application/json";
    headers: Record<string, string>;
    exact_raw_body: string;
    parsed_body: Record<string, unknown>;
  };
  provider_paths: { payload: string; headers: string; route_field: string };
  expected: Record<string, string | boolean>;
  checks: string[];
  safety: {
    contains_customer_data: false;
    contains_live_credentials: false;
    inbound_actions_enabled: false;
    message: string;
  };
};

type PrivateAIProviderConnection = {
  id: string;
  name: string;
  status: "candidate";
  endpoint_host: string;
  model_identifier: string;
  credential_configured: boolean;
  billing_boundary?: {
    cost_responsibility: "customer";
    platform_billing_enabled: false;
    summary: string;
  };
  validation_status: "not_tested" | "failed" | "passed";
  network_validation_status: "not_tested" | "failed" | "passed";
  last_validation_reason?: string | null;
  last_validation_latency_ms?: number | null;
  activation_status: "inactive";
  automatic_activation_allowed: false;
  capability_catalog_version?: string;
  supported_capabilities?: Array<{
    code: string;
    label: string;
    summary: string;
    output_boundary: string;
    fixed_canary_percentage: 5;
    shared_workspace_prompt_limit_per_day: 1;
    separate_qualification_required: true;
    owner_approval_required: true;
    managed_fallback_required: true;
    automatic_rollback: true;
    automatic_changes_allowed: false;
    publishing_allowed: false;
  }>;
  last_validated_at?: string | null;
  candidate_only: true;
};

type PrivateAIProviderBenchmark = {
  id: string;
  connection_id: string;
  benchmark_version: string;
  status: "passed" | "failed";
  case_count: 3;
  passed_case_count: number;
  median_latency_ms: number;
  reported_input_tokens: number;
  reported_output_tokens: number;
  case_results: Array<{
    case_id: "evidence_selection" | "control_integrity" | "uncertainty_truth";
    passed: boolean;
    reason_code: string;
    latency_ms: number;
  }>;
  created_at: string;
  eligible_for_owner_review: boolean;
  routing_enabled: false;
  automatic_activation_allowed: false;
};

type PrivateAIProviderReview = {
  id: string;
  connection_id: string;
  benchmark_id: string;
  decision: "approved_for_future_activation" | "rejected";
  reviewed_at: string;
  immutable: true;
  eligible_for_later_standby_activation: boolean;
  activation_status: "inactive";
  routing_enabled: false;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
};

type PrivateAIReviewAcknowledgements = {
  reviewed_synthetic_results: boolean;
  understands_not_active: boolean;
  understands_managed_fallback_required: boolean;
  understands_no_automatic_changes: boolean;
};

type PrivateAIStandbyAcknowledgements = {
  reviewed_standby_boundary: boolean;
  understands_zero_customer_prompts: boolean;
  understands_managed_route_unchanged: boolean;
  understands_manual_disable_available: boolean;
};

type PrivateAIStandbyState = {
  state: "inactive" | "standby" | "standby_elsewhere" | "unavailable";
  connection_id?: string | null;
  summary: string;
  routing_mode?: "zero_traffic_standby" | "inactive";
  traffic_percentage: 0;
  customer_prompts_allowed: false;
  automatic_changes_allowed: false;
  managed_route_unchanged: true;
};

type PrivateAIRoutingReadiness = {
  id: string;
  status: "passed" | "blocked";
  managed_route_status: "healthy" | "stale" | "unavailable" | "not_configured";
  managed_evidence_at?: string | null;
  standby_evidence_current: boolean;
  rollback_ready: boolean;
  blockers: Array<{ code: string; summary: string }>;
  usage: {
    window_days: 30;
    managed_runs: number;
    managed_successes: number;
    managed_fallbacks: number;
    managed_input_tokens: number;
    managed_output_tokens: number;
    candidate_runs: 0;
  };
  traffic_percentage: 0;
  routing_enabled: false;
  customer_prompts_allowed: false;
  automatic_changes_allowed: false;
  created_at: string;
  immutable: true;
};

type PrivateAIReadinessState = {
  latest: PrivateAIRoutingReadiness | null;
  truth: {
    state: "not_checked" | "ready_for_later_routing_review" | "needs_attention" | "unavailable";
    summary: string;
  };
};

type PrivateAICanaryAcknowledgements = {
  reviewed_five_percent_limit: boolean;
  understands_real_customer_prompt: boolean;
  understands_managed_fallback_required: boolean;
  understands_automatic_rollback: boolean;
  understands_no_automatic_changes: boolean;
};

type PrivateAICanaryState = {
  state: "inactive" | "canary" | "canary_elsewhere" | "needs_attention" | "unavailable";
  routing_enabled: boolean;
  feature: "intelligence_brief";
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  customer_prompts_allowed: boolean;
  automatic_rollback_enabled: true;
  automatic_changes_allowed: false;
  usage: {
    window_days: 30;
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
    input_tokens: number;
    output_tokens: number;
  };
  truth: { state: string; summary: string };
};

type PrivateAICanaryMonitoringState = {
  state: "not_started" | "collecting" | "eligible_for_later_review" | "blocked" | "unavailable";
  latest: {
    id: string;
    status: "collecting" | "eligible_for_later_review" | "blocked";
    created_at: string;
    immutable: true;
  } | null;
  evidence: {
    window_days: 30;
    required_success_days: 3;
    max_latency_threshold_ms: 8000;
    private_successes: number;
    distinct_success_days: number;
    successful_days_remaining: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
    max_latency_ms: number;
    blockers: Array<{ code: string; summary: string }>;
    evidence_only: true;
  };
  traffic_change_allowed: false;
  capability_change_allowed: false;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
  truth: { state: string; summary: string };
};

type PrivateAIQuestionCapabilityAcknowledgements = {
  reviewed_question_capability_check: boolean;
  understands_real_customer_questions: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_no_automatic_changes: boolean;
};

type PrivateAIQuestionCapabilityState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "intelligence_question";
  customer_label: "Saved-evidence questions";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  daily_limit_shared_with_explanations: true;
  customer_prompts_allowed: boolean;
  automatic_rollback_enabled: true;
  automatic_changes_allowed: false;
  usage: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  truth: { state: string; summary: string };
};

type PrivateAIDraftCapabilityAcknowledgements = {
  reviewed_draft_capability_check: boolean;
  understands_real_saved_action_context: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_draft_only_no_publish: boolean;
};

type PrivateAIDraftCapabilityState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "intelligence_draft";
  customer_label: "Saved-action draft wording";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  daily_limit_shared_with_explanations_and_questions: true;
  customer_prompts_allowed: boolean;
  automatic_rollback_enabled: true;
  automatic_changes_allowed: false;
  draft_only: true;
  publishing_allowed: false;
  usage: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  truth: { state: string; summary: string };
};

type PrivateAIKeywordReviewAcknowledgements = {
  reviewed_keyword_review_check: boolean;
  understands_real_saved_search_context: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_saved_search_classification_only: boolean;
};

type PrivateAIKeywordReviewQualificationState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_later_review" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "keyword_relevance_review";
  customer_label: "Unclear search review";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    saved_searches_changed: false;
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  daily_limit_shared_with_explanations_questions_and_drafts: true;
  customer_prompts_allowed: boolean;
  owner_activation_available: boolean;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
  saved_searches_changed: false;
  classification_only: true;
  may_update_reviewed_saved_searches: boolean;
  may_add_or_track_searches: false;
  publishing_allowed: false;
  automatic_rollback_enabled: true;
  usage: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  qualification_only: boolean;
  truth: { state: string; summary: string };
};

type PrivateAIContentDraftQualificationState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_later_review" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "content_draft_suggestion";
  customer_label: "Optional website draft wording";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    owner_drafts_changed: false;
    publishing_allowed: false;
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  daily_limit_shared_with_other_private_ai: true;
  customer_prompts_allowed: boolean;
  owner_activation_available: boolean;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
  owner_drafts_changed: false;
  suggestion_only: true;
  may_edit_or_publish: false;
  publishing_allowed: false;
  automatic_rollback_enabled: true;
  usage: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  qualification_only: boolean;
  truth: { state: string; summary: string };
};

type PrivateAIContentDraftAcknowledgements = {
  reviewed_content_draft_check: boolean;
  understands_real_saved_website_draft_context: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_suggestion_only_no_edit_or_publish: boolean;
};

type PrivateAIBaselineQualificationState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_later_review" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "onboarding_baseline_narrative";
  customer_label: "Optional baseline explanation";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    explanation_only: true;
    scores_changed: false;
    diagnosis_changed: false;
    fixes_changed: false;
    website_changes_allowed: false;
    immutable: true;
  } | null;
  current: {
    id: string;
    connection_id: string;
    action: "enabled" | "disabled" | "automatic_rollback";
    state: "capability_canary" | "inactive";
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day: 1;
  daily_limit_shared_with_other_private_ai: true;
  customer_prompts_allowed: boolean;
  owner_activation_available: boolean;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
  explanation_only: true;
  scores_changed: false;
  diagnosis_changed: false;
  fixes_changed: false;
  website_changes_allowed: false;
  automatic_rollback_enabled: true;
  usage: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  qualification_only: boolean;
  truth: { state: string; summary: string };
};

type PrivateAIBaselineAcknowledgements = {
  reviewed_baseline_check: boolean;
  understands_real_saved_baseline_context: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_explanation_only_no_changes: boolean;
};

type PrivateAIReviewResponseQualificationState = {
  state: "needs_qualification" | "qualification_failed" | "eligible_for_later_review" | "eligible_for_owner_approval" | "capability_canary" | "capability_canary_elsewhere" | "needs_attention" | "unavailable";
  capability: "review_response_draft";
  customer_label: "Optional review reply wording";
  latest_benchmark: {
    id: string;
    status: "passed" | "failed";
    reason_code: string;
    latency_ms: number;
    customer_prompt_sent: false;
    routing_enabled: false;
    draft_only: true;
    customer_review_sent: false;
    review_status_changed: false;
    may_post_response: false;
    publishing_allowed: false;
    immutable: true;
  } | null;
  current?: {
    id: string;
    connection_id: string;
    action: "enabled" | "disabled" | "automatic_rollback";
    state: "capability_canary" | "inactive";
    immutable: true;
  } | null;
  routing_enabled: boolean;
  traffic_percentage: 0 | 5;
  max_prompts_per_day?: 1;
  daily_limit_shared_with_other_private_ai?: true;
  customer_prompts_allowed: boolean;
  owner_activation_available: boolean;
  automatic_activation_allowed: false;
  automatic_changes_allowed: false;
  draft_only: true;
  customer_review_sent: false;
  review_status_changed: false;
  may_post_response: false;
  publishing_allowed: false;
  automatic_rollback_enabled?: true;
  usage?: {
    private_attempts: number;
    private_successes: number;
    managed_fallbacks: number;
    automatic_rollbacks: number;
  };
  qualification_only: boolean;
  truth: { state: string; summary: string };
};

type PrivateAIReviewResponseAcknowledgements = {
  reviewed_review_reply_check: boolean;
  understands_real_saved_review_context: boolean;
  understands_shared_daily_limit: boolean;
  understands_managed_fallback_and_rollback: boolean;
  understands_draft_only_no_posting: boolean;
};

type PrivateAIRelayEnrollment = {
  id: string;
  name: string;
  protocol_version: "outbound-local-relay-v1";
  status: "active" | "revoked";
  connection_state: "waiting_for_first_check" | "connected" | "needs_reconnect" | "revoked";
  token_hint: string;
  heartbeat_count: number;
  last_seen_at?: string | null;
  created_at: string;
  revoked_at?: string | null;
  customer_prompts_allowed: false;
  decision_packets_enabled: false;
  database_access_allowed: false;
  execution_allowed: false;
  publishing_allowed: false;
};

type PrivateAIRelayAcknowledgements = {
  understands_connection_only: boolean;
  understands_no_customer_prompts: boolean;
  understands_no_database_or_execution_access: boolean;
  understands_manual_revocation: boolean;
};

type PrivateAIRelayDiagnostic = {
  id: string;
  protocol_version: "outbound-local-relay-packet-v1";
  kind: "synthetic_connection_challenge";
  state: "waiting_for_relay" | "verified" | "expired";
  created_at: string;
  expires_at: string;
  acknowledged_at?: string | null;
  synthetic_only: true;
  customer_data_included: false;
  model_execution_requested: false;
  database_access_requested: false;
  business_execution_requested: false;
  publishing_requested: false;
};

type PrivateAIRelayRuntimeDiscovery = {
  id: string;
  agent_version: string;
  runtime_kind: "not_found" | "ollama" | "lm_studio" | "multiple";
  model_count: number;
  ollama_detected: boolean;
  lm_studio_detected: boolean;
  observed_at: string;
  received_at: string;
  loopback_only: true;
  customer_data_sent: false;
  model_called: false;
  model_identifiers_included: false;
};

type PrivateAIRelayModelQualification = {
  id: string;
  agent_version: string;
  runtime_kind: "ollama" | "lm_studio";
  prompt_version: "local-model-synthetic-v1";
  status: "passed" | "failed";
  latency_ms: number;
  output_json_valid: boolean;
  required_contract_matched: boolean;
  observed_at: string;
  received_at: string;
  synthetic_input_only: true;
  model_call_attempted: true;
  model_response_received: boolean;
  customer_data_sent: false;
  raw_model_identifier_sent: false;
  model_output_sent: false;
  customer_work_allowed: false;
  publishing_allowed: false;
};

type BillingCheckoutAttempt = {
  organizationId: string;
  planCode: string;
  clientRequestId: string;
  createdAt: number;
  expiresAt?: string | null;
};

type BillingConfirmationState =
  | "idle"
  | "checking"
  | "processing"
  | "confirmed"
  | "timed_out";

const BILLING_CHECKOUT_ATTEMPT_KEY = "insightos:billing-checkout-attempt:v1";
const BILLING_CHECKOUT_ATTEMPT_MAX_AGE_MS = 2 * 60 * 60 * 1000;
const BILLING_CONFIRMATION_DELAYS_MS = [0, 1000, 1500, 2000, 2500, 3000, 3500, 4000] as const;

const EMPTY_PRIVATE_AI_ACKNOWLEDGEMENTS: PrivateAIReviewAcknowledgements = {
  reviewed_synthetic_results: false,
  understands_not_active: false,
  understands_managed_fallback_required: false,
  understands_no_automatic_changes: false,
};

const EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS: PrivateAIStandbyAcknowledgements = {
  reviewed_standby_boundary: false,
  understands_zero_customer_prompts: false,
  understands_managed_route_unchanged: false,
  understands_manual_disable_available: false,
};

const EMPTY_PRIVATE_AI_CANARY_ACKNOWLEDGEMENTS: PrivateAICanaryAcknowledgements = {
  reviewed_five_percent_limit: false,
  understands_real_customer_prompt: false,
  understands_managed_fallback_required: false,
  understands_automatic_rollback: false,
  understands_no_automatic_changes: false,
};

const EMPTY_PRIVATE_AI_QUESTION_ACKNOWLEDGEMENTS: PrivateAIQuestionCapabilityAcknowledgements = {
  reviewed_question_capability_check: false,
  understands_real_customer_questions: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_no_automatic_changes: false,
};

const EMPTY_PRIVATE_AI_DRAFT_ACKNOWLEDGEMENTS: PrivateAIDraftCapabilityAcknowledgements = {
  reviewed_draft_capability_check: false,
  understands_real_saved_action_context: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_draft_only_no_publish: false,
};

const EMPTY_PRIVATE_AI_KEYWORD_REVIEW_ACKNOWLEDGEMENTS: PrivateAIKeywordReviewAcknowledgements = {
  reviewed_keyword_review_check: false,
  understands_real_saved_search_context: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_saved_search_classification_only: false,
};

const EMPTY_PRIVATE_AI_CONTENT_DRAFT_ACKNOWLEDGEMENTS: PrivateAIContentDraftAcknowledgements = {
  reviewed_content_draft_check: false,
  understands_real_saved_website_draft_context: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_suggestion_only_no_edit_or_publish: false,
};

const EMPTY_PRIVATE_AI_BASELINE_ACKNOWLEDGEMENTS: PrivateAIBaselineAcknowledgements = {
  reviewed_baseline_check: false,
  understands_real_saved_baseline_context: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_explanation_only_no_changes: false,
};

const EMPTY_PRIVATE_AI_REVIEW_RESPONSE_ACKNOWLEDGEMENTS: PrivateAIReviewResponseAcknowledgements = {
  reviewed_review_reply_check: false,
  understands_real_saved_review_context: false,
  understands_shared_daily_limit: false,
  understands_managed_fallback_and_rollback: false,
  understands_draft_only_no_posting: false,
};

const EMPTY_PRIVATE_AI_RELAY_ACKNOWLEDGEMENTS: PrivateAIRelayAcknowledgements = {
  understands_connection_only: false,
  understands_no_customer_prompts: false,
  understands_no_database_or_execution_access: false,
  understands_manual_revocation: false,
};

function privateAIRequestId(prefix: string) {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`.slice(0, 64);
}

function safeSessionStorageGet(key: string) {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSessionStorageSet(key: string, value: string) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Checkout can still continue when the browser blocks session storage.
  }
}

function safeSessionStorageRemove(key: string) {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Removing optional checkout recovery state must never block the page.
  }
}

function readBillingCheckoutAttempt(organizationId: string) {
  const raw = safeSessionStorageGet(BILLING_CHECKOUT_ATTEMPT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<BillingCheckoutAttempt>;
    if (
      parsed.organizationId !== organizationId ||
      typeof parsed.planCode !== "string" ||
      typeof parsed.clientRequestId !== "string" ||
      typeof parsed.createdAt !== "number" ||
      (typeof parsed.expiresAt === "string"
        ? !Number.isFinite(Date.parse(parsed.expiresAt)) || Date.parse(parsed.expiresAt) <= Date.now()
        : Date.now() - parsed.createdAt > BILLING_CHECKOUT_ATTEMPT_MAX_AGE_MS)
    ) {
      safeSessionStorageRemove(BILLING_CHECKOUT_ATTEMPT_KEY);
      return null;
    }
    return parsed as BillingCheckoutAttempt;
  } catch {
    safeSessionStorageRemove(BILLING_CHECKOUT_ATTEMPT_KEY);
    return null;
  }
}

function billingAttemptFromPending(
  organizationId: string,
  pending: BillingSummary["pending_checkout"],
) {
  if (
    !pending?.active
    || !pending.client_request_id
    || !pending.requested_plan_code
    || !pending.expires_at
  ) {
    return null;
  }
  return {
    organizationId,
    planCode: pending.requested_plan_code,
    clientRequestId: pending.client_request_id,
    createdAt: Date.now(),
    expiresAt: pending.expires_at,
  } satisfies BillingCheckoutAttempt;
}

function reconcileBillingCheckoutAttempt(
  organizationId: string,
  summary: BillingSummary,
) {
  const serverAttempt = billingAttemptFromPending(organizationId, summary.pending_checkout);
  if (serverAttempt) return saveBillingCheckoutAttempt(serverAttempt);
  clearBillingCheckoutAttempt(organizationId);
  return null;
}

function saveBillingCheckoutAttempt(attempt: BillingCheckoutAttempt) {
  safeSessionStorageSet(BILLING_CHECKOUT_ATTEMPT_KEY, JSON.stringify(attempt));
  return attempt;
}

function checkoutAttemptForPlan(organizationId: string, planCode: string) {
  const saved = readBillingCheckoutAttempt(organizationId);
  if (saved?.planCode === planCode) return saved;
  return saveBillingCheckoutAttempt({
    organizationId,
    planCode,
    clientRequestId: crypto.randomUUID(),
    createdAt: Date.now(),
  });
}

function clearBillingCheckoutAttempt(organizationId: string) {
  const saved = readBillingCheckoutAttempt(organizationId);
  if (saved?.organizationId === organizationId) {
    safeSessionStorageRemove(BILLING_CHECKOUT_ATTEMPT_KEY);
  }
}

function waitForBillingConfirmation(delayMs: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, delayMs));
}

type MigrationReview = {
  mode: "dry_run";
  adapter: string;
  review_hash: string;
  source_sha256: string;
  writes_performed: number;
  next_step: string;
  summary: {
    total_rows: number;
    ready: number;
    already_saved: number;
    duplicates_in_file: number;
    needs_attention: number;
    locations: number;
    keywords: number;
    competitors: number;
    ranking_history: number;
    listing_history: number;
    report_recipients: number;
  };
  ignored_columns: Array<{
    column: string;
    populated_rows: number;
    reason: string;
  }>;
  rows: Array<{
    row_number: number;
    record_type: string;
    location_name: string;
    status: "ready" | "already_saved" | "duplicate" | "needs_attention";
    detail: string;
    matched_location_name?: string | null;
    values: Record<string, string>;
    issues: Array<{ code: string; message: string }>;
  }>;
  pagination?: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
    has_more: boolean;
  };
};

type MigrationUpload = {
  id: string;
  status: "uploading" | "reviewed" | "applied";
  total_chunks: number;
  received_chunks: number;
  received_chunk_indexes: number[];
  expected_sha256?: string | null;
  review_hash?: string | null;
  expires_at: string;
};

type MigrationBatch = {
  id: string;
  source_system: string;
  source_filename?: string | null;
  status: "applied" | "rolled_back";
  applied_at: string;
  rolled_back_at?: string | null;
  rollback_available: boolean;
  summary: MigrationReview["summary"] & {
    records_applied?: number;
    locations_created?: number;
    keywords_created?: number;
    competitors_created?: number;
    ranking_history_created?: number;
    listing_history_created?: number;
    report_recipients_created?: number;
  };
};

type DataExport = {
  id: string;
  status: "ready" | "failed" | "expired";
  format: "json";
  schema_version: string;
  record_counts: Record<string, number>;
  artifact_sha256?: string | null;
  artifact_byte_size?: number | null;
  failure_code?: string | null;
  requested_at: string;
  completed_at?: string | null;
  downloaded_at?: string | null;
  expires_at: string;
  download_available: boolean;
};

type ProviderDisconnectPreview = {
  provider_name: "google";
  connected: boolean;
  credential_present: boolean;
  connections_total: number;
  active_connections: number;
  affected_locations: number;
  preserved_record_counts: Record<string, number>;
  what_stops: string[];
  what_stays: string[];
  confirmation_text: string;
};

type ProviderDisconnectRecord = {
  id: string;
  provider_name: "google";
  status: "completed" | "completed_external_action_required";
  credential_deleted: boolean;
  external_revocation_status: "confirmed" | "not_confirmed" | "not_needed";
  external_revocation_code?: string | null;
  connections_disconnected: number;
  queued_jobs_cancelled: number;
  preserved_record_counts: Record<string, number>;
  requested_at: string;
  completed_at?: string | null;
};

type OrganizationClosureRecord = {
  id: string;
  status: "recovery_window" | "on_hold" | "cancelled" | "ready_for_verified_deletion";
  hold_status: "clear" | "active";
  action_counts: Record<string, number>;
  requested_at: string;
  recovery_until: string;
  cancelled_at?: string | null;
  closed_at?: string | null;
  deletion_ready_at?: string | null;
  deletion_authorized: boolean;
  deletion_authorization_version: string;
  deletion_authorized_at: string | null;
  can_cancel: boolean;
  primary_data_deleted: false;
};

type OrganizationClosurePreview = {
  organization_name: string;
  organization_status: string;
  recovery_days: number;
  active_legal_hold: boolean;
  can_request: boolean;
  blockers: Array<{ code: string; message: string }>;
  affected_counts: Record<string, number>;
  what_stops: string[];
  what_stays: string[];
  confirmation_text: string;
  confirmation_steps: 2;
  required_acknowledgements: string[];
  current_request?: OrganizationClosureRecord | null;
};

const primaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-accent-500/40 bg-accent-500/15 px-4 py-2 text-sm font-semibold text-white transition hover:border-accent-500/70 hover:bg-accent-500/25 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass =
  "inline-flex items-center justify-center rounded-md border border-[#303137] bg-[#17181b] px-3.5 py-2 text-sm font-medium text-zinc-100 transition hover:bg-[#1d1e22] disabled:cursor-not-allowed disabled:opacity-50";
const selectClass =
  "w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2.5 text-sm text-white outline-none transition focus:border-accent-500/60 disabled:opacity-50";

function formatTimestamp(value?: string | null) {
  if (!value) return "Not synced yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function privateAIBenchmarkCaseLabel(caseId: PrivateAIProviderBenchmark["case_results"][number]["case_id"]) {
  return {
    evidence_selection: "Uses only the evidence provided",
    control_integrity: "Keeps owner approval controls",
    uncertainty_truth: "Does not invent missing measurements",
  }[caseId];
}

function formatDataDate(value?: string | null) {
  if (!value) return "No usable data saved yet";
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function healthStatusLabel(item: ConnectionHealthItem) {
  if (item.display_state === "healthy") return "Healthy";
  if (item.display_state === "updating") return "Updating";
  if (item.display_state === "needs_attention") return "Needs attention";
  return "Finish setup";
}

function healthTone(item: ConnectionHealthItem) {
  if (item.display_state === "healthy") return "success";
  if (item.display_state === "needs_attention") return "danger";
  return item.display_state === "needs_setup" ? "warning" : "info";
}

function formatResetDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "next month";
  return new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric" }).format(parsed);
}

function toneClasses(tone: string) {
  if (tone === "success") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (tone === "danger") return "border-rose-500/25 bg-rose-500/10 text-rose-100";
  if (tone === "warning") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-sky-500/25 bg-sky-500/10 text-sky-100";
}

function formatFileSize(value?: number | null) {
  if (!value || value < 1) return "Size unavailable";
  if (value < 1024) return `${value} bytes`;
  return `${(value / 1024).toFixed(value >= 1024 * 100 ? 0 : 1)} KB`;
}

const migrationChunkBytes = 500 * 1024;
const resumableMigrationThreshold = 1_200_000;

async function sha256Text(value: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function splitMigrationChunks(value: string) {
  const encoder = new TextEncoder();
  const chunks: string[] = [];
  let start = 0;
  while (start < value.length) {
    let low = start + 1;
    let high = Math.min(value.length, start + migrationChunkBytes);
    let best = low;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      const candidate = value.slice(start, middle);
      if (encoder.encode(candidate).byteLength <= migrationChunkBytes) {
        best = middle;
        low = middle + 1;
      } else {
        high = middle - 1;
      }
    }
    if (
      best < value.length &&
      /[\uD800-\uDBFF]/.test(value.charAt(best - 1)) &&
      /[\uDC00-\uDFFF]/.test(value.charAt(best))
    ) {
      best -= 1;
    }
    chunks.push(value.slice(start, best));
    start = best;
  }
  return chunks;
}

export default function SettingsPage() {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [payload, setPayload] = useState<ConnectionsPayload | null>(null);
  const [usageAllowance, setUsageAllowance] = useState<UsageAllowance | null>(null);
  const [automationConnections, setAutomationConnections] = useState<AutomationConnection[]>([]);
  const [automationMonthlyUsage, setAutomationMonthlyUsage] =
    useState<AutomationMonthlyDeliveryUsage | null>(null);
  const [automationProviders, setAutomationProviders] = useState<AutomationConnectionsPayload["supported_providers"]>([]);
  const [automationEvents, setAutomationEvents] = useState<AutomationConnectionsPayload["supported_events"]>([]);
  const [automationRecipes, setAutomationRecipes] = useState<AutomationStarterRecipe[]>([]);
  const [automationProviderSetup, setAutomationProviderSetup] = useState<AutomationProviderSetup[]>([]);
  const [automationWorkflowDirection, setAutomationWorkflowDirection] =
    useState<"outgoing" | "incoming">("outgoing");
  const [automationSelectedRecipe, setAutomationSelectedRecipe] = useState("");
  const [automationName, setAutomationName] = useState("");
  const [automationProvider, setAutomationProvider] = useState<"zapier" | "make" | "pipedream" | "n8n">("zapier");
  const [automationDestination, setAutomationDestination] = useState("");
  const [automationSelectedEvents, setAutomationSelectedEvents] = useState<string[]>([]);
  const [automationSigningSecret, setAutomationSigningSecret] = useState("");
  const [automationConnectionReadyToTest, setAutomationConnectionReadyToTest] = useState("");
  const [automationServiceAccounts, setAutomationServiceAccounts] = useState<AutomationServiceAccount[]>([]);
  const [automationConnectorCatalog, setAutomationConnectorCatalog] = useState<AutomationConnectorCatalog | null>(null);
  const [automationCommandProvider, setAutomationCommandProvider] =
    useState<AutomationConnectorCatalog["items"][number]["code"]>("zapier");
  const [automationCommandHistory, setAutomationCommandHistory] = useState<AutomationCommandReceipt[]>([]);
  const [automationCommandLoadState, setAutomationCommandLoadState] = useState<"idle" | "ready" | "unavailable">("idle");
  const [automationCommandName, setAutomationCommandName] = useState("Saved report workflow");
  const [automationCommandLocationId, setAutomationCommandLocationId] = useState("");
  const [automationCommandAdditionalLocationIds, setAutomationCommandAdditionalLocationIds] = useState<string[]>([]);
  const [automationCommandToken, setAutomationCommandToken] = useState("");
  const [privateAIProviders, setPrivateAIProviders] = useState<PrivateAIProviderConnection[]>([]);
  const [privateAIProviderLoadState, setPrivateAIProviderLoadState] = useState<"idle" | "ready" | "unavailable">("idle");
  const [privateAIBenchmarks, setPrivateAIBenchmarks] = useState<Record<string, PrivateAIProviderBenchmark[]>>({});
  const [privateAIReviews, setPrivateAIReviews] = useState<Record<string, PrivateAIProviderReview[]>>({});
  const [privateAIStandby, setPrivateAIStandby] = useState<Record<string, PrivateAIStandbyState>>({});
  const [privateAIReadiness, setPrivateAIReadiness] = useState<Record<string, PrivateAIReadinessState>>({});
  const [privateAICanary, setPrivateAICanary] = useState<Record<string, PrivateAICanaryState>>({});
  const [privateAICanaryMonitoring, setPrivateAICanaryMonitoring] = useState<Record<string, PrivateAICanaryMonitoringState>>({});
  const [privateAIQuestionCapability, setPrivateAIQuestionCapability] = useState<Record<string, PrivateAIQuestionCapabilityState>>({});
  const [privateAIDraftCapability, setPrivateAIDraftCapability] = useState<Record<string, PrivateAIDraftCapabilityState>>({});
  const [privateAIKeywordReviewQualification, setPrivateAIKeywordReviewQualification] = useState<Record<string, PrivateAIKeywordReviewQualificationState>>({});
  const [privateAIContentDraftQualification, setPrivateAIContentDraftQualification] = useState<Record<string, PrivateAIContentDraftQualificationState>>({});
  const [privateAIBaselineQualification, setPrivateAIBaselineQualification] = useState<Record<string, PrivateAIBaselineQualificationState>>({});
  const [privateAIReviewResponseQualification, setPrivateAIReviewResponseQualification] = useState<Record<string, PrivateAIReviewResponseQualificationState>>({});
  const [privateAIName, setPrivateAIName] = useState("");
  const [privateAIEndpoint, setPrivateAIEndpoint] = useState("");
  const [privateAIModel, setPrivateAIModel] = useState("");
  const [privateAIApiKey, setPrivateAIApiKey] = useState("");
  const [privateAIReviewAcks, setPrivateAIReviewAcks] = useState<Record<string, PrivateAIReviewAcknowledgements>>({});
  const [privateAIStandbyAcks, setPrivateAIStandbyAcks] = useState<Record<string, PrivateAIStandbyAcknowledgements>>({});
  const [privateAICanaryAcks, setPrivateAICanaryAcks] = useState<Record<string, PrivateAICanaryAcknowledgements>>({});
  const [privateAIQuestionAcks, setPrivateAIQuestionAcks] = useState<Record<string, PrivateAIQuestionCapabilityAcknowledgements>>({});
  const [privateAIDraftAcks, setPrivateAIDraftAcks] = useState<Record<string, PrivateAIDraftCapabilityAcknowledgements>>({});
  const [privateAIKeywordReviewAcks, setPrivateAIKeywordReviewAcks] = useState<Record<string, PrivateAIKeywordReviewAcknowledgements>>({});
  const [privateAIContentDraftAcks, setPrivateAIContentDraftAcks] = useState<Record<string, PrivateAIContentDraftAcknowledgements>>({});
  const [privateAIBaselineAcks, setPrivateAIBaselineAcks] = useState<Record<string, PrivateAIBaselineAcknowledgements>>({});
  const [privateAIReviewResponseAcks, setPrivateAIReviewResponseAcks] = useState<Record<string, PrivateAIReviewResponseAcknowledgements>>({});
  const [privateAIRelay, setPrivateAIRelay] = useState<PrivateAIRelayEnrollment | null>(null);
  const [privateAIRelayLoadState, setPrivateAIRelayLoadState] = useState<"idle" | "ready" | "unavailable">("idle");
  const [privateAIRelayName, setPrivateAIRelayName] = useState("Office local model");
  const [privateAIRelayToken, setPrivateAIRelayToken] = useState("");
  const [privateAIRelayAcks, setPrivateAIRelayAcks] = useState<PrivateAIRelayAcknowledgements>(EMPTY_PRIVATE_AI_RELAY_ACKNOWLEDGEMENTS);
  const [privateAIRelayDiagnostic, setPrivateAIRelayDiagnostic] = useState<PrivateAIRelayDiagnostic | null>(null);
  const [privateAIRelayRuntime, setPrivateAIRelayRuntime] = useState<PrivateAIRelayRuntimeDiscovery | null>(null);
  const [privateAIRelayQualification, setPrivateAIRelayQualification] = useState<PrivateAIRelayModelQualification | null>(null);
  const [billingSummary, setBillingSummary] = useState<BillingSummary | null>(null);
  const [authSessions, setAuthSessions] = useState<AuthSessionSummary[] | null>(null);
  const [billingConfirmationState, setBillingConfirmationState] =
    useState<BillingConfirmationState>("idle");
  const [pendingBillingPlanCode, setPendingBillingPlanCode] = useState("");
  const [pendingBillingClientRequestId, setPendingBillingClientRequestId] = useState("");
  const [pendingBillingSessionId, setPendingBillingSessionId] = useState("");
  const billingConfirmationRun = useRef(0);
  const [resources, setResources] = useState<SearchConsoleResource[]>([]);
  const [resourceDrafts, setResourceDrafts] = useState<Record<string, string>>({});
  const [profileResources, setProfileResources] = useState<BusinessProfileResource[]>([]);
  const [profileDrafts, setProfileDrafts] = useState<Record<string, string>>({});
  const [analyticsResources, setAnalyticsResources] = useState<AnalyticsResource[]>([]);
  const [analyticsDrafts, setAnalyticsDrafts] = useState<Record<string, string>>({});
  const [websiteEventKeys, setWebsiteEventKeys] = useState<Record<string, WebsiteEventKey>>({});
  const [loading, setLoading] = useState(true);
  const [loadingResources, setLoadingResources] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [guidedConnectionSetup, setGuidedConnectionSetup] = useState(false);
  const [migrationSource, setMigrationSource] = useState<"semrush" | "brightlocal" | "other">("other");
  const [migrationCsv, setMigrationCsv] = useState("");
  const [migrationFileName, setMigrationFileName] = useState("");
  const [migrationReview, setMigrationReview] = useState<MigrationReview | null>(null);
  const [migrationConfirmed, setMigrationConfirmed] = useState(false);
  const [migrationRequestId, setMigrationRequestId] = useState("");
  const [migrationBatch, setMigrationBatch] = useState<MigrationBatch | null>(null);
  const [migrationHistory, setMigrationHistory] = useState<MigrationBatch[]>([]);
  const [migrationUploadId, setMigrationUploadId] = useState("");
  const [migrationUploadProgress, setMigrationUploadProgress] = useState(0);
  const [migrationFileFingerprint, setMigrationFileFingerprint] = useState("");
  const [dataExports, setDataExports] = useState<DataExport[]>([]);
  const [googleDisconnectPreview, setGoogleDisconnectPreview] = useState<ProviderDisconnectPreview | null>(null);
  const [providerDisconnects, setProviderDisconnects] = useState<ProviderDisconnectRecord[]>([]);
  const [showGoogleDisconnect, setShowGoogleDisconnect] = useState(false);
  const [googleDisconnectConfirmation, setGoogleDisconnectConfirmation] = useState("");
  const [closurePreview, setClosurePreview] = useState<OrganizationClosurePreview | null>(null);
  const [closureHistory, setClosureHistory] = useState<OrganizationClosureRecord[]>([]);
  const [closureReviewStep, setClosureReviewStep] = useState<0 | 1 | 2>(0);
  const [closureConfirmation, setClosureConfirmation] = useState("");
  const [closureExportChoiceAcknowledged, setClosureExportChoiceAcknowledged] = useState(false);
  const [closureRecoveryAcknowledged, setClosureRecoveryAcknowledged] = useState(false);

  useEffect(() => {
    setGuidedConnectionSetup(
      new URLSearchParams(window.location.search).get("setup") === "connections",
    );
  }, []);

  const organizationId = me?.organization_id || "";
  const manageableCampaigns = useMemo(
    () => campaigns.filter((campaign) => Boolean(campaign.business_location_id)),
    [campaigns],
  );
  const automationCommandLocations = useMemo(
    () => Array.from(
      new Map(
        manageableCampaigns.map((campaign) => [
          campaign.business_location_id as string,
          {
            id: campaign.business_location_id as string,
            label: campaign.name || campaign.domain || "Saved location",
          },
        ]),
      ).values(),
    ),
    [manageableCampaigns],
  );
  const connections = useMemo(() => payload?.connections || [], [payload?.connections]);
  const connectionHealth = payload?.health || null;
  const connectionItemsNeedingWork = useMemo(
    () => (connectionHealth?.items || []).filter((item) => item.display_state !== "healthy"),
    [connectionHealth],
  );
  const healthyConnectionItems = useMemo(
    () => (connectionHealth?.items || []).filter((item) => item.display_state === "healthy"),
    [connectionHealth],
  );
  const searchConsoleConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_search_console"),
    [connections],
  );
  const profileConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_business_profile"),
    [connections],
  );
  const analyticsConnections = useMemo(
    () => connections.filter((connection) => connection.provider_name === "google_analytics"),
    [connections],
  );
  const connectionByCampaign = useMemo(
    () => new Map(searchConsoleConnections.map((connection) => [connection.campaign_id, connection])),
    [searchConsoleConnections],
  );
  const profileConnectionByCampaign = useMemo(
    () => new Map(profileConnections.map((connection) => [connection.campaign_id, connection])),
    [profileConnections],
  );
  const analyticsConnectionByCampaign = useMemo(
    () => new Map(analyticsConnections.map((connection) => [connection.campaign_id, connection])),
    [analyticsConnections],
  );
  const websiteMappingsComplete =
    manageableCampaigns.length > 0 &&
    manageableCampaigns.every((campaign) => connectionByCampaign.has(campaign.id));
  const profileMappingsComplete =
    manageableCampaigns.length > 0 &&
    manageableCampaigns.every((campaign) => profileConnectionByCampaign.has(campaign.id));
  const guidedStepsComplete = [
    Boolean(payload?.google_oauth.connected),
    websiteMappingsComplete,
    Boolean(payload?.google_oauth.approved_access?.business_profile) && profileMappingsComplete,
  ].filter(Boolean).length;

  useEffect(() => {
    if (
      !automationCommandLocationId &&
      automationCommandLocations.length > 0
    ) {
      setAutomationCommandLocationId(automationCommandLocations[0].id);
    }
  }, [automationCommandLocationId, automationCommandLocations]);

  function scrollToConnectionStep(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const loadConnections = useCallback(async (orgId: string) => {
    const next = (await platformApi(
      `/organizations/${orgId}/data-connections`,
      { method: "GET" },
    )) as ConnectionsPayload;
    setPayload(next);
    setResourceDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_search_console",
      )) {
        if (!seeded[connection.campaign_id]) {
          seeded[connection.campaign_id] = connection.external_resource_id;
        }
      }
      return seeded;
    });
    setProfileDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_business_profile",
      )) {
        if (!seeded[connection.campaign_id]) {
          seeded[connection.campaign_id] = connection.external_resource_id;
        }
      }
      return seeded;
    });
    setAnalyticsDrafts((current) => {
      const seeded = { ...current };
      for (const connection of (next.connections || []).filter(
        (item) => item.provider_name === "google_analytics",
      )) {
        if (!seeded[connection.campaign_id]) {
          seeded[connection.campaign_id] = connection.external_resource_id;
        }
      }
      return seeded;
    });
    return next;
  }, []);

  const loadProfileResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-business-profile/resources`,
        { method: "GET" },
      )) as { resources?: BusinessProfileResource[] };
      setProfileResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no business listings were returned. Confirm that this Google account manages the listing.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Google business listings.");
    } finally {
      setLoadingResources(false);
    }
  }, []);

  const loadResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-search-console/resources`,
        { method: "GET" },
      )) as { resources?: SearchConsoleResource[] };
      setResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no Search Console websites were returned. Confirm that this Google account has access to the website.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Search Console websites.");
    } finally {
      setLoadingResources(false);
    }
  }, []);

  const loadAnalyticsResources = useCallback(async (orgId: string) => {
    setLoadingResources(true);
    setError("");
    try {
      const response = (await platformApi(
        `/organizations/${orgId}/data-connections/google-analytics/resources`,
        { method: "GET" },
      )) as { resources?: AnalyticsResource[] };
      setAnalyticsResources(response.resources || []);
      if ((response.resources || []).length === 0) {
        setNotice(
          "Google is connected, but no website analytics properties were returned. Confirm that this Google account can view the correct property.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load website analytics properties.");
    } finally {
      setLoadingResources(false);
    }
  }, []);

  const loadAutomationConnections = useCallback(async () => {
    const response = (await platformApi("/automation/connections", {
      method: "GET",
    })) as AutomationConnectionsPayload;
    setAutomationConnections(response.items || []);
    setAutomationMonthlyUsage(response.monthly_delivery_usage || null);
    setAutomationProviders(response.supported_providers || []);
    setAutomationEvents(response.supported_events || []);
    setAutomationRecipes(response.starter_recipes || []);
    setAutomationProviderSetup(response.provider_setup || []);
    setAutomationSelectedEvents((current) =>
      current.length > 0 ? current : (response.supported_events || []).map((item) => item.code),
    );
    return response;
  }, []);

  const loadAutomationCommandAccess = useCallback(async () => {
    try {
      const [accountResponse, historyResponse, connectorCatalog] = await Promise.all([
        platformApi("/automation/service-accounts", { method: "GET" }) as Promise<{
          items?: AutomationServiceAccount[];
        }>,
        platformApi("/automation/command-history", { method: "GET" }) as Promise<{
          items?: Array<{ receipt: AutomationCommandReceipt }>;
        }>,
        (platformApi("/automation/connector-catalog", { method: "GET" }) as Promise<AutomationConnectorCatalog>)
          .catch(() => null),
      ]);
      setAutomationServiceAccounts(accountResponse.items || []);
      setAutomationCommandHistory(
        (historyResponse.items || []).map((item) => item.receipt),
      );
      setAutomationConnectorCatalog(connectorCatalog);
      setAutomationCommandLoadState("ready");
      return accountResponse;
    } catch (error) {
      setAutomationCommandLoadState("unavailable");
      throw error;
    }
  }, []);

  const loadPrivateAIProviders = useCallback(async () => {
    const response = (await platformApi("/ai/providers", {
      method: "GET",
    })) as { items?: PrivateAIProviderConnection[] };
    const items = response.items || [];
    const details = await Promise.all(
      items.map(async (provider) => {
        const [benchmarkResponse, reviewResponse, standbyResponse, readinessResponse, canaryResponse, monitoringResponse, questionCapabilityResponse, draftCapabilityResponse, keywordReviewQualificationResponse, contentDraftQualificationResponse, baselineQualificationResponse, reviewResponseQualificationResponse] = await Promise.all([
          (platformApi(`/ai/providers/${provider.id}/benchmarks`, {
            method: "GET",
          }) as Promise<{ items?: PrivateAIProviderBenchmark[] }>).catch(() => ({ items: [] })),
          (platformApi(`/ai/providers/${provider.id}/reviews`, {
            method: "GET",
          }) as Promise<{ items?: PrivateAIProviderReview[] }>).catch(() => ({ items: [] })),
          (platformApi(`/ai/providers/${provider.id}/standby`, {
            method: "GET",
          }) as Promise<{ current?: PrivateAIStandbyState }>).catch(() => ({
            current: {
              state: "unavailable" as const,
              summary: "Standby status could not be checked.",
              traffic_percentage: 0 as const,
              customer_prompts_allowed: false as const,
              automatic_changes_allowed: false as const,
              managed_route_unchanged: true as const,
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/routing-readiness`, {
            method: "GET",
          }) as Promise<{
            latest?: PrivateAIRoutingReadiness | null;
            truth?: PrivateAIReadinessState["truth"];
          }>).catch(() => ({
            latest: null,
            truth: {
              state: "unavailable" as const,
              summary: "Routing safety status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/routing-canary`, {
            method: "GET",
          }) as Promise<PrivateAICanaryState>).catch(() => ({
            state: "unavailable" as const,
            routing_enabled: false,
            feature: "intelligence_brief" as const,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            customer_prompts_allowed: false,
            automatic_rollback_enabled: true as const,
            automatic_changes_allowed: false as const,
            usage: {
              window_days: 30 as const,
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
              input_tokens: 0,
              output_tokens: 0,
            },
            truth: {
              state: "unavailable",
              summary: "Limited routing status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/routing-canary-monitoring`, {
            method: "GET",
          }) as Promise<PrivateAICanaryMonitoringState>).catch(() => ({
            state: "unavailable" as const,
            latest: null,
            evidence: {
              window_days: 30 as const,
              required_success_days: 3 as const,
              max_latency_threshold_ms: 8000 as const,
              private_successes: 0,
              distinct_success_days: 0,
              successful_days_remaining: 3,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
              max_latency_ms: 0,
              blockers: [],
              evidence_only: true as const,
            },
            traffic_change_allowed: false as const,
            capability_change_allowed: false as const,
            automatic_activation_allowed: false as const,
            automatic_changes_allowed: false as const,
            truth: {
              state: "unavailable",
              summary: "Canary health history could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/question-capability`, {
            method: "GET",
          }) as Promise<PrivateAIQuestionCapabilityState>).catch(() => ({
            state: "unavailable" as const,
            capability: "intelligence_question" as const,
            customer_label: "Saved-evidence questions" as const,
            latest_benchmark: null,
            routing_enabled: false,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            daily_limit_shared_with_explanations: true as const,
            customer_prompts_allowed: false,
            automatic_rollback_enabled: true as const,
            automatic_changes_allowed: false as const,
            usage: {
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
            },
            truth: {
              state: "unavailable",
              summary: "Saved-question private-AI status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/draft-capability`, {
            method: "GET",
          }) as Promise<PrivateAIDraftCapabilityState>).catch(() => ({
            state: "unavailable" as const,
            capability: "intelligence_draft" as const,
            customer_label: "Saved-action draft wording" as const,
            latest_benchmark: null,
            routing_enabled: false,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            daily_limit_shared_with_explanations_and_questions: true as const,
            customer_prompts_allowed: false,
            automatic_rollback_enabled: true as const,
            automatic_changes_allowed: false as const,
            draft_only: true as const,
            publishing_allowed: false as const,
            usage: {
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
            },
            truth: {
              state: "unavailable",
              summary: "Draft-wording private-AI status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/keyword-review-capability`, {
            method: "GET",
          }) as Promise<PrivateAIKeywordReviewQualificationState>).catch(() => ({
            state: "unavailable" as const,
            capability: "keyword_relevance_review" as const,
            customer_label: "Unclear search review" as const,
            latest_benchmark: null,
            routing_enabled: false as const,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            daily_limit_shared_with_explanations_questions_and_drafts: true as const,
            customer_prompts_allowed: false as const,
            owner_activation_available: false as const,
            automatic_activation_allowed: false as const,
            automatic_changes_allowed: false as const,
            saved_searches_changed: false as const,
            classification_only: true as const,
            may_update_reviewed_saved_searches: false,
            may_add_or_track_searches: false as const,
            publishing_allowed: false as const,
            automatic_rollback_enabled: true as const,
            usage: {
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
            },
            qualification_only: true,
            truth: {
              state: "unavailable",
              summary: "Unclear-search private-AI status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/content-draft-capability`, {
            method: "GET",
          }) as Promise<PrivateAIContentDraftQualificationState>).catch(() => ({
            state: "unavailable" as const,
            capability: "content_draft_suggestion" as const,
            customer_label: "Optional website draft wording" as const,
            latest_benchmark: null,
            routing_enabled: false as const,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            daily_limit_shared_with_other_private_ai: true as const,
            customer_prompts_allowed: false as const,
            owner_activation_available: false as const,
            automatic_activation_allowed: false as const,
            automatic_changes_allowed: false as const,
            owner_drafts_changed: false as const,
            suggestion_only: true as const,
            may_edit_or_publish: false as const,
            publishing_allowed: false as const,
            automatic_rollback_enabled: true as const,
            usage: {
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
            },
            qualification_only: true as const,
            truth: {
              state: "unavailable",
              summary: "Website-draft private-AI status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/baseline-capability`, {
            method: "GET",
          }) as Promise<PrivateAIBaselineQualificationState>).catch(() => ({
            state: "unavailable" as const,
            capability: "onboarding_baseline_narrative" as const,
            customer_label: "Optional baseline explanation" as const,
            latest_benchmark: null,
            current: null,
            routing_enabled: false as const,
            traffic_percentage: 0 as const,
            max_prompts_per_day: 1 as const,
            daily_limit_shared_with_other_private_ai: true as const,
            customer_prompts_allowed: false as const,
            owner_activation_available: false as const,
            automatic_activation_allowed: false as const,
            automatic_changes_allowed: false as const,
            explanation_only: true as const,
            scores_changed: false as const,
            diagnosis_changed: false as const,
            fixes_changed: false as const,
            website_changes_allowed: false as const,
            automatic_rollback_enabled: true as const,
            usage: {
              private_attempts: 0,
              private_successes: 0,
              managed_fallbacks: 0,
              automatic_rollbacks: 0,
            },
            qualification_only: true as const,
            truth: {
              state: "unavailable",
              summary: "Baseline private-AI status could not be checked.",
            },
          })),
          (platformApi(`/ai/providers/${provider.id}/review-response-capability`, {
            method: "GET",
          }) as Promise<PrivateAIReviewResponseQualificationState>).catch(() => ({
            state: "unavailable" as const,
            capability: "review_response_draft" as const,
            customer_label: "Optional review reply wording" as const,
            latest_benchmark: null,
            routing_enabled: false as const,
            traffic_percentage: 0 as const,
            customer_prompts_allowed: false as const,
            owner_activation_available: false as const,
            automatic_activation_allowed: false as const,
            automatic_changes_allowed: false as const,
            draft_only: true as const,
            customer_review_sent: false as const,
            review_status_changed: false as const,
            may_post_response: false as const,
            publishing_allowed: false as const,
            qualification_only: true as const,
            truth: {
              state: "unavailable",
              summary: "Review-reply private-AI status could not be checked.",
            },
          })),
        ]);
        return {
          connectionId: provider.id,
          benchmarks: benchmarkResponse.items || [],
          reviews: reviewResponse.items || [],
          standby: standbyResponse.current,
          readiness: {
            latest: readinessResponse.latest || null,
            truth: readinessResponse.truth || {
              state: "not_checked" as const,
              summary: "Fallback readiness has not been checked yet.",
            },
          },
          canary: canaryResponse,
          monitoring: monitoringResponse,
          questionCapability: questionCapabilityResponse,
          draftCapability: draftCapabilityResponse,
          keywordReviewQualification: keywordReviewQualificationResponse,
          contentDraftQualification: contentDraftQualificationResponse,
          baselineQualification: baselineQualificationResponse,
          reviewResponseQualification: reviewResponseQualificationResponse,
        };
      }),
    );
    setPrivateAIProviders(items);
    setPrivateAIBenchmarks(
      Object.fromEntries(details.map((item) => [item.connectionId, item.benchmarks])),
    );
    setPrivateAIReviews(
      Object.fromEntries(details.map((item) => [item.connectionId, item.reviews])),
    );
    setPrivateAIStandby(
      Object.fromEntries(
        details.map((item) => [
          item.connectionId,
          item.standby || {
            state: "unavailable",
            summary: "Standby status could not be checked.",
            traffic_percentage: 0,
            customer_prompts_allowed: false,
            automatic_changes_allowed: false,
            managed_route_unchanged: true,
          },
        ]),
      ),
    );
    setPrivateAIReadiness(
      Object.fromEntries(details.map((item) => [item.connectionId, item.readiness])),
    );
    setPrivateAICanary(
      Object.fromEntries(details.map((item) => [item.connectionId, item.canary])),
    );
    setPrivateAICanaryMonitoring(
      Object.fromEntries(details.map((item) => [item.connectionId, item.monitoring])),
    );
    setPrivateAIQuestionCapability(
      Object.fromEntries(details.map((item) => [item.connectionId, item.questionCapability])),
    );
    setPrivateAIDraftCapability(
      Object.fromEntries(details.map((item) => [item.connectionId, item.draftCapability])),
    );
    setPrivateAIKeywordReviewQualification(
      Object.fromEntries(details.map((item) => [item.connectionId, item.keywordReviewQualification])),
    );
    setPrivateAIContentDraftQualification(
      Object.fromEntries(details.map((item) => [item.connectionId, item.contentDraftQualification])),
    );
    setPrivateAIBaselineQualification(
      Object.fromEntries(details.map((item) => [item.connectionId, item.baselineQualification])),
    );
    setPrivateAIReviewResponseQualification(
      Object.fromEntries(details.map((item) => [item.connectionId, item.reviewResponseQualification])),
    );
    setPrivateAIProviderLoadState("ready");
    return response;
  }, []);

  const loadPrivateAIRelay = useCallback(async () => {
    const response = (await platformApi("/ai/relay-enrollments", {
      method: "GET",
    })) as {
      current?: PrivateAIRelayEnrollment | null;
      diagnostic?: PrivateAIRelayDiagnostic | null;
      runtime_discovery?: PrivateAIRelayRuntimeDiscovery | null;
      model_qualification?: PrivateAIRelayModelQualification | null;
    };
    setPrivateAIRelay(response.current || null);
    setPrivateAIRelayDiagnostic(response.diagnostic || null);
    setPrivateAIRelayRuntime(response.runtime_discovery || null);
    setPrivateAIRelayQualification(response.model_qualification || null);
    setPrivateAIRelayLoadState("ready");
    return response;
  }, []);

  const createPrivateAIRelayDiagnostic = useCallback(async (enrollmentId: string) => {
    setBusyAction("private-ai-relay-diagnostic");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(`/ai/relay-enrollments/${enrollmentId}/diagnostic-packets`, {
        method: "POST",
        body: JSON.stringify({
          client_request_id: privateAIRequestId("local-relay-diagnostic"),
        }),
      })) as { item?: PrivateAIRelayDiagnostic; summary?: string };
      setPrivateAIRelayDiagnostic(response.item || null);
      setNotice(response.summary || "A short-lived signed connection check is waiting for the relay.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to prepare the signed relay check.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadPrivateAIRelayAgent = useCallback(async () => {
    setBusyAction("private-ai-relay-agent-download");
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile("/ai/relay-enrollments/agent/download", {
        method: "GET",
      });
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = "insightos-local-relay.py";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The InsightOS local relay helper was downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download the local relay helper.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const createPrivateAIRelay = useCallback(async () => {
    setBusyAction("private-ai-relay-create");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/ai/relay-enrollments", {
        method: "POST",
        body: JSON.stringify({
          name: privateAIRelayName,
          client_request_id: privateAIRequestId("local-relay"),
          ...privateAIRelayAcks,
        }),
      })) as {
        enrollment_token?: string | null;
        item?: PrivateAIRelayEnrollment;
        summary?: string;
      };
      setPrivateAIRelayToken(response.enrollment_token || "");
      setPrivateAIRelay(response.item || null);
      setPrivateAIRelayLoadState("ready");
      setNotice(response.summary || "Local relay connection key created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the local relay connection key.");
    } finally {
      setBusyAction("");
    }
  }, [privateAIRelayAcks, privateAIRelayName]);

  const revokePrivateAIRelay = useCallback(async (enrollmentId: string) => {
    setBusyAction("private-ai-relay-revoke");
    setError("");
    setNotice("");
    try {
      await platformApi(`/ai/relay-enrollments/${enrollmentId}`, { method: "DELETE" });
      setPrivateAIRelayToken("");
      setPrivateAIRelayAcks(EMPTY_PRIVATE_AI_RELAY_ACKNOWLEDGEMENTS);
      setPrivateAIRelayDiagnostic(null);
      setPrivateAIRelayRuntime(null);
      setPrivateAIRelayQualification(null);
      await loadPrivateAIRelay();
      setNotice("Local relay connection revoked. Its saved key can no longer connect.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to revoke the local relay connection.");
    } finally {
      setBusyAction("");
    }
  }, [loadPrivateAIRelay]);

  const refreshPrivateAIProviders = useCallback(async () => {
    setBusyAction("private-ai-refresh");
    setError("");
    try {
      await loadPrivateAIProviders();
    } catch (err) {
      setPrivateAIProviderLoadState("unavailable");
      setError(err instanceof Error ? err.message : "Unable to check private AI candidates.");
    } finally {
      setBusyAction("");
    }
  }, [loadPrivateAIProviders]);

  const createPrivateAIProvider = useCallback(async () => {
    setBusyAction("private-ai-create");
    setError("");
    setNotice("");
    try {
      await platformApi("/ai/providers", {
        method: "POST",
        body: JSON.stringify({
          name: privateAIName,
          endpoint_url: privateAIEndpoint,
          model_identifier: privateAIModel,
          api_key: privateAIApiKey || null,
        }),
      });
      setPrivateAIName("");
      setPrivateAIEndpoint("");
      setPrivateAIModel("");
      setPrivateAIApiKey("");
      setNotice("Private AI candidate saved. It is inactive until every later review gate passes.");
      await loadPrivateAIProviders();
    } catch (err) {
      setPrivateAIApiKey("");
      setError(err instanceof Error ? err.message : "Unable to save this private AI candidate.");
    } finally {
      setBusyAction("");
    }
  }, [
    loadPrivateAIProviders,
    privateAIApiKey,
    privateAIEndpoint,
    privateAIModel,
    privateAIName,
  ]);

  const preflightPrivateAIProvider = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-preflight-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(`/ai/providers/${connectionId}/preflight`, {
          method: "POST",
        })) as { passed: boolean; summary: string };
        setNotice(response.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to check the provider network.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const validatePrivateAIProvider = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-validate-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(`/ai/providers/${connectionId}/validate`, {
          method: "POST",
        })) as { passed: boolean; summary: string };
        setNotice(response.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to validate the provider connection.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const benchmarkPrivateAIProvider = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(`/ai/providers/${connectionId}/benchmarks`, {
          method: "POST",
          body: JSON.stringify({
            client_request_id: privateAIRequestId("settings-benchmark"),
          }),
        })) as { item: PrivateAIProviderBenchmark; truth: { summary: string } };
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to run the provider quality checks.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const reviewPrivateAIProvider = useCallback(
    async (
      connectionId: string,
      benchmarkId: string,
      decision: "approved_for_future_activation" | "rejected",
    ) => {
      setBusyAction(`private-ai-review-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements =
          privateAIReviewAcks[benchmarkId] || EMPTY_PRIVATE_AI_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/benchmarks/${benchmarkId}/review`,
          {
            method: "PUT",
            body: JSON.stringify({ decision, ...acknowledgements }),
          },
        )) as { truth: { summary: string } };
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to save the owner review.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIReviewAcks],
  );

  const disconnectPrivateAIProvider = useCallback(
    async (connectionId: string) => {
      if (!window.confirm("Disconnect this private AI candidate and erase its saved endpoint credential?")) return;
      setBusyAction(`private-ai-disconnect-${connectionId}`);
      setError("");
      setNotice("");
      try {
        await platformApi(`/ai/providers/${connectionId}`, { method: "DELETE" });
        setNotice("Private AI candidate disconnected. Its endpoint credential was erased.");
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to disconnect this private AI candidate.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIStandby = useCallback(
    async (
      connectionId: string,
      reviewId: string | null,
      action: "enable" | "disable",
    ) => {
      setBusyAction(`private-ai-standby-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = reviewId
          ? privateAIStandbyAcks[reviewId] || EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS;
        const response = (await platformApi(`/ai/providers/${connectionId}/standby`, {
          method: "PUT",
          body: JSON.stringify({
            action,
            client_request_id: privateAIRequestId(`settings-standby-${action}`),
            review_id: reviewId,
            ...acknowledgements,
          }),
        })) as { truth: { summary: string } };
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to update zero-traffic standby.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIStandbyAcks],
  );

  const checkPrivateAIRoutingReadiness = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-readiness-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/routing-readiness`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-routing-readiness"),
            }),
          },
        )) as { truth: { summary: string } };
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check the managed fallback right now.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAICanary = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-canary-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAICanaryAcks[connectionId] || EMPTY_PRIVATE_AI_CANARY_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_CANARY_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/routing-canary`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-canary-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAICanaryState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to update the limited private-AI check.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAICanaryAcks],
  );

  const savePrivateAICanaryHealthReview = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-canary-monitoring-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/routing-canary-monitoring`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-canary-monitoring"),
            }),
          },
        )) as PrivateAICanaryMonitoringState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to save the private-AI health review.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const benchmarkPrivateAIQuestionCapability = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-question-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/question-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-question-check"),
            }),
          },
        )) as PrivateAIQuestionCapabilityState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to check saved-question compatibility.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIQuestionCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-question-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIQuestionAcks[connectionId] || EMPTY_PRIVATE_AI_QUESTION_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_QUESTION_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/question-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-question-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIQuestionCapabilityState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to update saved-question private AI.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIQuestionAcks],
  );

  const benchmarkPrivateAIDraftCapability = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-draft-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/draft-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-draft-check"),
            }),
          },
        )) as PrivateAIDraftCapabilityState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to check draft-wording compatibility.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIDraftCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-draft-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIDraftAcks[connectionId] || EMPTY_PRIVATE_AI_DRAFT_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_DRAFT_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/draft-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-draft-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIDraftCapabilityState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to update draft-wording private AI.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIDraftAcks],
  );

  const benchmarkPrivateAIKeywordReviewQualification = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-keyword-review-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/keyword-review-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-keyword-review-check"),
            }),
          },
        )) as PrivateAIKeywordReviewQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to check unclear-search compatibility.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIKeywordReviewCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-keyword-review-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIKeywordReviewAcks[connectionId]
            || EMPTY_PRIVATE_AI_KEYWORD_REVIEW_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_KEYWORD_REVIEW_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/keyword-review-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-keyword-review-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIKeywordReviewQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to update unclear-search private AI.");
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIKeywordReviewAcks],
  );

  const benchmarkPrivateAIContentDraftQualification = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-content-draft-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/content-draft-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-content-draft-check"),
            }),
          },
        )) as PrivateAIContentDraftQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check website-draft compatibility.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIContentDraftCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-content-draft-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIContentDraftAcks[connectionId]
            || EMPTY_PRIVATE_AI_CONTENT_DRAFT_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_CONTENT_DRAFT_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/content-draft-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-content-draft-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIContentDraftQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to update website-draft private AI.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIContentDraftAcks],
  );

  const benchmarkPrivateAIBaselineQualification = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-baseline-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/baseline-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-baseline-check"),
            }),
          },
        )) as PrivateAIBaselineQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check baseline-explanation compatibility.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const benchmarkPrivateAIReviewResponseQualification = useCallback(
    async (connectionId: string) => {
      setBusyAction(`private-ai-review-response-benchmark-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(
          `/ai/providers/${connectionId}/review-response-capability/benchmark`,
          {
            method: "POST",
            body: JSON.stringify({
              client_request_id: privateAIRequestId("settings-review-response-check"),
            }),
          },
        )) as PrivateAIReviewResponseQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check review-reply compatibility.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders],
  );

  const updatePrivateAIReviewResponseCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-review-response-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIReviewResponseAcks[connectionId]
            || EMPTY_PRIVATE_AI_REVIEW_RESPONSE_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_REVIEW_RESPONSE_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/review-response-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-review-response-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIReviewResponseQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to update review-reply private AI.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIReviewResponseAcks],
  );

  const updatePrivateAIBaselineCapability = useCallback(
    async (connectionId: string, action: "enable" | "disable") => {
      setBusyAction(`private-ai-baseline-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const acknowledgements = action === "enable"
          ? privateAIBaselineAcks[connectionId]
            || EMPTY_PRIVATE_AI_BASELINE_ACKNOWLEDGEMENTS
          : EMPTY_PRIVATE_AI_BASELINE_ACKNOWLEDGEMENTS;
        const response = (await platformApi(
          `/ai/providers/${connectionId}/baseline-capability`,
          {
            method: "PUT",
            body: JSON.stringify({
              action,
              client_request_id: privateAIRequestId(`settings-baseline-${action}`),
              ...acknowledgements,
            }),
          },
        )) as PrivateAIBaselineQualificationState;
        setNotice(response.truth.summary);
        await loadPrivateAIProviders();
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to update baseline-explanation private AI.",
        );
      } finally {
        setBusyAction("");
      }
    },
    [loadPrivateAIProviders, privateAIBaselineAcks],
  );

  const downloadAutomationConformanceKit = useCallback(async (
    requestedProvider?: "zapier" | "make" | "pipedream" | "n8n" | "https",
  ) => {
    if (requestedProvider === "https") return;
    const provider = requestedProvider || automationProvider;
    setBusyAction(`automation-conformance-${provider}`);
    setError("");
    setNotice("");
    try {
      const conformanceUrl = requestedProvider
        ? `/automation/conformance/${requestedProvider}`
        : `/automation/conformance/${automationProvider}`;
      const response = (await platformApi(
        conformanceUrl,
        { method: "GET" },
      )) as AutomationConformanceKit;
      const objectUrl = URL.createObjectURL(
        new Blob([JSON.stringify(response, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `insightos-${response.provider}-receiver-conformance-v1.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      setNotice(
        `${response.provider_label} receiver test contract downloaded. It contains synthetic data and a test-only secret.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download the receiver test contract.");
    } finally {
      setBusyAction("");
    }
  }, [automationProvider]);

  const createAutomationConnection = useCallback(async () => {
    setBusyAction("automation-create");
    setError("");
    setNotice("");
    setAutomationSigningSecret("");
    try {
      const response = (await platformApi("/automation/connections", {
        method: "POST",
        body: JSON.stringify({
          name: automationName,
          provider: automationProvider,
          destination_url: automationDestination,
          event_types: automationSelectedEvents,
        }),
      })) as {
        connection: AutomationConnection;
        signing_secret: string;
        secret_shown_once: true;
      };
      setAutomationSigningSecret(response.signing_secret);
      setAutomationConnectionReadyToTest(response.connection.id);
      setAutomationName("");
      setAutomationDestination("");
      setAutomationSelectedRecipe("");
      setNotice("Connection saved. Copy the signing secret now, then send a test event.");
      await loadAutomationConnections();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the automation connection.");
    } finally {
      setBusyAction("");
    }
  }, [
    automationDestination,
    automationName,
    automationProvider,
    automationSelectedEvents,
    loadAutomationConnections,
  ]);

  const testAutomationConnection = useCallback(
    async (connectionId: string) => {
      setBusyAction(`automation-test-${connectionId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(`/automation/connections/${connectionId}/test`, {
          method: "POST",
        })) as { received_by_destination: boolean };
        setNotice(
          response.received_by_destination
            ? "The workflow endpoint accepted the signed test event."
            : "The test was saved, but the workflow endpoint did not accept it.",
        );
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to send the test event.");
        await loadAutomationConnections().catch(() => undefined);
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const retryAutomationDelivery = useCallback(
    async (deliveryId: string) => {
      setBusyAction(`automation-retry-${deliveryId}`);
      setError("");
      setNotice("");
      try {
        const response = (await platformApi(`/automation/deliveries/${deliveryId}/retry`, {
          method: "POST",
        })) as { received_by_destination: boolean };
        setNotice(
          response.received_by_destination
            ? "The workflow endpoint accepted the retry."
            : "The retry was saved, but the workflow endpoint did not accept it.",
        );
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to retry this event.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const rotateAutomationSecret = useCallback(
    async (connectionId: string) => {
      if (!window.confirm("Replace the current signing secret? The old secret will stop working immediately.")) return;
      setBusyAction(`automation-rotate-${connectionId}`);
      setError("");
      setNotice("");
      setAutomationSigningSecret("");
      setAutomationConnectionReadyToTest("");
      try {
        const response = (await platformApi(`/automation/connections/${connectionId}/rotate-secret`, {
          method: "POST",
        })) as { signing_secret: string };
        setAutomationSigningSecret(response.signing_secret);
        setAutomationConnectionReadyToTest(connectionId);
        setNotice("Signing secret replaced. Copy the new secret now and update the workflow before testing.");
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to replace the signing secret.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const disconnectAutomationConnection = useCallback(
    async (connectionId: string) => {
      if (!window.confirm("Disconnect this workflow? Its saved URL and signing secret will be removed.")) return;
      setBusyAction(`automation-disconnect-${connectionId}`);
      setError("");
      setNotice("");
      try {
        await platformApi(`/automation/connections/${connectionId}`, { method: "DELETE" });
        setNotice("Workflow disconnected. Its saved URL and signing secret were removed.");
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to disconnect this workflow.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const setAutomationConnectionPaused = useCallback(
    async (connectionId: string, paused: boolean) => {
      const action = paused ? "pause" : "resume";
      setBusyAction(`automation-${action}-${connectionId}`);
      setError("");
      setNotice("");
      try {
        await platformApi(`/automation/connections/${connectionId}/${action}`, {
          method: "POST",
        });
        setNotice(
          paused
            ? "Automatic events paused. Saved history and connection details were preserved."
            : "Automatic events resumed. New subscribed events can be delivered again.",
        );
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : `Unable to ${action} this workflow.`);
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const recoverAutomationDelivery = useCallback(
    async (deliveryId: string) => {
      setBusyAction(`automation-recover-${deliveryId}`);
      setError("");
      setNotice("");
      try {
        await platformApi(`/automation/deliveries/${deliveryId}/recover`, {
          method: "POST",
        });
        setNotice("Recovery queued with three new bounded attempts. The original event ID is preserved.");
        await loadAutomationConnections();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to recover this event.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationConnections],
  );

  const copyAutomationSecret = useCallback(async () => {
    if (!automationSigningSecret) return;
    try {
      await navigator.clipboard.writeText(automationSigningSecret);
      setNotice("Workflow security key copied. It will not be shown again after you leave this page.");
    } catch {
      setNotice("Select and copy the workflow security key before leaving this page.");
    }
  }, [automationSigningSecret]);

  const createAutomationCommandAccess = useCallback(async () => {
    if (!automationCommandLocationId) return;
    setBusyAction("automation-command-create");
    setError("");
    setNotice("");
    setAutomationCommandToken("");
    try {
      const response = (await platformApi("/automation/service-accounts", {
        method: "POST",
        body: JSON.stringify({
          name: automationCommandName,
          location_id: automationCommandLocationId,
          additional_location_ids: automationCommandAdditionalLocationIds,
          expires_in_days: 30,
        }),
      })) as {
        token: string;
        token_shown_once: true;
        service_account: AutomationServiceAccount;
      };
      setAutomationCommandToken(response.token);
      setNotice(`Report access is ready for ${response.service_account.location_count} location${response.service_account.location_count === 1 ? "" : "s"}. Copy the workflow key now; it will not be shown again.`);
      await loadAutomationCommandAccess();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to create workflow access.");
    } finally {
      setBusyAction("");
    }
  }, [automationCommandAdditionalLocationIds, automationCommandLocationId, automationCommandName, loadAutomationCommandAccess]);

  const rotateAutomationCommandAccess = useCallback(
    async (serviceAccountId: string) => {
      if (!window.confirm("Replace this workflow key? The old key will stop working immediately.")) return;
      setBusyAction(`automation-command-rotate-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          { method: "POST" },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice("Workflow key replaced. Copy the new key now and update your workflow tool before testing again.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to replace the workflow key.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationCommandAccess],
  );

  const updateAutomationCommandLocations = useCallback(
    async (serviceAccount: AutomationServiceAccount, locationIds: string[]) => {
      const additionalLocationIds = locationIds.filter((item) => item !== serviceAccount.location_id);
      if (!window.confirm(
        `Replace the workflow key and allow saved-report retrieval for ${1 + additionalLocationIds.length} location${additionalLocationIds.length === 0 ? "" : "s"}? The old key will stop working immediately.`,
      )) return;
      setBusyAction(`automation-command-location-scope-${serviceAccount.id}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccount.id}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({ additional_location_ids: additionalLocationIds }),
          },
        )) as { token: string; token_shown_once: true; service_account: AutomationServiceAccount };
        setAutomationCommandToken(response.token);
        setNotice(`Saved-report access now covers ${response.service_account.location_count} location${response.service_account.location_count === 1 ? "" : "s"}. Copy the replacement key into your workflow tool now.`);
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change report location access.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationCommandAccess],
  );

  const setAutomationReportCreation = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool create private reports from results InsightOS has already saved? This replaces the workflow key. It will not run new checks, email anyone, or publish changes."
        : "Remove report-creation access? This replaces the workflow key, and saved-report retrieval will continue to work.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: Array.from(new Set([
                "report.retrieve",
                ...(enabled ? ["report.generate_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.retrieve")
                  ? ["recommendation.retrieve"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.request_review")
                  ? ["recommendation.request_review"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("connection.refresh_saved")
                  ? ["connection.refresh_saved"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("listing.check_public")
                  ? ["listing.check_public"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.create_working_draft")
                  ? ["content.create_working_draft"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.request_draft_review") ? ["content.request_draft_review"] : []),
                ...(currentAccount?.allowed_commands.includes("review.retrieve") ? ["review.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("review.create_response_draft") ? ["review.create_response_draft"] : []),
              ])),
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(
          enabled
            ? "Private report creation is on. Copy the replacement workflow key into your workflow tool now."
            : "Report creation is off. Copy the replacement read-only key into your workflow tool now.",
        );
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change workflow report access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationRecommendationAccess = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool read saved recommendations for this location? This replaces the workflow key. It cannot approve, schedule, execute, or publish the recommendation."
        : "Remove saved recommendation access? This replaces the workflow key; report access will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-recommendation-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.includes("report.generate_saved")
                  ? ["report.generate_saved"]
                  : []),
                ...(enabled ? ["recommendation.retrieve"] : []),
                ...(enabled ? ["recommendation.request_review"] : []),
                ...(currentAccount?.allowed_commands.includes("connection.refresh_saved")
                  ? ["connection.refresh_saved"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("listing.check_public")
                  ? ["listing.check_public"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.create_working_draft")
                  ? ["content.create_working_draft"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.request_draft_review") ? ["content.request_draft_review"] : []),
                ...(currentAccount?.allowed_commands.includes("review.retrieve") ? ["review.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("review.create_response_draft") ? ["review.create_response_draft"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Saved recommendation access is on. Copy the replacement workflow key into your workflow tool now."
          : "Saved recommendation access is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change saved recommendation access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationConnectionRefresh = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool ask InsightOS to refresh data from sources already connected to this location? This replaces the workflow key. It cannot add an account, change settings, publish, or run an unrelated action."
        : "Remove connected-source refresh access? This replaces the workflow key; report and recommendation access will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-refresh-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.includes("report.generate_saved") ? ["report.generate_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.retrieve") ? ["recommendation.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.request_review") ? ["recommendation.request_review"] : []),
                ...(enabled ? ["connection.refresh_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("listing.check_public")
                  ? ["listing.check_public"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.create_working_draft")
                  ? ["content.create_working_draft"]
                  : []),
                ...(currentAccount?.allowed_commands.includes("content.request_draft_review") ? ["content.request_draft_review"] : []),
                ...(currentAccount?.allowed_commands.includes("review.retrieve") ? ["review.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("review.create_response_draft") ? ["review.create_response_draft"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Connected-source refresh access is on. Copy the replacement workflow key into your workflow tool now."
          : "Connected-source refresh access is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change connected-source refresh access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationPublicListingCheck = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool start public business-listing inventory checks for this location? Each accepted check can use Insight Credits and the plan's daily allowance. This replaces the workflow key. It cannot correct listings, publish, or change your business profile."
        : "Remove public listing check access? This replaces the workflow key; other enabled workflow actions will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-listing-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.includes("report.generate_saved") ? ["report.generate_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.retrieve") ? ["recommendation.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.request_review") ? ["recommendation.request_review"] : []),
                ...(currentAccount?.allowed_commands.includes("connection.refresh_saved") ? ["connection.refresh_saved"] : []),
                ...(enabled ? ["listing.check_public"] : []),
                ...(currentAccount?.allowed_commands.includes("content.create_working_draft") ? ["content.create_working_draft"] : []),
                ...(currentAccount?.allowed_commands.includes("content.request_draft_review") ? ["content.request_draft_review"] : []),
                ...(currentAccount?.allowed_commands.includes("review.retrieve") ? ["review.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("review.create_response_draft") ? ["review.create_response_draft"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Public listing check access is on. Copy the replacement workflow key into your workflow tool now."
          : "Public listing check access is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change public listing check access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationWorkingDraftCreation = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool start a private working draft only after you have accepted its saved content brief? This replaces the workflow key. It creates an empty editable outline and cannot write AI copy, approve, schedule, publish, or change your website."
        : "Remove working-draft creation access? This replaces the workflow key; other enabled workflow actions will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-draft-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.includes("report.generate_saved") ? ["report.generate_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.retrieve") ? ["recommendation.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("recommendation.request_review") ? ["recommendation.request_review"] : []),
                ...(currentAccount?.allowed_commands.includes("connection.refresh_saved") ? ["connection.refresh_saved"] : []),
                ...(currentAccount?.allowed_commands.includes("listing.check_public") ? ["listing.check_public"] : []),
                ...(enabled ? ["content.create_working_draft", "content.request_draft_review"] : []),
                ...(currentAccount?.allowed_commands.includes("review.retrieve") ? ["review.retrieve"] : []),
                ...(currentAccount?.allowed_commands.includes("review.create_response_draft") ? ["review.create_response_draft"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Working-draft creation is on. Copy the replacement workflow key into your workflow tool now."
          : "Working-draft creation is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change working-draft access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationReviewRetrieval = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool route the rating, date, and reply state for one exact saved review? This replaces the workflow key. Reviewer names and comment text stay inside InsightOS, and the workflow cannot write or post a reply."
        : "Remove saved-review routing? This replaces the workflow key; other enabled workflow actions will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-review-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.filter((command) => (
                  command !== "report.retrieve" && command !== "review.retrieve"
                )) ?? []),
                ...(enabled ? ["review.retrieve"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Saved-review routing is on. Copy the replacement workflow key into your workflow tool now."
          : "Saved-review routing is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change saved-review routing.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const setAutomationReviewDraftCreation = useCallback(
    async (serviceAccountId: string, enabled: boolean) => {
      const currentAccount = automationServiceAccounts.find((item) => item.id === serviceAccountId);
      const warning = enabled
        ? "Let this workflow tool request a private reply draft for one exact saved review? This replaces the workflow key. Every draft stays inside InsightOS and still requires a person to review and approve it before anything can be posted."
        : "Remove private reply-draft access? This replaces the workflow key; saved-review routing and other enabled actions will continue.";
      if (!window.confirm(warning)) return;
      setBusyAction(`automation-command-review-draft-scope-${serviceAccountId}`);
      setError("");
      setNotice("");
      setAutomationCommandToken("");
      try {
        const response = (await platformApi(
          `/automation/service-accounts/${serviceAccountId}/rotate`,
          {
            method: "POST",
            body: JSON.stringify({
              allowed_commands: [
                "report.retrieve",
                ...(currentAccount?.allowed_commands.filter((command) => (
                  command !== "report.retrieve" && command !== "review.create_response_draft"
                )) ?? []),
                ...(enabled ? ["review.create_response_draft"] : []),
              ],
            }),
          },
        )) as { token: string; token_shown_once: true };
        setAutomationCommandToken(response.token);
        setNotice(enabled
          ? "Private reply drafting is on. Copy the replacement workflow key into your workflow tool now."
          : "Private reply drafting is off. Copy the replacement workflow key into your workflow tool now.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to change private reply-draft access.");
      } finally {
        setBusyAction("");
      }
    },
    [automationServiceAccounts, loadAutomationCommandAccess],
  );

  const revokeAutomationCommandAccess = useCallback(
    async (serviceAccountId: string) => {
      if (!window.confirm("Turn off this report connection? The workflow tool will lose access immediately, while its activity history stays saved.")) return;
      setBusyAction(`automation-command-revoke-${serviceAccountId}`);
      setError("");
      setNotice("");
      try {
        await platformApi(`/automation/service-accounts/${serviceAccountId}`, {
          method: "DELETE",
        });
        setAutomationCommandToken("");
        setNotice("Report access turned off. The workflow key no longer works.");
        await loadAutomationCommandAccess();
      } catch (error) {
        setError(error instanceof Error ? error.message : "Unable to turn off report access.");
      } finally {
        setBusyAction("");
      }
    },
    [loadAutomationCommandAccess],
  );

  const copyAutomationCommandToken = useCallback(async () => {
    if (!automationCommandToken) return;
    try {
      await navigator.clipboard.writeText(automationCommandToken);
      setNotice("Workflow key copied. Save it in your workflow tool before leaving this page.");
    } catch {
      setNotice("Select and copy the workflow key before leaving this page.");
    }
  }, [automationCommandToken]);

  const downloadN8nReportWorkflow = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/report-ready?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-report-ready.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive n8n starter workflow was downloaded. Import it, add the workflow key, then publish it when you are ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the n8n starter workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadAutomationConnectionGuide = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-guide-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/command-client-kit?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-automation-connection-guide.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The universal connection guide was downloaded. It works with Zapier, Make, n8n, Pipedream, and custom HTTPS tools, and it does not contain your workflow key.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the automation connection guide.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadAutomationOpenApi = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-openapi-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/command-openapi?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-automation-openapi.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The OpenAPI file was downloaded. Import it into a compatible automation builder, then add the workflow key in that tool's private credential settings.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the automation API file.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadN8nMonthlyReportWorkflow = useCallback(async (
    serviceAccountId: string,
    campaignId: string,
  ) => {
    setBusyAction(`automation-command-monthly-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/saved-report-schedule?service_account_id=${encodeURIComponent(serviceAccountId)}&campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-monthly-private-report.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive monthly-report workflow was downloaded. Import it, select the current workflow key, review its timezone, and publish it only when ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the monthly-report workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadN8nRecommendationWorkflow = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-recommendation-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/recommendation-ready?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-recommendation-ready.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive saved-recommendation workflow was downloaded. Import it, select the current workflow key, and publish only when ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the saved-recommendation workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadN8nContentDraftWorkflow = useCallback(async (
    serviceAccountId: string,
    campaignId: string,
  ) => {
    setBusyAction(`automation-command-content-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/content-draft-review?service_account_id=${encodeURIComponent(serviceAccountId)}&campaign_id=${encodeURIComponent(campaignId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-private-draft-review.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive private-draft workflow was downloaded. Replace the accepted brief ID, select the current workflow key, test manually, and activate it only when ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the private-draft workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadN8nSavedReviewWorkflow = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-review-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/saved-review-routing?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-saved-review-routing.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive saved-review workflow was downloaded. Import it, select the current workflow key, connect its Production URL to Review saved updates, and publish only when ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the saved-review workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const downloadN8nReviewDraftWorkflow = useCallback(async (serviceAccountId: string) => {
    setBusyAction(`automation-command-review-draft-template-${serviceAccountId}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/automation/starter-workflows/n8n/review-response-draft?service_account_id=${encodeURIComponent(serviceAccountId)}`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || "insightos-n8n-private-review-reply-drafts.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setNotice("The inactive private reply-draft workflow was downloaded. Import it, select the current workflow key, connect its Production URL to Review saved updates, test it, and publish only when ready.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to download the private reply-draft workflow.");
    } finally {
      setBusyAction("");
    }
  }, []);

  const loadAuthSessions = useCallback(async () => {
    const response = (await platformApi("/auth/sessions", {
      method: "GET",
    })) as { sessions?: AuthSessionSummary[] };
    setAuthSessions(response.sessions || []);
    return response;
  }, []);

  const confirmBillingReturn = useCallback(
    async (
      orgId: string,
      expectedPlanCode: string,
      expectedClientRequestId: string,
      expectedSessionId: string,
      initialSummary: BillingSummary | null = null,
    ) => {
      const runId = billingConfirmationRun.current + 1;
      billingConfirmationRun.current = runId;
      setPendingBillingPlanCode(expectedPlanCode);
      setPendingBillingClientRequestId(expectedClientRequestId);
      setPendingBillingSessionId(expectedSessionId);
      setBillingConfirmationState("checking");

      for (let index = 0; index < BILLING_CONFIRMATION_DELAYS_MS.length; index += 1) {
        const delayMs = BILLING_CONFIRMATION_DELAYS_MS[index];
        if (delayMs > 0) await waitForBillingConfirmation(delayMs);
        if (billingConfirmationRun.current !== runId) return;

        try {
          const nextSummary =
            index === 0 && initialSummary
              ? initialSummary
              : ((await platformApi("/billing/summary", {
                  method: "GET",
                })) as BillingSummary);
          if (billingConfirmationRun.current !== runId) return;
          setBillingSummary(nextSummary);

          const confirmation = nextSummary.checkout_confirmation;
          const expectedRequestMatches = Boolean(expectedClientRequestId)
            && confirmation?.client_request_id === expectedClientRequestId;
          const expectedSessionMatches = Boolean(expectedSessionId)
            && confirmation?.session_id === expectedSessionId;
          const expectedCheckoutMatches = expectedClientRequestId
            ? expectedRequestMatches
            : expectedSessionMatches;
          const confirmedRequestedPlan = confirmation?.requested_plan_code || "";
          const checkoutPlanMatches = expectedPlanCode
            ? confirmedRequestedPlan === expectedPlanCode
            : Boolean(confirmedRequestedPlan);
          const activePlanMatches = checkoutPlanMatches
            && nextSummary.plan_code === confirmedRequestedPlan;
          if (
            confirmation?.subscription_active === true
            && expectedCheckoutMatches
            && activePlanMatches
          ) {
            setBillingConfirmationState("confirmed");
            clearBillingCheckoutAttempt(orgId);
            const refreshedAllowance = await platformApi("/usage/credits", {
              method: "GET",
            }).catch(() => null);
            if (billingConfirmationRun.current === runId && refreshedAllowance) {
              setUsageAllowance(refreshedAllowance as UsageAllowance);
            }
            return;
          }

          if (
            confirmation?.checkout_completed === true
            && expectedCheckoutMatches
            && checkoutPlanMatches
          ) {
            setBillingConfirmationState("processing");
          }
        } catch {
          // A temporary read failure is retried within the same bounded confirmation window.
        }
      }

      if (billingConfirmationRun.current === runId) {
        setBillingConfirmationState("timed_out");
      }
    },
    [],
  );

  useEffect(
    () => () => {
      billingConfirmationRun.current += 1;
    },
    [],
  );

  useEffect(() => {
    async function loadPage() {
      setLoading(true);
      setError("");
      try {
        const currentUser = (await platformApi("/auth/me", { method: "GET" })) as Me;
        if (!currentUser.organization_id) {
          throw new Error("An organization is required to manage data connections.");
        }
        setMe(currentUser);
        const [campaignResponse, connectionResponse, allowanceResponse, billingResponse, migrationResponse, dataExportResponse, disconnectPreviewResponse, disconnectHistoryResponse, closurePreviewResponse, closureHistoryResponse, authSessionResponse] = await Promise.all([
          platformApi("/campaigns", { method: "GET" }) as Promise<{ items?: Campaign[] }>,
          loadConnections(currentUser.organization_id).catch((err) => {
            setError(
              err instanceof Error && err.message !== "Failed to fetch"
                ? err.message
                : "Google data connections could not be refreshed. Billing and automation settings are still available.",
            );
            return null;
          }),
          platformApi("/usage/credits", { method: "GET" }) as Promise<UsageAllowance>,
          (platformApi("/billing/summary", { method: "GET" }) as Promise<BillingSummary>)
            .catch(() => null),
          (platformApi(`/organizations/${currentUser.organization_id}/migration-imports`, {
            method: "GET",
          }) as Promise<{ items?: MigrationBatch[] }>).catch(() => ({ items: [] })),
          currentUser.org_role === "org_owner"
            ? ((platformApi(`/organizations/${currentUser.organization_id}/data-governance/exports`, {
                method: "GET",
              }) as Promise<{ items?: DataExport[] }>).catch(() => ({ items: [] })))
            : Promise.resolve({ items: [] as DataExport[] }),
          currentUser.org_role === "org_owner"
            ? ((platformApi(`/organizations/${currentUser.organization_id}/data-governance/provider-disconnects/google/preview`, {
                method: "GET",
              }) as Promise<{ preview?: ProviderDisconnectPreview }>).catch(() => ({ preview: undefined })))
            : Promise.resolve({ preview: undefined }),
          currentUser.org_role === "org_owner"
            ? ((platformApi(`/organizations/${currentUser.organization_id}/data-governance/provider-disconnects`, {
                method: "GET",
              }) as Promise<{ items?: ProviderDisconnectRecord[] }>).catch(() => ({ items: [] })))
            : Promise.resolve({ items: [] as ProviderDisconnectRecord[] }),
          currentUser.org_role === "org_owner"
            ? ((platformApi(`/organizations/${currentUser.organization_id}/data-governance/closures/preview`, {
                method: "GET",
              }) as Promise<{ preview?: OrganizationClosurePreview }>).catch(() => ({ preview: undefined })))
            : Promise.resolve({ preview: undefined }),
          currentUser.org_role === "org_owner"
            ? ((platformApi(`/organizations/${currentUser.organization_id}/data-governance/closures`, {
                method: "GET",
              }) as Promise<{ items?: OrganizationClosureRecord[] }>).catch(() => ({ items: [] })))
            : Promise.resolve({ items: [] as OrganizationClosureRecord[] }),
          loadAuthSessions().catch(() => null),
        ]);
        setCampaigns(campaignResponse.items || []);
        setUsageAllowance(allowanceResponse);
        await Promise.all([
          loadAutomationConnections().catch(() => undefined),
          loadAutomationCommandAccess().catch(() => undefined),
          currentUser.org_role === "org_owner"
            ? loadPrivateAIProviders().catch(() => {
                setPrivateAIProviderLoadState("unavailable");
                return undefined;
              })
            : Promise.resolve(undefined),
          currentUser.org_role === "org_owner"
            ? loadPrivateAIRelay().catch(() => {
                setPrivateAIRelayLoadState("unavailable");
                return undefined;
              })
            : Promise.resolve(undefined),
        ]);
        setBillingSummary(billingResponse);
        const localBillingAttempt = readBillingCheckoutAttempt(currentUser.organization_id);
        const serverBillingAttempt = billingResponse
          ? reconcileBillingCheckoutAttempt(currentUser.organization_id, billingResponse)
          : null;
        setMigrationHistory(migrationResponse.items || []);
        setDataExports(dataExportResponse.items || []);
        setGoogleDisconnectPreview(disconnectPreviewResponse.preview || null);
        setProviderDisconnects(disconnectHistoryResponse.items || []);
        setClosurePreview(closurePreviewResponse.preview || null);
        setClosureHistory(closureHistoryResponse.items || []);
        if (authSessionResponse === null) setAuthSessions(null);
        const returnParams = new URLSearchParams(window.location.search);
        const billingReturned = returnParams.get("billing");
        const returnedBillingSessionId = returnParams.get("session_id") || "";
        const googleReturned = returnParams.get("google");
        const returnSource = returnParams.get("source");
        if (billingReturned === "success") {
          const attempt = serverBillingAttempt || localBillingAttempt;
          setNotice("");
          window.history.replaceState({}, "", "/settings");
          void confirmBillingReturn(
            currentUser.organization_id,
            attempt?.planCode || "",
            attempt?.clientRequestId || "",
            returnedBillingSessionId,
            billingResponse,
          );
        } else if (billingReturned === "cancelled") {
          billingConfirmationRun.current += 1;
          setBillingConfirmationState("idle");
          setPendingBillingPlanCode("");
          setPendingBillingClientRequestId("");
          setPendingBillingSessionId("");
          setNotice("Checkout was closed. Your current plan and saved work were not changed.");
          window.history.replaceState({}, "", "/settings");
        } else if (googleReturned === "connected") {
          setNotice(
            returnSource === "business-profile"
              ? "Google business listings are connected. Match each location to its listing next."
              : returnSource === "analytics"
                ? "Website analytics is connected. Match each location to its analytics property next."
              : "Google Search Console is connected. Match each location to its website next.",
          );
          window.history.replaceState({}, "", "/settings");
          if (returnSource === "business-profile") {
            await loadProfileResources(currentUser.organization_id);
          } else if (returnSource === "analytics") {
            await loadAnalyticsResources(currentUser.organization_id);
          } else {
            await loadResources(currentUser.organization_id);
          }
        } else if (connectionResponse.google_oauth.connected) {
          setNotice("");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load data connections.");
      } finally {
        setLoading(false);
      }
    }
    void loadPage();
  }, [confirmBillingReturn, loadAnalyticsResources, loadAuthSessions, loadAutomationCommandAccess, loadAutomationConnections, loadConnections, loadPrivateAIProviders, loadPrivateAIRelay, loadProfileResources, loadResources]);

  async function startCheckout(planCode: string) {
    if (!organizationId) return;
    setBusyAction("billing-checkout");
    setError("");
    setNotice("");
    try {
      const serverAttempt = billingAttemptFromPending(
        organizationId,
        billingSummary?.pending_checkout,
      );
      const attempt = serverAttempt || checkoutAttemptForPlan(organizationId, planCode);
      const requestedPlanCode = serverAttempt?.planCode || planCode;
      const response = (await platformApi("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({
          plan_code: requestedPlanCode,
          client_request_id: attempt.clientRequestId,
        }),
      })) as {
        url?: string;
        session_id?: string;
        expires_at?: string;
        client_request_id?: string;
        requested_plan_code?: string;
        checkout_status?: "created" | "reused";
      };
      if (!response.url) throw new Error("The secure checkout link was not created.");
      saveBillingCheckoutAttempt({
        ...attempt,
        planCode: response.requested_plan_code || attempt.planCode,
        clientRequestId: response.client_request_id || attempt.clientRequestId,
        expiresAt: response.expires_at || attempt.expiresAt || null,
      });
      window.location.assign(response.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open secure checkout.");
      setBusyAction("");
    }
  }

  function refreshBillingConfirmation() {
    if (!organizationId) return;
    const attempt = readBillingCheckoutAttempt(organizationId);
    void confirmBillingReturn(
      organizationId,
      pendingBillingPlanCode || attempt?.planCode || "",
      pendingBillingClientRequestId || attempt?.clientRequestId || "",
      pendingBillingSessionId,
    );
  }

  async function manageBilling() {
    setBusyAction("billing-portal");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/billing/portal", {
        method: "POST",
      })) as { url?: string };
      if (!response.url) throw new Error("The secure billing link was not created.");
      window.location.assign(response.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to open billing settings.");
      setBusyAction("");
    }
  }

  async function revokeAuthSession(sessionId: string) {
    setBusyAction(`auth-session-${sessionId}`);
    setError("");
    setNotice("");
    try {
      await platformApi(`/auth/sessions/${sessionId}`, { method: "DELETE" });
      await loadAuthSessions();
      setNotice("That browser was signed out. This browser stayed signed in.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign out that browser.");
    } finally {
      setBusyAction("");
    }
  }

  async function revokeOtherAuthSessions() {
    setBusyAction("auth-sessions-others");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi("/auth/sessions/others", {
        method: "DELETE",
      })) as { revoked_count: number };
      await loadAuthSessions();
      setNotice(
        response.revoked_count === 0
          ? "No other browsers were signed in."
          : `${response.revoked_count} other ${response.revoked_count === 1 ? "browser was" : "browsers were"} signed out. This browser stayed signed in.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign out other browsers.");
    } finally {
      setBusyAction("");
    }
  }

  async function createAccountExport() {
    if (!organizationId) return;
    setBusyAction("data-export-create");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-governance/exports`,
        {
          method: "POST",
          body: JSON.stringify({ client_request_id: crypto.randomUUID() }),
        },
      )) as { export: DataExport };
      setDataExports((current) => [
        response.export,
        ...current.filter((item) => item.id !== response.export.id),
      ]);
      setNotice("Your account export is ready. Download it within seven days.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create your account export.");
    } finally {
      setBusyAction("");
    }
  }

  async function downloadAccountExport(item: DataExport) {
    if (!organizationId || !item.download_available) return;
    setBusyAction(`data-export-download-${item.id}`);
    setError("");
    setNotice("");
    try {
      const file = await platformApiFile(
        `/organizations/${organizationId}/data-governance/exports/${item.id}/download`,
        { method: "GET" },
      );
      const dispositionFilename = file.contentDisposition.match(/filename="?([^";]+)"?/i)?.[1];
      const fileUrl = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = fileUrl;
      link.download = dispositionFilename || `insightos-account-export-${item.id}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(fileUrl);
      setDataExports((current) =>
        current.map((exportItem) =>
          exportItem.id === item.id
            ? { ...exportItem, downloaded_at: new Date().toISOString() }
            : exportItem,
        ),
      );
      setNotice("Your account export was downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download your account export.");
    } finally {
      setBusyAction("");
    }
  }

  async function disconnectGoogleProvider() {
    if (!organizationId || !googleDisconnectPreview) return;
    setBusyAction("google-disconnect");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-governance/provider-disconnects`,
        {
          method: "POST",
          body: JSON.stringify({
            client_request_id: crypto.randomUUID(),
            provider_name: "google",
            confirmation: googleDisconnectConfirmation,
          }),
        },
      )) as { disconnect: ProviderDisconnectRecord };
      const previewResponse = (await platformApi(
        `/organizations/${organizationId}/data-governance/provider-disconnects/google/preview`,
        { method: "GET" },
      )) as { preview: ProviderDisconnectPreview };
      await loadConnections(organizationId);
      setGoogleDisconnectPreview(previewResponse.preview);
      setProviderDisconnects((current) => [
        response.disconnect,
        ...current.filter((item) => item.id !== response.disconnect.id),
      ]);
      setResources([]);
      setProfileResources([]);
      setAnalyticsResources([]);
      setWebsiteEventKeys({});
      setShowGoogleDisconnect(false);
      setGoogleDisconnectConfirmation("");
      setNotice(
        response.disconnect.external_revocation_status === "not_confirmed"
          ? "Google is disconnected from InsightOS and the local authorization was deleted. Google could not confirm its side, so review third-party access in your Google Account."
          : "Google is disconnected. Automatic updates stopped, the local authorization was deleted, and your saved results remain available.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect Google safely.");
    } finally {
      setBusyAction("");
    }
  }

  async function scheduleWorkspaceClosure() {
    if (!organizationId || !closurePreview) return;
    setBusyAction("workspace-closure");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-governance/closures`,
        {
          method: "POST",
          body: JSON.stringify({
            client_request_id: crypto.randomUUID(),
            confirmation: closureConfirmation,
            data_export_choice_acknowledged: closureExportChoiceAcknowledged,
            recovery_window_acknowledged: closureRecoveryAcknowledged,
          }),
        },
      )) as { closure: OrganizationClosureRecord };
      const previewResponse = (await platformApi(
        `/organizations/${organizationId}/data-governance/closures/preview`,
        { method: "GET" },
      )) as { preview: OrganizationClosurePreview };
      setClosurePreview(previewResponse.preview);
      setClosureHistory((current) => [
        response.closure,
        ...current.filter((item) => item.id !== response.closure.id),
      ]);
      setClosureReviewStep(0);
      setClosureConfirmation("");
      setClosureExportChoiceAcknowledged(false);
      setClosureRecoveryAcknowledged(false);
      setNotice(
        `Workspace closure is scheduled. It is now read-only, and an account owner can reopen it until ${formatTimestamp(response.closure.recovery_until)}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to schedule workspace closure safely.");
    } finally {
      setBusyAction("");
    }
  }

  async function cancelWorkspaceClosure(item: OrganizationClosureRecord) {
    if (!organizationId) return;
    setBusyAction("workspace-reopen");
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-governance/closures/${item.id}/cancel`,
        { method: "POST" },
      )) as { closure: OrganizationClosureRecord };
      const previewResponse = (await platformApi(
        `/organizations/${organizationId}/data-governance/closures/preview`,
        { method: "GET" },
      )) as { preview: OrganizationClosurePreview };
      setClosurePreview(previewResponse.preview);
      setClosureHistory((current) => current.map((row) => (
        row.id === response.closure.id ? response.closure : row
      )));
      setNotice(
        "The workspace is open again. Safe connections and schedules were restored; old public report links and canceled jobs were not reopened.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reopen this workspace.");
    } finally {
      setBusyAction("");
    }
  }

  function downloadMigrationTemplate() {
    const template = [
      "Record Type,Location Name,Website,City,State,Country,Postal Code,Keyword,Group,Competitor,Position,Captured At,Source Record ID,Directory Name,Listing URL,Listing Status,Listing Business Name,Listing Address,Listing City,Listing Region,Listing Postal Code,Listing Phone,Listing Website,Primary Category,Directory Importance,Recipient Email,Recipient Name,Recipient Role",
      "location,Reno Location,example.com,Reno,NV,US,89501,,,",
      "keyword,Reno Location,,,,,,junk removal reno,Core service,",
      "competitor,Reno Location,,,,,,,,competitor.com",
      "ranking,Reno Location,,,,,,junk removal reno,,,12,2026-07-31,legacy-row-101",
      "listing,Reno Location,,,,US,,,,,,2026-07-31,legacy-listing-101,Google Business Profile,https://example.com/profile,live,Example Junk Removal,123 Main St,Reno,NV,89501,775-555-0100,example.com,Junk Removal,essential",
      "report recipient,Reno Location,,,,,,,,,,,legacy-recipient-101,,,,,,,,,,,,,owner@example.com,Alex Owner,owner",
    ].join("\r\n");
    const url = URL.createObjectURL(new Blob([template], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "insightos-migration-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function chooseMigrationFile(file?: File) {
    setMigrationReview(null);
    setMigrationConfirmed(false);
    setMigrationRequestId("");
    setMigrationBatch(null);
    setMigrationCsv("");
    setMigrationFileName("");
    setMigrationUploadId("");
    setMigrationUploadProgress(0);
    setMigrationFileFingerprint("");
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      setError("Choose a CSV file smaller than 20 MB.");
      return;
    }
    setError("");
    setMigrationFileName(file.name);
    setMigrationFileFingerprint(`${file.name}:${file.size}:${file.lastModified}`);
    setMigrationCsv(await file.text());
  }

  function migrationResumeKey() {
    if (!organizationId || !migrationFileFingerprint) return "";
    return `insightos:migration-upload:${organizationId}:${migrationSource}:${migrationFileFingerprint}`;
  }

  async function reviewResumableMigration() {
    if (!organizationId || !migrationCsv) return null;
    const chunks = splitMigrationChunks(migrationCsv);
    if (chunks.length > 100) {
      throw new Error("This file needs more than 100 upload parts. Choose a CSV smaller than 20 MB.");
    }
    const expectedSha256 = await sha256Text(migrationCsv);
    const storageKey = migrationResumeKey();
    let saved: { upload_id?: string; create_request_id?: string; expected_sha256?: string } = {};
    if (storageKey) {
      try {
        saved = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as typeof saved;
      } catch {
        saved = {};
      }
    }
    let createRequestId =
      saved.expected_sha256 === expectedSha256 && saved.create_request_id
        ? saved.create_request_id
        : crypto.randomUUID();

    async function createSession(requestId: string) {
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/uploads`,
        {
          method: "POST",
          body: JSON.stringify({
            source_system: migrationSource,
            source_filename: migrationFileName || null,
            total_chunks: chunks.length,
            expected_sha256: expectedSha256,
            client_request_id: requestId,
          }),
        },
      )) as { upload: MigrationUpload };
      return response.upload;
    }

    let upload = await createSession(createRequestId);
    if (upload.status === "applied" || new Date(upload.expires_at).getTime() <= Date.now()) {
      createRequestId = crypto.randomUUID();
      upload = await createSession(createRequestId);
    }
    setMigrationUploadId(upload.id);
    if (storageKey) {
      window.localStorage.setItem(
        storageKey,
        JSON.stringify({
          upload_id: upload.id,
          create_request_id: createRequestId,
          expected_sha256: expectedSha256,
        }),
      );
    }

    const received = new Set(upload.received_chunk_indexes || []);
    setMigrationUploadProgress(
      Math.round(((upload.received_chunks || 0) / upload.total_chunks) * 100),
    );
    if (upload.status === "uploading") {
      for (let index = 0; index < chunks.length; index += 1) {
        if (received.has(index)) continue;
        const content = chunks[index];
        await platformApi(
          `/organizations/${organizationId}/migration-imports/uploads/${upload.id}/chunks/${index}`,
          {
            method: "PUT",
            body: JSON.stringify({ content, chunk_sha256: await sha256Text(content) }),
          },
        );
        received.add(index);
        setMigrationUploadProgress(Math.round((received.size / chunks.length) * 100));
      }
    }
    return (await platformApi(
      `/organizations/${organizationId}/migration-imports/uploads/${upload.id}/review?page=1&page_size=100`,
      { method: "POST" },
    )) as MigrationReview;
  }

  async function reviewMigrationFile() {
    if (!organizationId || !migrationCsv) return;
    setBusyAction("migration-dry-run");
    setError("");
    setNotice("");
    try {
      const rowCount = (migrationCsv.match(/\r?\n/g) || []).length;
      const useResumableUpload =
        migrationCsv.length > resumableMigrationThreshold || rowCount > 2_501;
      const response = useResumableUpload
        ? await reviewResumableMigration()
        : ((await platformApi(
            `/organizations/${organizationId}/migration-imports/dry-run`,
            {
              method: "POST",
              body: JSON.stringify({ source_system: migrationSource, csv_text: migrationCsv }),
            },
          )) as MigrationReview);
      if (!response) return;
      setMigrationReview(response);
      setMigrationConfirmed(false);
      setMigrationRequestId(crypto.randomUUID());
    } catch (err) {
      setMigrationReview(null);
      setError(err instanceof Error ? err.message : "Unable to review this migration file.");
    } finally {
      setBusyAction("");
    }
  }

  async function loadMoreMigrationReviewRows() {
    if (!organizationId || !migrationUploadId || !migrationReview?.pagination?.has_more) return;
    setBusyAction("migration-review-more");
    setError("");
    try {
      const nextPage = migrationReview.pagination.page + 1;
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/uploads/${migrationUploadId}/review/rows?page=${nextPage}&page_size=${migrationReview.pagination.page_size}`,
        { method: "GET" },
      )) as MigrationReview;
      setMigrationReview((current) =>
        current
          ? { ...current, rows: [...current.rows, ...response.rows], pagination: response.pagination }
          : response,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load more review rows.");
    } finally {
      setBusyAction("");
    }
  }

  async function applyMigrationFile() {
    if (!organizationId || !migrationCsv || !migrationReview || !migrationConfirmed) return;
    setBusyAction("migration-apply");
    setError("");
    setNotice("");
    try {
      const response = migrationUploadId
        ? ((await platformApi(
            `/organizations/${organizationId}/migration-imports/uploads/${migrationUploadId}/apply`,
            {
              method: "POST",
              body: JSON.stringify({
                review_hash: migrationReview.review_hash,
                client_request_id: migrationRequestId,
                confirmed: true,
              }),
            },
          )) as { batch: MigrationBatch })
        : ((await platformApi(
            `/organizations/${organizationId}/migration-imports/apply`,
            {
              method: "POST",
              body: JSON.stringify({
                source_system: migrationSource,
                source_filename: migrationFileName || null,
                csv_text: migrationCsv,
                review_hash: migrationReview.review_hash,
                client_request_id: migrationRequestId,
                confirmed: true,
              }),
            },
          )) as { batch: MigrationBatch });
      setMigrationBatch(response.batch);
      setMigrationHistory((current) => [
        response.batch,
        ...current.filter((item) => item.id !== response.batch.id),
      ]);
      setNotice(
        `Import complete: ${response.batch.summary.records_applied || 0} reviewed rows were added.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to apply this migration file.");
    } finally {
      setBusyAction("");
    }
  }

  async function rollbackMigration(batch: MigrationBatch) {
    if (!organizationId || !batch.rollback_available) return;
    if (!window.confirm("Remove only the records created by this import? Newer attached work will be protected.")) {
      return;
    }
    setBusyAction(`migration-rollback-${batch.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/migration-imports/${batch.id}/rollback`,
        {
          method: "POST",
          body: JSON.stringify({ confirmed: true }),
        },
      )) as { batch: MigrationBatch };
      setMigrationBatch((current) => current?.id === batch.id ? response.batch : current);
      setMigrationHistory((current) => current.map((item) => (
        item.id === batch.id ? response.batch : item
      )));
      setNotice("The records created by this import were removed. The review history was kept.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to roll back this import.");
    } finally {
      setBusyAction("");
    }
  }

  async function connectGoogle(scopeTarget: "gsc" | "gbp" | "analytics" = "gsc") {
    if (!organizationId) return;
    setBusyAction(`oauth-${scopeTarget}`);
    setError("");
    setNotice("");
    try {
      const returnPath = guidedConnectionSetup
        ? scopeTarget === "gbp"
          ? "/settings?setup=connections&source=business-profile"
          : scopeTarget === "analytics"
            ? "/settings?setup=connections&source=analytics"
          : "/settings?setup=connections"
        : scopeTarget === "gbp"
          ? "/settings?source=business-profile"
          : scopeTarget === "analytics"
            ? "/settings?source=analytics"
          : "/settings";
      const response = (await platformApi(
        `/organizations/${organizationId}/providers/google/oauth/start?scope_target=${scopeTarget}&return_path=${encodeURIComponent(returnPath)}`,
        { method: "POST" },
      )) as { authorization_url?: string };
      if (!response.authorization_url) {
        throw new Error("Google did not return a connection link.");
      }
      window.location.assign(response.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start the Google connection.");
      setBusyAction("");
    }
  }

  async function saveProfileMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = profileDrafts[campaign.id] || "";
    const resource = profileResources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose the Google business listing for this location.");
      return;
    }
    setBusyAction(`profile-mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-business-profile/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ external_resource_id: resource.id }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The Google business listing match was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      setNotice(
        syncResponse.job?.status === "completed"
          ? `${campaign.name} is matched and its Google listing check is ready.`
          : `${campaign.name} is matched. Its first Google listing check is queued.`,
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this listing match.");
    } finally {
      setBusyAction("");
    }
  }

  async function saveMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = resourceDrafts[campaign.id] || "";
    const resource = resources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose a Search Console website for this location.");
      return;
    }
    setBusyAction(`mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-search-console/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            external_resource_id: resource.id,
            external_resource_name: resource.name,
          }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The website mapping was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      if (syncResponse.job?.status === "completed") {
        setNotice(`${campaign.name} is connected and its first Search Console history is ready.`);
      } else {
        setNotice(`${campaign.name} is connected. Its first automatic update has been queued.`);
      }
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this website connection.");
    } finally {
      setBusyAction("");
    }
  }

  async function saveAnalyticsMapping(campaign: Campaign) {
    if (!organizationId) return;
    const resourceId = analyticsDrafts[campaign.id] || "";
    const resource = analyticsResources.find((item) => item.id === resourceId);
    if (!resourceId || !resource) {
      setError("Choose the website analytics property for this location.");
      return;
    }
    setBusyAction(`analytics-mapping-${campaign.id}`);
    setError("");
    setNotice("");
    try {
      const mappingResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/google-analytics/mappings/${campaign.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            external_resource_id: resource.id,
            external_resource_name: resource.name,
          }),
        },
      )) as { connection?: DataConnection };
      const connectionId = mappingResponse.connection?.id;
      if (!connectionId) throw new Error("The website analytics match was not saved.");
      const syncResponse = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connectionId}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string } };
      await loadConnections(organizationId);
      setNotice(
        syncResponse.job?.status === "completed"
          ? `${campaign.name} is matched and its first website visit history is ready.`
          : `${campaign.name} is matched. Its first website visit update is queued.`,
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to save this analytics match.");
    } finally {
      setBusyAction("");
    }
  }

  async function createWebsiteEventKey(connection: DataConnection) {
    if (!organizationId) return;
    setBusyAction(`website-event-key-${connection.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connection.id}/website-events/key`,
        { method: "POST" },
      )) as WebsiteEventKey;
      if (!response.token || !response.event_path) {
        throw new Error("The secure form connection was not created.");
      }
      setWebsiteEventKeys((current) => ({ ...current, [connection.id]: response }));
      await loadConnections(organizationId);
      setNotice(
        "The secure form connection is ready. Copy it now; the private key will not be shown again.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the form connection.");
    } finally {
      setBusyAction("");
    }
  }

  async function syncConnection(connection: DataConnection) {
    if (!organizationId) return;
    if (connection.status === "reconnect_required") {
      await connectGoogle(
        connection.provider_name === "google_business_profile"
          ? "gbp"
          : connection.provider_name === "google_analytics"
            ? "analytics"
            : "gsc",
      );
      return;
    }
    setBusyAction(`sync-${connection.id}`);
    setError("");
    setNotice("");
    try {
      const response = (await platformApi(
        `/organizations/${organizationId}/data-connections/${connection.id}/sync`,
        { method: "POST" },
      )) as { job?: { status?: string; idempotent_replay?: boolean } };
      await loadConnections(organizationId);
      setNotice(
        response.job?.idempotent_replay
          ? `${connection.business_location_name || connection.campaign_name} is already up to date.`
          : response.job?.status === "completed"
            ? `${connection.business_location_name || connection.campaign_name} was updated successfully.`
            : "The update is queued and will continue automatically.",
      );
    } catch (err) {
      await loadConnections(organizationId).catch(() => undefined);
      setError(err instanceof Error ? err.message : "Unable to update this connection.");
    } finally {
      setBusyAction("");
    }
  }

  async function handleHealthAction(item: ConnectionHealthItem) {
    if (item.recovery_action.kind === "none" || item.recovery_action.kind === "wait") return;
    if (item.recovery_action.kind === "sync" && item.connection_id) {
      const connection = connections.find((row) => row.id === item.connection_id);
      if (connection) await syncConnection(connection);
      return;
    }
    const href = item.recovery_action.href;
    if (!href) return;
    if (href.startsWith("/settings#")) {
      const anchor = href.split("#")[1];
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    if (item.provider_name === "google_business_profile") {
      await connectGoogle("gbp");
      return;
    }
    if (item.provider_name === "google_analytics") {
      await connectGoogle("analytics");
      return;
    }
    await connectGoogle("gsc");
  }

  const navItems = useMemo(() => buildProductNav(pathname), [pathname]);
  const selectedAutomationProviderSetup = automationProviderSetup.find(
    (item) => item.code === automationProvider,
  );
  const selectedAutomationCommandConnector = automationConnectorCatalog?.items.find(
    (item) => item.code === automationCommandProvider,
  );
  const activeAutomationServiceAccount = automationServiceAccounts.find(
    (item) => item.status === "active",
  );
  const automationExtraAbilityCount = activeAutomationServiceAccount
    ? [
        "report.generate_saved",
        "recommendation.retrieve",
        "connection.refresh_saved",
        "listing.check_public",
        "content.create_working_draft",
        "review.retrieve",
        "review.create_response_draft",
      ].filter((command) => activeAutomationServiceAccount.allowed_commands.includes(
        command as AutomationServiceAccount["allowed_commands"][number],
      )).length
    : 0;
  const activeAutomationCampaign = activeAutomationServiceAccount
    ? manageableCampaigns.find(
        (campaign) => campaign.business_location_id === activeAutomationServiceAccount.location_id,
      )
    : undefined;
  const currentAuthSession = authSessions?.find((session) => session.current) || null;
  const otherAuthSessions = authSessions?.filter((session) => !session.current) || [];
  const visibleAuthSessions = currentAuthSession
    ? [currentAuthSession, ...otherAuthSessions.slice(0, 2)]
    : otherAuthSessions.slice(0, 3);
  const additionalAuthSessions = currentAuthSession
    ? otherAuthSessions.slice(2)
    : otherAuthSessions.slice(3);
  const privateAIProviderPlanEligible =
    usageAllowance?.capabilities.find((item) => item.code === "private_ai_provider")
      ?.available === true;
  const allPrivateAIRelayAcknowledged = Object.values(privateAIRelayAcks).every(Boolean);

  const renderAuthSession = (session: AuthSessionSummary) => (
    <article key={session.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-white">
            {session.current ? "This browser" : "Another signed-in browser"}
          </h3>
          {session.current ? (
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-100">
              Current
            </span>
          ) : null}
        </div>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          Signed in {formatTimestamp(session.created_at)} · Last active {formatTimestamp(session.last_seen_at)}
        </p>
      </div>
      {!session.current ? (
        <button
          type="button"
          className={secondaryButtonClass}
          disabled={busyAction === `auth-session-${session.id}`}
          onClick={() => void revokeAuthSession(session.id)}
        >
          {busyAction === `auth-session-${session.id}` ? "Signing out..." : "Sign out this browser"}
        </button>
      ) : (
        <span className="text-xs text-zinc-500">Use the main Sign out action to end this session.</span>
      )}
    </article>
  );
  const trustSignals = useMemo<TrustSignal[]>(
    () => [
      {
        label: "Google",
        value: payload?.google_oauth.connected ? "Connected" : "Not connected",
        tone: payload?.google_oauth.connected ? "success" : "warning",
      },
      {
        label: "Healthy sources",
        value: connectionHealth
          ? `${connectionHealth.summary.healthy}/${connectionHealth.summary.sources}`
          : "Checking",
        tone:
          connectionHealth && connectionHealth.summary.healthy === connectionHealth.summary.sources
            ? "success"
            : "warning",
      },
      {
        label: "Needs action",
        value: connectionHealth
          ? String(connectionHealth.summary.needs_attention + connectionHealth.summary.needs_setup)
          : "Checking",
        tone:
          connectionHealth && connectionHealth.summary.needs_attention > 0
            ? "danger"
            : connectionHealth && connectionHealth.summary.needs_setup > 0
              ? "warning"
              : "success",
      },
      {
        label: "Insight Credits",
        value: usageAllowance
          ? `${usageAllowance.credits.remaining.toLocaleString()} available`
          : "Checking",
        tone: usageAllowance?.credits.blocked
          ? "danger"
          : usageAllowance?.credits.warning_level
            ? "warning"
            : "info",
      },
    ],
    [connectionHealth, payload, usageAllowance],
  );

  return (
    <AppShell
      navItems={navItems}
      trustSignals={trustSignals}
      accountLabel="Settings"
      dateRangeLabel="Connections and account"
      topBarActions={
        <button
          className={primaryButtonClass}
          disabled={busyAction.startsWith("oauth-")}
          onClick={() => void connectGoogle()}
        >
          {payload?.google_oauth.connected ? "Reconnect Google" : "Connect Google"}
        </button>
      }
    >
      <section className="space-y-6">
        <ProductPageIntro
          compact
          eyebrow="Settings"
          title="Manage your connections and account"
          summary="Choose what you need to set up or change. Technical details stay out of the way unless you open them."
        />

        <TruthNotice title="Start with the task you came here to finish" tone="info">
          Connection problems appear first when something needs attention. Everything else is grouped below so you do not have to scan one long technical page.
        </TruthNotice>

        <nav aria-label="Settings tasks" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Business data", "Connect or repair Google", "#google-search-console-connection"],
            ["Workflow tools", "Connect Zapier, Make, or n8n", "#external-automation"],
            ["Plan and billing", "Manage subscription and usage", "#plan-and-billing"],
            ["Account security", "Review other signed-in browsers", "#account-security"],
          ].map(([label, summary, href]) => (
            <a
              key={href}
              href={href}
              className="rounded-md border border-[#292a2f] bg-[#141518] px-4 py-3 transition hover:border-[#3a3b42] hover:bg-[#191a1e]"
            >
              <span className="block text-sm font-semibold text-white">{label}</span>
              <span className="mt-1 block text-xs leading-5 text-zinc-400">{summary}</span>
            </a>
          ))}
        </nav>

        {error ? (
          <div className="rounded-md border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {notice}
          </div>
        ) : null}

        {guidedConnectionSetup && !loading ? (
          <section className="rounded-md border border-accent-500/30 bg-accent-500/5 p-5" aria-labelledby="guided-connections-title">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-200">
                  Finish setup
                </p>
                <h2 id="guided-connections-title" className="mt-1 text-xl font-semibold text-white">
                  Connect the information that keeps your results current
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                  Work from top to bottom. InsightOS will show the websites and listings your Google account can access, then keep every location&apos;s results separate.
                </p>
              </div>
              <span className="shrink-0 rounded-full border border-accent-500/25 bg-accent-500/10 px-3 py-1.5 text-xs font-semibold text-accent-100">
                {guidedStepsComplete} of 3 complete
              </span>
            </div>

            <ol className="mt-5 divide-y divide-[#303137] border-y border-[#303137]">
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">1</span>
                <div>
                  <p className="font-semibold text-white">Approve Google access</p>
                  <p className="mt-1 text-sm text-zinc-400">This securely connects your account. InsightOS never receives your Google password.</p>
                </div>
                {payload?.google_oauth.connected ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : (
                  <button type="button" className={primaryButtonClass} onClick={() => void connectGoogle()}>
                    Connect Google
                  </button>
                )}
              </li>
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">2</span>
                <div>
                  <p className="font-semibold text-white">Match each website to its location</p>
                  <p className="mt-1 text-sm text-zinc-400">This brings in Google appearances, website visits, and average position without mixing locations.</p>
                </div>
                {websiteMappingsComplete ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : payload?.google_oauth.connected ? (
                  <button type="button" className={primaryButtonClass} onClick={() => scrollToConnectionStep("website-mappings")}>
                    Match websites
                  </button>
                ) : (
                  <span className="text-sm text-zinc-500">Finish step 1 first</span>
                )}
              </li>
              <li className="grid gap-3 py-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[#303137] bg-[#111214] text-sm font-semibold text-white">3</span>
                <div>
                  <p className="font-semibold text-white">Match each Google business listing</p>
                  <p className="mt-1 text-sm text-zinc-400">This connects listing details and customer actions. No listing changes are made automatically.</p>
                </div>
                {profileMappingsComplete && payload?.google_oauth.approved_access?.business_profile ? (
                  <span className="text-sm font-semibold text-emerald-300">Complete</span>
                ) : payload?.google_oauth.approved_access?.business_profile ? (
                  <button type="button" className={primaryButtonClass} onClick={() => scrollToConnectionStep("profile-mappings")}>
                    Match listings
                  </button>
                ) : payload?.google_oauth.connected ? (
                  <button type="button" className={primaryButtonClass} onClick={() => void connectGoogle("gbp")}>
                    Approve listing access
                  </button>
                ) : (
                  <span className="text-sm text-zinc-500">Finish step 1 first</span>
                )}
              </li>
            </ol>

            {guidedStepsComplete === 3 ? (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-4">
                <p className="text-sm font-medium text-emerald-100">Setup is complete. Your connected information will now update automatically.</p>
                <button
                  type="button"
                  className={primaryButtonClass}
                  onClick={() => {
                    requestProductTour(window.localStorage, getTenantId() || organizationId);
                    window.location.assign("/dashboard");
                  }}
                >
                  Open your dashboard
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

        {loading ? (
          <LoadingCard
            title="Loading data connections"
            summary="Checking Google access, location mappings, and the latest automatic updates."
          />
        ) : (
          <>
            <OwnerDecisionPanel
              eyebrow="Connection status"
              title={connectionHealth?.summary.headline || "Checking your connections"}
              summary={
                connectionHealth
                  ? `${connectionHealth.summary.healthy} of ${connectionHealth.summary.sources} connected sources are healthy across ${connectionHealth.summary.locations} ${connectionHealth.summary.locations === 1 ? "location" : "locations"}.`
                  : "InsightOS is checking the latest saved connection history."
              }
              nextStep={connectionHealth?.summary.next_step || "Wait for the connection check to finish."}
              actionLabel={
                manageableCampaigns.length === 0
                  ? "Add a location"
                  : connectionItemsNeedingWork[0]?.recovery_action.label
              }
              onAction={
                manageableCampaigns.length === 0
                  ? () => window.location.assign("/locations")
                  : connectionItemsNeedingWork[0]
                    ? () => void handleHealthAction(connectionItemsNeedingWork[0])
                    : undefined
              }
              tone={
                (connectionHealth?.summary.needs_attention || 0) > 0
                  ? "urgent"
                  : (connectionHealth?.summary.needs_setup || 0) > 0
                    ? "warning"
                    : (connectionHealth?.summary.sources || 0) > 0
                      ? "positive"
                      : "neutral"
              }
              progress={
                connectionHealth && connectionHealth.summary.sources > 0
                  ? {
                      label: "Connected sources working normally",
                      value: connectionHealth.summary.healthy,
                      total: connectionHealth.summary.sources,
                      summary: "A source only counts as healthy after a successful update.",
                    }
                  : undefined
              }
            />

            {connectionItemsNeedingWork.length > 0 ? (
              <section aria-labelledby="connections-needing-work" className="space-y-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500">
                    Do this next
                  </p>
                  <h2 id="connections-needing-work" className="mt-1 text-xl font-semibold text-white">
                    Fix these connections
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Work from the top. Each row shows what is affected and the next safe step.
                  </p>
                </div>
                <div className="divide-y divide-[#292a2f] border-y border-[#292a2f]">
                  {connectionItemsNeedingWork.map((item) => (
                    <article key={item.id} className="grid gap-4 py-4 lg:grid-cols-[1fr_auto] lg:items-center">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-white">{item.location_name} · {item.label}</h3>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClasses(healthTone(item))}`}>
                            {healthStatusLabel(item)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-zinc-300">{item.summary}</p>
                        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
                          <span>Last successful update: {formatTimestamp(item.last_success_at)}</span>
                          <span>Newest usable data: {formatDataDate(item.newest_usable_data_date)}</span>
                        </div>
                        {item.affected_features.length > 0 ? (
                          <p className="mt-2 text-xs text-amber-100/80">
                            May affect: {item.affected_features.join(", ")}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className={primaryButtonClass}
                        disabled={item.recovery_action.kind === "wait" || busyAction === `sync-${item.connection_id}`}
                        onClick={() => void handleHealthAction(item)}
                      >
                        {busyAction === `sync-${item.connection_id}` ? "Checking..." : item.recovery_action.label}
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            {healthyConnectionItems.length > 0 ? (
              <details className="border-y border-[#292a2f] py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-white">
                  <span>{healthyConnectionItems.length} healthy {healthyConnectionItems.length === 1 ? "connection" : "connections"}</span>
                  <span className="text-xs font-medium text-emerald-300">No action needed</span>
                </summary>
                <div className="mt-3 divide-y divide-[#292a2f]">
                  {healthyConnectionItems.map((item) => (
                    <div key={item.id} className="flex flex-col gap-1 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                      <span className="font-medium text-zinc-200">{item.location_name} · {item.label}</span>
                      <span className="text-xs text-zinc-500">Usable data through {formatDataDate(item.newest_usable_data_date)}</span>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}

            {me?.org_role === "org_owner" && googleDisconnectPreview ? (
              <section aria-labelledby="google-access-control-heading" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Account control
                    </p>
                    <h2 id="google-access-control-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      Google access and saved results
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      {googleDisconnectPreview.connected
                        ? `Google is supplying updates for ${googleDisconnectPreview.affected_locations} ${googleDisconnectPreview.affected_locations === 1 ? "location" : "locations"}. You can disconnect it without erasing results already saved in InsightOS.`
                        : "Google is not connected. Previously saved results and reports remain available, but they will not receive new Google updates."}
                    </p>
                  </div>
                  {googleDisconnectPreview.connected && !showGoogleDisconnect ? (
                    <button
                      type="button"
                      className="inline-flex items-center justify-center rounded-md border border-rose-500/35 bg-rose-500/10 px-3.5 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20"
                      onClick={() => setShowGoogleDisconnect(true)}
                    >
                      Review disconnect
                    </button>
                  ) : null}
                </div>

                {showGoogleDisconnect && googleDisconnectPreview.connected ? (
                  <div className="mt-5 rounded-md border border-rose-500/30 bg-rose-500/5 p-5">
                    <p className="text-base font-semibold text-rose-100">Before you disconnect Google</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      This affects all Google access for this workspace. An update already running may finish, but it cannot turn the connection back on.
                    </p>
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      <div>
                        <p className="text-sm font-semibold text-white">These updates will stop</p>
                        <ul className="mt-2 space-y-2 text-sm leading-5 text-zinc-300">
                          {googleDisconnectPreview.what_stops.map((item) => (
                            <li key={item}>× {item}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">This information will stay</p>
                        <ul className="mt-2 space-y-2 text-sm leading-5 text-zinc-300">
                          {googleDisconnectPreview.what_stays.map((item) => (
                            <li key={item}>✓ {item}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <div className="mt-5 border-t border-rose-500/20 pt-4">
                      <label htmlFor="google-disconnect-confirmation" className="block text-sm font-semibold text-white">
                        Type {googleDisconnectPreview.confirmation_text} to confirm
                      </label>
                      <input
                        id="google-disconnect-confirmation"
                        type="text"
                        autoComplete="off"
                        className="mt-2 w-full max-w-md rounded-md border border-[#3a3b41] bg-[#101114] px-3 py-2.5 text-sm text-white outline-none focus:border-rose-400/60"
                        value={googleDisconnectConfirmation}
                        onChange={(event) => setGoogleDisconnectConfirmation(event.target.value)}
                      />
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          type="button"
                          className="inline-flex items-center justify-center rounded-md border border-rose-500/40 bg-rose-500/15 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={
                            googleDisconnectConfirmation !== googleDisconnectPreview.confirmation_text ||
                            busyAction === "google-disconnect"
                          }
                          onClick={() => void disconnectGoogleProvider()}
                        >
                          {busyAction === "google-disconnect" ? "Disconnecting safely..." : "Disconnect Google"}
                        </button>
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          disabled={busyAction === "google-disconnect"}
                          onClick={() => {
                            setShowGoogleDisconnect(false);
                            setGoogleDisconnectConfirmation("");
                          }}
                        >
                          Keep Google connected
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}

                {providerDisconnects.length > 0 ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Most recent change
                    </p>
                    <p className="mt-2 text-sm font-semibold text-white">
                      Disconnected {formatTimestamp(providerDisconnects[0].completed_at || providerDisconnects[0].requested_at)}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      {providerDisconnects[0].external_revocation_status === "not_confirmed"
                        ? "InsightOS deleted its Google authorization, but Google did not confirm the outside revocation. Review third-party access in your Google Account."
                        : providerDisconnects[0].external_revocation_status === "confirmed"
                          ? "Google confirmed the authorization was revoked. Saved business results were kept."
                          : "There was no saved Google authorization to revoke. Existing saved results were kept."}
                    </p>
                  </div>
                ) : null}
              </section>
            ) : null}

            <details id="account-security" className="group rounded-md border border-[#292a2f] bg-[#141518]">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Account and security
                  </p>
                  <p className="mt-1 text-base font-semibold text-white">
                    {authSessions === null
                      ? "Sign-in status needs attention"
                      : `${authSessions.length} active ${authSessions.length === 1 ? "browser" : "browsers"}`}
                  </p>
                  <p className="mt-1 text-sm text-zinc-400">
                    Open this only when you want to review or sign out another browser.
                  </p>
                </div>
                <span className="shrink-0 text-sm font-semibold text-zinc-300 group-open:hidden">Review</span>
                <span className="hidden shrink-0 text-sm font-semibold text-zinc-300 group-open:inline">Close</span>
              </summary>
              <div className="border-t border-[#292a2f] p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Account security
                  </p>
                  <h2 id="active-sign-ins-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                    Where you&apos;re signed in
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    Review active InsightOS sign-ins. If you do not recognize one, sign it out immediately. Passwords and login tokens are never shown here.
                  </p>
                </div>
                {authSessions && authSessions.some((item) => !item.current) ? (
                  <button
                    type="button"
                    className={secondaryButtonClass}
                    disabled={busyAction === "auth-sessions-others"}
                    onClick={() => void revokeOtherAuthSessions()}
                  >
                    {busyAction === "auth-sessions-others" ? "Signing out..." : "Sign out all other browsers"}
                  </button>
                ) : null}
              </div>

              {authSessions === null ? (
                <div className="mt-5 rounded-md border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-50">
                  <p className="font-semibold">Active sign-ins could not be checked</p>
                  <p className="mt-1 leading-6 text-amber-100/80">Your current session was not changed. Try checking again.</p>
                  <button
                    type="button"
                    className={`${secondaryButtonClass} mt-3`}
                    disabled={busyAction === "auth-sessions-refresh"}
                    onClick={() => {
                      setBusyAction("auth-sessions-refresh");
                      setError("");
                      void loadAuthSessions()
                        .catch((err) => setError(err instanceof Error ? err.message : "Unable to check active sign-ins."))
                        .finally(() => setBusyAction(""));
                    }}
                  >
                    {busyAction === "auth-sessions-refresh" ? "Checking..." : "Check again"}
                  </button>
                </div>
              ) : authSessions.length === 0 ? (
                <p className="mt-5 text-sm leading-6 text-zinc-400">
                  No active sign-in records were returned. Your current browser was not signed out.
                </p>
              ) : (
                <div className="mt-5 border-y border-[#292a2f]">
                  <div className="divide-y divide-[#292a2f]">
                    {visibleAuthSessions.map(renderAuthSession)}
                  </div>
                  {additionalAuthSessions.length > 0 ? (
                    <details className="group border-t border-[#292a2f]">
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3 text-sm font-semibold text-zinc-300">
                        <span>
                          Show {additionalAuthSessions.length} older signed-in {additionalAuthSessions.length === 1 ? "browser" : "browsers"}
                        </span>
                        <span className="text-xs text-zinc-500 group-open:hidden">Show</span>
                        <span className="hidden text-xs text-zinc-500 group-open:inline">Hide</span>
                      </summary>
                      <div className="divide-y divide-[#292a2f] border-t border-[#292a2f]">
                        {additionalAuthSessions.map(renderAuthSession)}
                      </div>
                    </details>
                  ) : null}
                </div>
              )}
              </div>
            </details>

            {usageAllowance ? (
              <section id="plan-and-billing" aria-labelledby="current-plan-heading" className="scroll-mt-24 rounded-md border border-[#292a2f] bg-[#141518] p-5">
                {billingConfirmationState !== "idle" ? (
                  <div
                    role="status"
                    className={`mb-5 rounded-md border p-4 text-sm ${
                      billingConfirmationState === "confirmed"
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-50"
                        : "border-amber-500/30 bg-amber-500/10 text-amber-50"
                    }`}
                  >
                    <p className="font-semibold">
                      {billingConfirmationState === "confirmed"
                        ? "Your plan is active"
                        : billingConfirmationState === "processing"
                          ? "Checkout is complete. Plan access is still updating"
                          : billingConfirmationState === "timed_out"
                            ? "Plan confirmation is taking longer than expected"
                            : "Confirming your plan"}
                    </p>
                    <p className="mt-1 leading-6 opacity-80">
                      {billingConfirmationState === "confirmed"
                        ? `${billingSummary?.plan_name || "Your updated plan"} is confirmed and ready to use.`
                        : billingConfirmationState === "processing"
                          ? "The checkout is saved, but access will not change until the active plan is confirmed."
                          : billingConfirmationState === "timed_out"
                            ? "Your checkout may still be processing. You do not need to purchase it again. Check the plan status again, or refresh this page later."
                            : "Checkout returned successfully. InsightOS is waiting for saved plan confirmation before changing access."}
                    </p>
                    {billingConfirmationState === "timed_out" ? (
                      <button
                        type="button"
                        className={`${secondaryButtonClass} mt-3`}
                        onClick={refreshBillingConfirmation}
                      >
                        Check plan status again
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {billingSummary?.recovery_message ? (
                  <div className="mb-5 rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-50">
                    <p className="font-semibold">Payment needs attention</p>
                    <p className="mt-1 leading-6 text-amber-100/80">{billingSummary.recovery_message}</p>
                    {billingSummary.portal_available ? (
                      <button
                        type="button"
                        className={`${primaryButtonClass} mt-3`}
                        disabled={busyAction === "billing-portal"}
                        onClick={() => void manageBilling()}
                      >
                        {busyAction === "billing-portal" ? "Opening..." : "Update payment method"}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Your plan
                    </p>
                    <h2 id="current-plan-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      {usageAllowance.plan.name} · ${usageAllowance.plan.monthly_price.toLocaleString()}/month
                    </h2>
                    <p className="mt-2 text-sm text-zinc-300">
                      {usageAllowance.plan.active_locations} of {usageAllowance.plan.included_locations} included {usageAllowance.plan.included_locations === 1 ? "location" : "locations"} in use
                    </p>
                    {billingSummary ? (
                      <p className="mt-1 text-xs text-zinc-500">
                        Billing: {billingSummary.status_label}
                        {billingSummary.cancel_at_period_end ? " · Ends after the current billing period" : ""}
                      </p>
                    ) : null}
                  </div>
                  <div className="grid gap-2 text-sm sm:grid-cols-2 lg:max-w-2xl">
                    {usageAllowance.capabilities.filter((item) => item.available).slice(0, 4).map((item) => (
                      <div key={item.code} className="border-l-2 border-emerald-500/40 pl-3">
                        <p className="font-semibold text-white">{item.label}</p>
                        <p className="mt-1 text-xs leading-5 text-zinc-400">{item.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
                {usageAllowance.upgrade ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-accent-200">
                          {usageAllowance.upgrade.plan_name} · ${usageAllowance.upgrade.monthly_price.toLocaleString()}/month
                        </p>
                        <h3 className="mt-1 font-semibold text-white">{usageAllowance.upgrade.headline}</h3>
                        <ul className="mt-2 space-y-1 text-sm leading-6 text-zinc-300">
                          {usageAllowance.upgrade.reasons.map((reason) => (
                            <li key={reason}>✓ {reason}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {billingSummary?.provider_configured &&
                        billingSummary.available_checkout_plans.includes(usageAllowance.upgrade.plan_code) ? (
                          <button
                            type="button"
                            className={primaryButtonClass}
                            disabled={busyAction === "billing-checkout"}
                            onClick={() => void startCheckout(usageAllowance.upgrade!.plan_code)}
                          >
                            {busyAction === "billing-checkout" ? "Opening checkout..." : "Upgrade securely"}
                          </button>
                        ) : (
                          <button type="button" className={secondaryButtonClass} onClick={() => window.location.assign("/help")}>Ask about upgrading</button>
                        )}
                        {billingSummary?.portal_available ? (
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === "billing-portal"}
                            onClick={() => void manageBilling()}
                          >
                            {busyAction === "billing-portal" ? "Opening..." : "Manage billing"}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : billingSummary?.portal_available ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4">
                    <button
                      type="button"
                      className={secondaryButtonClass}
                      disabled={busyAction === "billing-portal"}
                      onClick={() => void manageBilling()}
                    >
                      {busyAction === "billing-portal" ? "Opening..." : "Manage billing"}
                    </button>
                  </div>
                ) : null}
              </section>
            ) : null}

            {usageAllowance ? (
              <details className="rounded-md border border-[#292a2f] bg-[#141518] p-4">
                <summary className="cursor-pointer list-none">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Insight Credits available this month
                  </p>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <h2 className="text-base font-semibold text-white">
                      {usageAllowance.credits.remaining.toLocaleString()} credits available
                    </h2>
                    <span className="text-xs text-zinc-400">See usage</span>
                  </div>
                </summary>
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      {usageAllowance.plan.name} plan
                    </p>
                    <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">
                      {usageAllowance.credits.remaining.toLocaleString()} credits left this month
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
                      You have used {usageAllowance.credits.used.toLocaleString()} credits. {" "}
                      {usageAllowance.credits.reserved.toLocaleString()} are set aside for work that
                      is still running. Your balance resets {formatResetDate(usageAllowance.period.resets_at)}.
                    </p>
                  </div>
                  <div className="min-w-[220px]">
                    <div className="flex items-center justify-between text-xs text-zinc-400">
                      <span>{usageAllowance.credits.percent_committed.toFixed(1)}% used or reserved</span>
                      <span>{usageAllowance.credits.monthly.toLocaleString()} each month</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#24252a]">
                      <div
                        className={`h-full rounded-full ${
                          usageAllowance.credits.blocked
                            ? "bg-rose-400"
                            : usageAllowance.credits.warning_level
                              ? "bg-amber-400"
                              : "bg-emerald-400"
                        }`}
                        style={{
                          width: `${Math.min(100, usageAllowance.credits.percent_committed)}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
                {usageAllowance.recovery_actions.length > 0 ? (
                  <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {usageAllowance.recovery_actions[0]}
                  </div>
                ) : null}
                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  {usageAllowance.action_prices.map((action) => (
                    <div key={action.code} className="border-l-2 border-[#303137] pl-3">
                      <p className="text-sm font-semibold text-white">{action.label}</p>
                      <p className="mt-1 text-xs text-zinc-400">{action.result}</p>
                      <p className="mt-2 text-xs font-semibold text-accent-200">
                        {action.price_type === "up_to" ? "Up to " : ""}
                        {action.credits.toLocaleString()} {action.credits === 1 ? "credit" : "credits"}
                        {action.price_type === "per_item" ? " each" : ""}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-xs leading-5 text-zinc-500">
                  {usageAllowance.important_note} Failed work returns unused credits automatically.
                  Eligible checks made through your own connected account use 0 Insight Credits.
                </p>
              </details>
            ) : null}

            {me?.org_role === "org_owner" &&
            (privateAIProviderPlanEligible || privateAIProviders.length > 0 || privateAIRelay) ? (
              <section
                id="private-ai-provider"
                aria-labelledby="private-ai-provider-heading"
                className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Enterprise model control
                    </p>
                    <h2 id="private-ai-provider-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      Private AI provider candidates
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      Save an approved OpenAI-compatible HTTPS endpoint, validate it with synthetic data,
                      and review three fixed quality checks. Your API key is encrypted and is never shown again.
                    </p>
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-500">
                      Private endpoints and models running on your own computer are Enterprise-only. Growth ($699/month) keeps the standard managed-AI experience and does not include private-model deployment or support.
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-100">
                    Managed AI stays primary
                  </span>
                </div>

                <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm leading-6 text-amber-50">
                  Passing a check and owner approval alone do not send traffic. Only the separately approved fixed 5% checks below can use this provider. Managed AI remains required, and no private provider can publish, change a website, or change a business profile.
                </div>

                <div className="mt-5 rounded-md border border-sky-500/20 bg-sky-500/5 p-4">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <h3 className="font-semibold text-white">Connect a model running on your own computer</h3>
                      <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-300">
                        A local relay makes an outbound connection to InsightOS, so your computer does not need an inbound public endpoint. It can receive only a signed, short-lived synthetic receipt check; it cannot receive customer prompts or run model work yet.
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full border border-sky-500/25 bg-sky-500/10 px-2.5 py-1 text-xs font-semibold text-sky-100">
                      Connection only
                    </span>
                  </div>

                  {privateAIRelayLoadState === "unavailable" ? (
                    <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-50">
                      <p>The local relay status could not be checked. No connection key will be created until current status is available.</p>
                      <button
                        type="button"
                        className={`${secondaryButtonClass} mt-3`}
                        disabled={busyAction === "private-ai-relay-refresh"}
                        onClick={() => {
                          setBusyAction("private-ai-relay-refresh");
                          void loadPrivateAIRelay()
                            .catch((err) => setError(err instanceof Error ? err.message : "Unable to check the local relay."))
                            .finally(() => setBusyAction(""));
                        }}
                      >
                        {busyAction === "private-ai-relay-refresh" ? "Checking..." : "Check local relay again"}
                      </button>
                    </div>
                  ) : privateAIRelay ? (
                    <div className="mt-4 rounded-md border border-[#303137] bg-[#101114] p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="font-medium text-white">{privateAIRelay.name}</p>
                          <p className="mt-1 text-sm text-zinc-400">
                            {privateAIRelay.connection_state === "connected"
                              ? "Outbound connection verified"
                              : privateAIRelay.connection_state === "needs_reconnect"
                                ? "Connection has not checked in recently"
                                : "Waiting for the first outbound check"}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500">
                            Key {privateAIRelay.token_hint}
                            {privateAIRelay.last_seen_at ? ` · Last checked ${formatTimestamp(privateAIRelay.last_seen_at)}` : ""}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {privateAIProviderPlanEligible ? (
                            <button
                              type="button"
                              className={secondaryButtonClass}
                              disabled={busyAction === "private-ai-relay-agent-download"}
                              onClick={() => void downloadPrivateAIRelayAgent()}
                            >
                              {busyAction === "private-ai-relay-agent-download"
                                ? "Downloading..."
                                : "Download relay helper"}
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === "private-ai-relay-refresh"}
                            onClick={() => {
                              setBusyAction("private-ai-relay-refresh");
                              void loadPrivateAIRelay()
                                .catch((err) => setError(err instanceof Error ? err.message : "Unable to check the local relay."))
                                .finally(() => setBusyAction(""));
                            }}
                          >
                            {busyAction === "private-ai-relay-refresh" ? "Checking..." : "Refresh status"}
                          </button>
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === "private-ai-relay-revoke"}
                            onClick={() => void revokePrivateAIRelay(privateAIRelay.id)}
                          >
                            {busyAction === "private-ai-relay-revoke" ? "Revoking..." : "Revoke connection"}
                          </button>
                        </div>
                      </div>
                      {!privateAIProviderPlanEligible ? (
                        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-sm leading-6 text-amber-50">
                          <p className="font-semibold">Local model connection paused</p>
                          <p className="mt-1 text-amber-100/80">
                            This is an Enterprise-only capability. Saved connection history remains visible, and you can revoke the key, but Growth ($699/month) cannot run relay checks or local-model qualification.
                          </p>
                        </div>
                      ) : null}
                      {privateAIRelayToken ? (
                        <div className="mt-4 rounded-md border border-amber-500/25 bg-amber-500/5 p-3">
                          <p className="text-sm font-semibold text-amber-50">Save this one-time connection key now</p>
                          <p className="mt-1 text-xs leading-5 text-amber-100/80">
                            InsightOS stores only a secure fingerprint and cannot show this key again.
                          </p>
                          <input
                            className={`${selectClass} mt-2 font-mono text-xs`}
                            readOnly
                            aria-label="One-time local relay connection key"
                            value={privateAIRelayToken}
                            onFocus={(event) => event.currentTarget.select()}
                          />
                          <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-amber-100/80">
                            <li>Download the relay helper.</li>
                            <li>Open a terminal in Downloads and run <code>python insightos-local-relay.py</code>.</li>
                            <li>Paste this one-time key when the helper asks for it.</li>
                            <li>Optional: after discovery, run <code>python insightos-local-relay.py --once --check-model</code> for one made-up compatibility check.</li>
                          </ol>
                        </div>
                      ) : (
                        <p className="mt-3 text-xs leading-5 text-zinc-500">
                          If the one-time key was not saved, revoke this connection and create a new one. InsightOS cannot recover the old key.
                        </p>
                      )}
                      {privateAIRelayDiagnostic ? (
                        <div className="mt-4 rounded-md border border-sky-500/20 bg-sky-500/5 p-3">
                          <p className="text-sm font-semibold text-sky-50">
                            {privateAIRelayDiagnostic.state === "verified"
                              ? "Signed receipt check verified"
                              : privateAIRelayDiagnostic.state === "expired"
                                ? "Signed receipt check expired"
                                : "Signed receipt check waiting for the relay"}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-sky-100/75">
                            This check contains a random synthetic challenge only. It includes no customer data and cannot call a model or run work.
                          </p>
                        </div>
                      ) : null}
                      {privateAIRelayRuntime ? (
                        <div className="mt-4 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                          <p className="text-sm font-semibold text-emerald-50">
                            {privateAIRelayRuntime.runtime_kind === "multiple"
                              ? "Ollama and LM Studio found"
                              : privateAIRelayRuntime.runtime_kind === "ollama"
                                ? "Ollama found"
                                : privateAIRelayRuntime.runtime_kind === "lm_studio"
                                  ? "LM Studio found"
                                  : "No supported local model software found yet"}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-emerald-100/75">
                            {privateAIRelayRuntime.model_count} local {privateAIRelayRuntime.model_count === 1 ? "model" : "models"} available. Model names stayed on this computer.
                          </p>
                          <p className="mt-1 text-xs leading-5 text-emerald-100/75">
                            Discovery only — no customer data was sent and no model was called.
                          </p>
                        </div>
                      ) : privateAIRelay.connection_state === "connected" ? (
                        <p className="mt-3 text-xs leading-5 text-zinc-500">
                          Restart the downloaded helper to check this computer for Ollama or LM Studio. It checks loopback only, keeps model names local, and does not call a model.
                        </p>
                      ) : null}
                      {privateAIRelayQualification ? (
                        <div className={`mt-4 rounded-md border p-3 ${privateAIRelayQualification.status === "passed" ? "border-emerald-500/20 bg-emerald-500/5" : "border-amber-500/20 bg-amber-500/5"}`}>
                          <p className={`text-sm font-semibold ${privateAIRelayQualification.status === "passed" ? "text-emerald-50" : "text-amber-50"}`}>
                            {privateAIRelayQualification.status === "passed"
                              ? "Made-up local model check passed"
                              : "Made-up local model check needs attention"}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-zinc-300">
                            One fixed made-up request was attempted in {privateAIRelayQualification.latency_ms.toLocaleString()} ms. The model name and any response stayed on this computer.
                          </p>
                          <p className="mt-1 text-xs leading-5 text-zinc-400">
                            This result does not enable customer prompts, routing, publishing, website changes, or business-profile work.
                          </p>
                        </div>
                      ) : privateAIRelayRuntime && privateAIRelayRuntime.model_count > 0 ? (
                        <div className="mt-4 rounded-md border border-sky-500/20 bg-sky-500/5 p-3">
                          <p className="text-sm font-semibold text-sky-50">Optional made-up compatibility check</p>
                          <p className="mt-1 text-xs leading-5 text-sky-100/75">
                            Run <code>python insightos-local-relay.py --once --check-model</code>. It calls one local model once with made-up data; the model name and response stay local.
                          </p>
                        </div>
                      ) : null}
                      {privateAIProviderPlanEligible &&
                      privateAIRelay.connection_state === "connected" &&
                      privateAIRelayDiagnostic?.state !== "waiting_for_relay" ? (
                        <button
                          type="button"
                          className={`${secondaryButtonClass} mt-3`}
                          disabled={busyAction === "private-ai-relay-diagnostic"}
                          onClick={() => void createPrivateAIRelayDiagnostic(privateAIRelay.id)}
                        >
                          {busyAction === "private-ai-relay-diagnostic"
                            ? "Preparing check..."
                            : "Prepare signed connection check"}
                        </button>
                      ) : null}
                    </div>
                  ) : privateAIProviderPlanEligible ? (
                    <div className="mt-4">
                      <label className="text-sm font-medium text-zinc-300">
                        Name this computer or relay
                        <input
                          className={`${selectClass} mt-1.5`}
                          value={privateAIRelayName}
                          maxLength={120}
                          onChange={(event) => setPrivateAIRelayName(event.target.value)}
                        />
                      </label>
                      <div className="mt-3 space-y-2 text-sm leading-5 text-zinc-300">
                        {([
                          ["understands_connection_only", "I understand this only creates and verifies an outbound connection."],
                          ["understands_no_customer_prompts", "I understand no customer prompts or saved evidence are available to the relay yet."],
                          ["understands_no_database_or_execution_access", "I understand the relay cannot query the InsightOS database, publish, or execute work."],
                          ["understands_manual_revocation", "I understand I can revoke the connection key here at any time."],
                        ] as Array<[keyof PrivateAIRelayAcknowledgements, string]>).map(([key, label]) => (
                          <label key={key} className="flex items-start gap-2">
                            <input
                              type="checkbox"
                              className="mt-0.5"
                              checked={privateAIRelayAcks[key]}
                              onChange={(event) => setPrivateAIRelayAcks((current) => ({
                                ...current,
                                [key]: event.target.checked,
                              }))}
                            />
                            <span>{label}</span>
                          </label>
                        ))}
                      </div>
                      <button
                        type="button"
                        className={`${primaryButtonClass} mt-3`}
                        disabled={!allPrivateAIRelayAcknowledged || privateAIRelayName.trim().length < 2 || busyAction === "private-ai-relay-create"}
                        onClick={() => void createPrivateAIRelay()}
                      >
                        {busyAction === "private-ai-relay-create" ? "Creating key..." : "Create one-time connection key"}
                      </button>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-zinc-400">
                      Local relay setup is Enterprise-only and is not included with Growth ($699/month). Any existing connection history remains visible and its key can still be revoked.
                    </p>
                  )}

                  <p className="mt-3 text-xs leading-5 text-zinc-500">
                    The heartbeat is empty unless the owner prepares one short-lived synthetic receipt check. It exposes no customer prompt, model call, database, website, business-profile, publishing, or execution access.
                  </p>
                </div>

                {privateAIProviderLoadState === "unavailable" ? (
                  <div className="mt-5 rounded-md border border-amber-500/20 bg-amber-500/5 p-4 text-sm leading-6 text-amber-50">
                    <p className="font-semibold">Private AI candidate status is unavailable</p>
                    <p className="mt-1 text-amber-100/80">
                      InsightOS will not assume there are no saved candidates or start a new setup until the current status can be checked.
                    </p>
                    <button
                      type="button"
                      className={`${secondaryButtonClass} mt-3`}
                      disabled={busyAction === "private-ai-refresh"}
                      onClick={() => void refreshPrivateAIProviders()}
                    >
                      {busyAction === "private-ai-refresh" ? "Checking..." : "Check candidates again"}
                    </button>
                  </div>
                ) : privateAIProviders.length > 0 ? (
                  <div className="mt-5 space-y-4">
                    {privateAIProviders.map((provider) => {
                      const benchmarks = privateAIBenchmarks[provider.id] || [];
                      const latestBenchmark = benchmarks[0];
                      const savedReview = latestBenchmark
                        ? (privateAIReviews[provider.id] || []).find(
                            (item) => item.benchmark_id === latestBenchmark.id,
                          )
                        : undefined;
                      const standby = privateAIStandby[provider.id];
                      const readiness = privateAIReadiness[provider.id];
                      const canary = privateAICanary[provider.id];
                      const canaryMonitoring = privateAICanaryMonitoring[provider.id];
                      const questionCapability = privateAIQuestionCapability[provider.id];
                      const draftCapability = privateAIDraftCapability[provider.id];
                      const keywordReviewQualification = privateAIKeywordReviewQualification[provider.id];
                      const contentDraftQualification = privateAIContentDraftQualification[provider.id];
                      const baselineQualification = privateAIBaselineQualification[provider.id];
                      const reviewResponseQualification = privateAIReviewResponseQualification[provider.id];
                      const canaryAcknowledgements = privateAICanaryAcks[provider.id]
                        || EMPTY_PRIVATE_AI_CANARY_ACKNOWLEDGEMENTS;
                      const allCanaryAcknowledged = Object.values(canaryAcknowledgements).every(Boolean);
                      const questionAcknowledgements = privateAIQuestionAcks[provider.id]
                        || EMPTY_PRIVATE_AI_QUESTION_ACKNOWLEDGEMENTS;
                      const allQuestionAcknowledged = Object.values(questionAcknowledgements).every(Boolean);
                      const draftAcknowledgements = privateAIDraftAcks[provider.id]
                        || EMPTY_PRIVATE_AI_DRAFT_ACKNOWLEDGEMENTS;
                      const allDraftAcknowledged = Object.values(draftAcknowledgements).every(Boolean);
                      const keywordReviewAcknowledgements = privateAIKeywordReviewAcks[provider.id]
                        || EMPTY_PRIVATE_AI_KEYWORD_REVIEW_ACKNOWLEDGEMENTS;
                      const allKeywordReviewAcknowledged = Object.values(keywordReviewAcknowledgements).every(Boolean);
                      const contentDraftAcknowledgements = privateAIContentDraftAcks[provider.id]
                        || EMPTY_PRIVATE_AI_CONTENT_DRAFT_ACKNOWLEDGEMENTS;
                      const allContentDraftAcknowledged = Object.values(contentDraftAcknowledgements).every(Boolean);
                      const baselineAcknowledgements = privateAIBaselineAcks[provider.id]
                        || EMPTY_PRIVATE_AI_BASELINE_ACKNOWLEDGEMENTS;
                      const allBaselineAcknowledged = Object.values(baselineAcknowledgements).every(Boolean);
                      const reviewResponseAcknowledgements = privateAIReviewResponseAcks[provider.id]
                        || EMPTY_PRIVATE_AI_REVIEW_RESPONSE_ACKNOWLEDGEMENTS;
                      const allReviewResponseAcknowledged = Object.values(reviewResponseAcknowledgements).every(Boolean);
                      const acknowledgements = latestBenchmark
                        ? privateAIReviewAcks[latestBenchmark.id] || EMPTY_PRIVATE_AI_ACKNOWLEDGEMENTS
                        : EMPTY_PRIVATE_AI_ACKNOWLEDGEMENTS;
                      const allAcknowledged = Object.values(acknowledgements).every(Boolean);
                      const standbyAcknowledgements = savedReview
                        ? privateAIStandbyAcks[savedReview.id] || EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS
                        : EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS;
                      const allStandbyAcknowledged = Object.values(standbyAcknowledgements).every(Boolean);
                      return (
                        <article key={provider.id} className="rounded-md border border-[#303137] bg-[#101114] p-4">
                          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-semibold text-white">{provider.name}</h3>
                                <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${standby?.state === "standby" ? "border-sky-500/25 bg-sky-500/10 text-sky-100" : "border-zinc-500/25 bg-zinc-500/10 text-zinc-300"}`}>
                                  {standby?.state === "standby" ? "Zero-traffic standby" : "Inactive candidate"}
                                </span>
                              </div>
                              <p className="mt-1 text-sm text-zinc-400">
                                {provider.endpoint_host} · {provider.model_identifier}
                              </p>
                              <p className="mt-1 text-xs text-zinc-500">
                                Credential {provider.credential_configured ? "saved securely" : "not required"}
                                {provider.last_validated_at
                                  ? ` · Last checked ${formatTimestamp(provider.last_validated_at)}`
                                  : " · Not checked yet"}
                              </p>
                              {provider.billing_boundary ? (
                                <p className="mt-1 text-xs text-zinc-500">
                                  Provider charges stay with your provider account; InsightOS does not add private-model usage fees.
                                </p>
                              ) : null}
                            </div>
                            <button
                              type="button"
                              className={secondaryButtonClass}
                              disabled={busyAction === `private-ai-disconnect-${provider.id}`}
                              onClick={() => void disconnectPrivateAIProvider(provider.id)}
                            >
                              {busyAction === `private-ai-disconnect-${provider.id}` ? "Disconnecting..." : "Disconnect"}
                            </button>
                          </div>

                          {provider.supported_capabilities?.length ? (
                            <details className="mt-4 rounded-md border border-[#292a2f] bg-[#141518] px-4 py-3">
                              <summary className="cursor-pointer text-sm font-semibold text-white">
                                What this connection can be checked for
                              </summary>
                              <p className="mt-2 text-sm leading-6 text-zinc-400">
                                Each item requires its own compatibility result and owner approval. Listing it here does not turn it on.
                              </p>
                              <div className="mt-3 grid gap-2 md:grid-cols-2">
                                {provider.supported_capabilities.map((capability) => (
                                  <div key={capability.code} className="rounded-md border border-[#292a2f] px-3 py-2.5">
                                    <p className="text-sm font-medium text-zinc-200">{capability.label}</p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-500">{capability.summary}</p>
                                  </div>
                                ))}
                              </div>
                              <p className="mt-3 text-xs leading-5 text-zinc-500">
                                Every approved check remains fixed at 5%, shares one private prompt per day, keeps managed AI as fallback, and cannot publish or make changes.
                              </p>
                            </details>
                          ) : null}

                          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                            <div className="border-l-2 border-[#303137] pl-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Network</p>
                              <p className="mt-1 text-sm font-semibold text-white">
                                {provider.network_validation_status === "passed" ? "Public endpoint checked" : provider.network_validation_status === "failed" ? "Needs attention" : "Not checked"}
                              </p>
                            </div>
                            <div className="border-l-2 border-[#303137] pl-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Standby</p>
                              <p className="mt-1 text-sm font-semibold text-white">
                                {standby?.state === "standby"
                                  ? "Registered · 0% traffic"
                                  : standby?.state === "standby_elsewhere"
                                    ? "Another candidate selected"
                                    : standby?.state === "unavailable"
                                      ? "Status unavailable"
                                      : "Not registered"}
                              </p>
                            </div>
                            <div className="border-l-2 border-[#303137] pl-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Connection</p>
                              <p className="mt-1 text-sm font-semibold text-white">
                                {provider.validation_status === "passed" ? "Structured response passed" : provider.validation_status === "failed" ? "Validation failed" : "Not validated"}
                              </p>
                            </div>
                            <div className="border-l-2 border-[#303137] pl-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Quality review</p>
                              <p className="mt-1 text-sm font-semibold text-white">
                                {savedReview?.decision === "approved_for_future_activation"
                                  ? "Recorded for a later standby step"
                                  : savedReview?.decision === "rejected"
                                    ? "Declined"
                                    : latestBenchmark?.status === "passed"
                                      ? "Ready for owner review"
                                      : latestBenchmark?.status === "failed"
                                        ? "Checks did not pass"
                                        : "Not run"}
                              </p>
                            </div>
                          </div>

                          <div className="mt-4 flex flex-wrap gap-2">
                            {provider.network_validation_status !== "passed" ? (
                              <button
                                type="button"
                                className={secondaryButtonClass}
                                disabled={busyAction === `private-ai-preflight-${provider.id}`}
                                onClick={() => void preflightPrivateAIProvider(provider.id)}
                              >
                                {busyAction === `private-ai-preflight-${provider.id}` ? "Checking network..." : "Check public network"}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className={secondaryButtonClass}
                              disabled={busyAction === `private-ai-validate-${provider.id}`}
                              onClick={() => void validatePrivateAIProvider(provider.id)}
                            >
                              {busyAction === `private-ai-validate-${provider.id}`
                                ? "Validating..."
                                : provider.validation_status === "passed"
                                  ? "Revalidate connection"
                                  : "Validate connection"}
                            </button>
                            {provider.validation_status === "passed" ? (
                              <button
                                type="button"
                                className={primaryButtonClass}
                                disabled={busyAction === `private-ai-benchmark-${provider.id}`}
                                onClick={() => void benchmarkPrivateAIProvider(provider.id)}
                              >
                                {busyAction === `private-ai-benchmark-${provider.id}`
                                  ? "Running three checks..."
                                  : latestBenchmark
                                    ? "Run quality checks again"
                                    : "Run three quality checks"}
                              </button>
                            ) : null}
                          </div>

                          {latestBenchmark ? (
                            <div className="mt-4 border-t border-[#292a2f] pt-4">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <p className="text-sm font-semibold text-white">Latest synthetic quality checks</p>
                                <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${latestBenchmark.status === "passed" ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-rose-500/25 bg-rose-500/10 text-rose-100"}`}>
                                  {latestBenchmark.passed_case_count} of 3 passed
                                </span>
                              </div>
                              <div className="mt-3 grid gap-2 md:grid-cols-3">
                                {latestBenchmark.case_results.map((result) => (
                                  <div key={result.case_id} className="rounded-md border border-[#292a2f] px-3 py-2.5">
                                    <p className="text-sm font-medium text-zinc-200">{privateAIBenchmarkCaseLabel(result.case_id)}</p>
                                    <p className={`mt-1 text-xs ${result.passed ? "text-emerald-300" : "text-rose-200"}`}>
                                      {result.passed ? "Passed" : "Did not pass"}
                                    </p>
                                  </div>
                                ))}
                              </div>
                              <p className="mt-2 text-xs leading-5 text-zinc-500">
                                Synthetic checks are limited examples, not a promise about every future answer.
                              </p>
                            </div>
                          ) : null}

                          {latestBenchmark?.status === "passed" && !savedReview ? (
                            <div className="mt-4 rounded-md border border-accent-500/25 bg-accent-500/5 p-4">
                              <h4 className="font-semibold text-white">Owner review</h4>
                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                Approval records eligibility for a separate future standby step. It does not activate this provider.
                              </p>
                              <div className="mt-3 space-y-2 text-sm text-zinc-300">
                                {([
                                  ["reviewed_synthetic_results", "I reviewed the three synthetic results."],
                                  ["understands_not_active", "I understand this does not activate or route to this provider."],
                                  ["understands_managed_fallback_required", "I understand the managed provider must remain available as fallback."],
                                  ["understands_no_automatic_changes", "I understand this does not authorize automatic website or business-profile changes."],
                                ] as Array<[keyof PrivateAIReviewAcknowledgements, string]>).map(([key, label]) => (
                                  <label key={key} className="flex items-start gap-2">
                                    <input
                                      type="checkbox"
                                      className="mt-1"
                                      checked={acknowledgements[key]}
                                      onChange={(event) =>
                                        setPrivateAIReviewAcks((current) => ({
                                          ...current,
                                          [latestBenchmark.id]: {
                                            ...(current[latestBenchmark.id] || EMPTY_PRIVATE_AI_ACKNOWLEDGEMENTS),
                                            [key]: event.target.checked,
                                          },
                                        }))
                                      }
                                    />
                                    <span>{label}</span>
                                  </label>
                                ))}
                              </div>
                              <div className="mt-4 flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  className={primaryButtonClass}
                                  disabled={!allAcknowledged || busyAction === `private-ai-review-${provider.id}`}
                                  onClick={() => void reviewPrivateAIProvider(provider.id, latestBenchmark.id, "approved_for_future_activation")}
                                >
                                  {busyAction === `private-ai-review-${provider.id}` ? "Saving review..." : "Approve for a later standby step"}
                                </button>
                                <button
                                  type="button"
                                  className={secondaryButtonClass}
                                  disabled={!acknowledgements.reviewed_synthetic_results || busyAction === `private-ai-review-${provider.id}`}
                                  onClick={() => void reviewPrivateAIProvider(provider.id, latestBenchmark.id, "rejected")}
                                >
                                  Decline this benchmark
                                </button>
                              </div>
                            </div>
                          ) : savedReview ? (
                            <div className="mt-4 rounded-md border border-[#303137] bg-[#17181b] px-4 py-3 text-sm leading-6 text-zinc-300">
                              <p className="font-semibold text-white">
                                {savedReview.decision === "approved_for_future_activation"
                                  ? "Owner approval recorded — still inactive"
                                  : "Owner declined this benchmark"}
                              </p>
                              <p className="mt-1">
                                This permanent review was saved {formatTimestamp(savedReview.reviewed_at)}.
                                {savedReview.decision === "approved_for_future_activation"
                                  ? readiness?.latest?.status === "passed"
                                    ? " The fallback check passed, but routing remains off and still requires separate approval."
                                    : " Zero-traffic standby and a fallback readiness check are still required before any future routing review."
                                  : " You may run a new benchmark later without changing this record."}
                              </p>
                              {savedReview.decision === "approved_for_future_activation" ? (
                                standby?.state === "unavailable" ? (
                                  <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 text-amber-50">
                                    Standby status is unavailable. InsightOS will not assume this provider is inactive or offer a state change until it can be checked.
                                  </div>
                                ) : standby?.state === "standby" ? (
                                  <div className="mt-3 rounded-md border border-sky-500/20 bg-sky-500/5 p-3 text-sky-50">
                                    <p className="font-semibold">Registered in zero-traffic standby</p>
                                    <p className="mt-1 text-sky-100/80">
                                      InsightOS&apos;s managed AI still handles every live request. This private provider receives 0% traffic and no customer prompts.
                                    </p>
                                    <div className="mt-3 rounded-md border border-[#303137] bg-[#101114] p-3 text-zinc-300">
                                      <div className="flex flex-wrap items-start justify-between gap-2">
                                        <div>
                                          <p className="font-semibold text-white">Live-routing safety check</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-400">
                                            Confirms that the managed AI has a recent successful result and remains available as the rollback path. This check does not turn on private-model traffic.
                                          </p>
                                        </div>
                                        {readiness?.latest ? (
                                          <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${readiness.latest.status === "passed" ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-amber-500/25 bg-amber-500/10 text-amber-100"}`}>
                                            {readiness.latest.status === "passed" ? "Prerequisites passed" : "Needs attention"}
                                          </span>
                                        ) : null}
                                      </div>
                                      <p className="mt-2 text-sm leading-6 text-zinc-400">
                                        {readiness?.truth.summary || "Fallback readiness has not been checked yet."}
                                      </p>
                                      {readiness?.latest?.blockers.length ? (
                                        <ul className="mt-2 space-y-1 text-sm text-amber-100">
                                          {readiness.latest.blockers.map((blocker) => (
                                            <li key={blocker.code}>• {blocker.summary}</li>
                                          ))}
                                        </ul>
                                      ) : null}
                                      {readiness?.latest ? (
                                        <p className="mt-2 text-xs leading-5 text-zinc-500">
                                          Last 30 days: {readiness.latest.usage.managed_successes} managed successes, {readiness.latest.usage.managed_fallbacks} fallbacks, and {readiness.latest.usage.candidate_runs} private-provider runs.
                                        </p>
                                      ) : null}
                                      <button
                                        type="button"
                                        className={`${secondaryButtonClass} mt-3`}
                                        disabled={busyAction === `private-ai-readiness-${provider.id}`}
                                        onClick={() => void checkPrivateAIRoutingReadiness(provider.id)}
                                      >
                                        {busyAction === `private-ai-readiness-${provider.id}`
                                          ? "Checking fallback..."
                                          : readiness?.latest
                                            ? "Check fallback again"
                                            : "Check fallback readiness"}
                                      </button>
                                      {canary?.state === "unavailable" ? (
                                        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 text-sm text-amber-50">
                                          Limited routing status is unavailable. InsightOS will not offer a traffic change until it can be checked.
                                        </div>
                                      ) : canary?.state === "canary" ? (
                                        <div className="mt-3 rounded-md border border-violet-500/25 bg-violet-500/10 p-3 text-violet-50">
                                          <div className="flex flex-wrap items-start justify-between gap-2">
                                            <div>
                                              <p className="font-semibold">Limited private-AI check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-violet-100/80">
                                                Up to 5% of eligible daily explanations may use this provider, with a hard limit of one private prompt per day. All other AI requests stay managed by InsightOS.
                                              </p>
                                            </div>
                                            <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-xs font-semibold">
                                              5% maximum · 1 per day
                                            </span>
                                          </div>
                                          <p className="mt-2 text-sm leading-6 text-violet-100/80">
                                            If the private result fails its network, format, evidence, or safety check, InsightOS stops the canary and retries through managed AI. It can never change a website or business profile.
                                          </p>
                                          <p className="mt-2 text-xs leading-5 text-violet-100/70">
                                            Last 30 days: {canary.usage.private_successes} private successes, {canary.usage.managed_fallbacks} managed fallbacks, and {canary.usage.automatic_rollbacks} automatic stops.
                                          </p>
                                          <button
                                            type="button"
                                            className={`${secondaryButtonClass} mt-3`}
                                            disabled={busyAction === `private-ai-canary-${provider.id}`}
                                            onClick={() => void updatePrivateAICanary(provider.id, "disable")}
                                          >
                                            {busyAction === `private-ai-canary-${provider.id}` ? "Stopping..." : "Stop limited private-AI check"}
                                          </button>
                                        </div>
                                      ) : canary?.state === "needs_attention" ? (
                                        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-50">
                                          <p className="font-semibold">The saved limited check is paused</p>
                                          <p className="mt-1 leading-6 text-amber-100/80">
                                            Its safety evidence is no longer current, so no private prompts can be sent. Stop this saved check, refresh the required evidence, and review it again before restarting.
                                          </p>
                                          <button
                                            type="button"
                                            className={`${secondaryButtonClass} mt-3`}
                                            disabled={busyAction === `private-ai-canary-${provider.id}`}
                                            onClick={() => void updatePrivateAICanary(provider.id, "disable")}
                                          >
                                            {busyAction === `private-ai-canary-${provider.id}` ? "Stopping..." : "Stop outdated private-AI check"}
                                          </button>
                                        </div>
                                      ) : canary?.state === "canary_elsewhere" ? (
                                        <p className="mt-3 text-sm text-amber-100">
                                          Another private provider already has the workspace&apos;s limited check.
                                        </p>
                                      ) : readiness?.latest?.status === "passed" ? (
                                        <div className="mt-3 rounded-md border border-violet-500/20 bg-violet-500/5 p-3">
                                          <p className="font-semibold text-white">Try a limited private-AI check</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-400">
                                            This is the first step that can send a real daily-explanation prompt to your private provider. The limit is fixed at 5%, never more than one prompt per day, with managed fallback reserved first.
                                          </p>
                                          <div className="mt-3 space-y-2">
                                            {([
                                              ["reviewed_five_percent_limit", "I reviewed the fixed 5% and one-prompt-per-day limits."],
                                              ["understands_real_customer_prompt", "I understand this can send one real customer-context prompt to my private provider."],
                                              ["understands_managed_fallback_required", "I understand InsightOS managed AI remains required as the fallback."],
                                              ["understands_automatic_rollback", "I understand any private-provider failure automatically stops this check."],
                                              ["understands_no_automatic_changes", "I understand this cannot change a website, listing, or business profile."],
                                            ] as Array<[keyof PrivateAICanaryAcknowledgements, string]>).map(([key, label]) => (
                                              <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                <input
                                                  type="checkbox"
                                                  className="mt-0.5"
                                                  checked={canaryAcknowledgements[key]}
                                                  onChange={(event) => {
                                                    const checked = event.target.checked;
                                                    setPrivateAICanaryAcks((current) => ({
                                                      ...current,
                                                      [provider.id]: {
                                                        ...canaryAcknowledgements,
                                                        [key]: checked,
                                                      },
                                                    }));
                                                  }}
                                                />
                                                <span>{label}</span>
                                              </label>
                                            ))}
                                          </div>
                                          <button
                                            type="button"
                                            className={`${primaryButtonClass} mt-3`}
                                            disabled={!allCanaryAcknowledged || busyAction === `private-ai-canary-${provider.id}`}
                                            onClick={() => void updatePrivateAICanary(provider.id, "enable")}
                                          >
                                            {busyAction === `private-ai-canary-${provider.id}` ? "Starting..." : "Start fixed 5% private-AI check"}
                                          </button>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "unavailable" ? (
                                        <div className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 text-sm text-amber-50">
                                          Private-AI health history is unavailable. This does not change the fixed check or managed fallback.
                                        </div>
                                      ) : canaryMonitoring && canaryMonitoring.state !== "not_started" ? (
                                        <div className={`mt-3 rounded-md border p-3 ${
                                          canaryMonitoring.state === "eligible_for_later_review"
                                            ? "border-emerald-500/25 bg-emerald-500/5"
                                            : canaryMonitoring.state === "blocked"
                                              ? "border-amber-500/25 bg-amber-500/5"
                                              : "border-sky-500/20 bg-sky-500/5"
                                        }`}>
                                          <p className="font-semibold text-white">
                                            {canaryMonitoring.state === "eligible_for_later_review"
                                              ? "Minimum health evidence collected"
                                              : canaryMonitoring.state === "blocked"
                                                ? "Health review has a blocker"
                                                : "Collecting health evidence"}
                                          </p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            {canaryMonitoring.truth.summary}
                                          </p>
                                          <p className="mt-2 text-xs leading-5 text-zinc-400">
                                            Successful days: {canaryMonitoring.evidence.distinct_success_days} of 3 · Private successes: {canaryMonitoring.evidence.private_successes} · Managed fallbacks: {canaryMonitoring.evidence.managed_fallbacks} · Automatic stops: {canaryMonitoring.evidence.automatic_rollbacks}
                                            {canaryMonitoring.evidence.max_latency_ms > 0
                                              ? ` · Slowest successful response: ${canaryMonitoring.evidence.max_latency_ms} ms`
                                              : ""}
                                          </p>
                                          {canaryMonitoring.evidence.blockers.length > 0 ? (
                                            <ul className="mt-2 space-y-1 text-sm leading-5 text-zinc-300">
                                              {canaryMonitoring.evidence.blockers.map((blocker) => (
                                                <li key={blocker.code}>• {blocker.summary}</li>
                                              ))}
                                            </ul>
                                          ) : null}
                                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                                            This review cannot increase traffic, add prompt types, or authorize automatic changes.
                                          </p>
                                          <button
                                            type="button"
                                            className={`${secondaryButtonClass} mt-3`}
                                            disabled={busyAction === `private-ai-canary-monitoring-${provider.id}`}
                                            onClick={() => void savePrivateAICanaryHealthReview(provider.id)}
                                          >
                                            {busyAction === `private-ai-canary-monitoring-${provider.id}`
                                              ? "Saving review..."
                                              : canaryMonitoring.latest
                                                ? "Save another health review"
                                                : "Save health review"}
                                          </button>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-violet-500/20 bg-violet-500/5 p-3">
                                          <p className="font-semibold text-white">Saved-evidence questions</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can answer a customer&apos;s question using only InsightOS&apos;s saved evidence and saved action IDs. The compatibility check uses synthetic data and sends no customer prompt.
                                          </p>
                                          {questionCapability?.state === "unavailable" || !questionCapability ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              Saved-question status is unavailable, so InsightOS will not offer this capability.
                                            </p>
                                          ) : questionCapability.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited saved-question check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of eligible saved-evidence questions may use this provider. Daily explanations and questions share one total private prompt per day. Any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {questionCapability.usage.private_successes} · Managed fallbacks: {questionCapability.usage.managed_fallbacks} · Automatic stops: {questionCapability.usage.automatic_rollbacks}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-question-${provider.id}`}
                                                onClick={() => void updatePrivateAIQuestionCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-question-${provider.id}` ? "Stopping..." : "Stop saved-question check"}
                                              </button>
                                            </div>
                                          ) : questionCapability.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Synthetic compatibility check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_question_capability_check", "I reviewed the saved-question compatibility result."],
                                                  ["understands_real_customer_questions", "I understand this can send a real customer question and its saved evidence to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand questions and daily explanations share one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_no_automatic_changes", "I understand answers cannot change a website, listing, or business profile."],
                                                ] as Array<[keyof PrivateAIQuestionCapabilityAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={questionAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIQuestionAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...questionAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allQuestionAcknowledged || busyAction === `private-ai-question-${provider.id}`}
                                                onClick={() => void updatePrivateAIQuestionCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-question-${provider.id}` ? "Starting..." : "Start fixed 5% saved-question check"}
                                              </button>
                                            </div>
                                          ) : questionCapability.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited question capability.</p>
                                          ) : questionCapability.state === "needs_attention" ? (
                                            <div className="mt-2 text-sm text-amber-100">
                                              This capability stopped because its saved evidence is no longer current. Run the compatibility check again after refreshing health evidence.
                                            </div>
                                          ) : (
                                            <div className="mt-3">
                                              {questionCapability.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last synthetic compatibility check did not pass. No customer question was sent.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-question-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIQuestionCapability(provider.id)}
                                              >
                                                {busyAction === `private-ai-question-benchmark-${provider.id}` ? "Checking..." : "Check saved-question compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability can only explain saved evidence. It cannot create, approve, publish, or execute work.
                                          </p>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-fuchsia-500/20 bg-fuchsia-500/5 p-3">
                                          <p className="font-semibold text-white">Saved-action draft wording</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can prepare review-only wording for one action already saved in InsightOS. The compatibility check uses synthetic information and sends no customer data.
                                          </p>
                                          {draftCapability?.state === "unavailable" || !draftCapability ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              Draft-wording status is unavailable, so InsightOS will keep using managed AI.
                                            </p>
                                          ) : draftCapability.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited draft-wording check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of eligible draft requests may use this provider. Explanations, questions, and drafts share one total private prompt per day. Every draft still requires review, and any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {draftCapability.usage.private_successes} · Managed fallbacks: {draftCapability.usage.managed_fallbacks} · Automatic stops: {draftCapability.usage.automatic_rollbacks}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-draft-${provider.id}`}
                                                onClick={() => void updatePrivateAIDraftCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-draft-${provider.id}` ? "Stopping..." : "Stop draft-wording check"}
                                              </button>
                                            </div>
                                          ) : draftCapability.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Synthetic draft check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_draft_capability_check", "I reviewed the draft-wording compatibility result."],
                                                  ["understands_real_saved_action_context", "I understand this can send one saved action and its supporting information to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand explanations, questions, and drafts share one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_draft_only_no_publish", "I understand this can only prepare a draft for review and cannot publish or make changes."],
                                                ] as Array<[keyof PrivateAIDraftCapabilityAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={draftAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIDraftAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...draftAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allDraftAcknowledged || busyAction === `private-ai-draft-${provider.id}`}
                                                onClick={() => void updatePrivateAIDraftCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-draft-${provider.id}` ? "Starting..." : "Start fixed 5% draft-wording check"}
                                              </button>
                                            </div>
                                          ) : draftCapability.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited draft-wording capability.</p>
                                          ) : draftCapability.state === "needs_attention" ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              This capability stopped because its saved evidence is no longer current. Refresh the health review before checking it again.
                                            </p>
                                          ) : (
                                            <div className="mt-3">
                                              {draftCapability.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last synthetic draft check did not pass. No customer information was sent.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-draft-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIDraftCapability(provider.id)}
                                              >
                                                {busyAction === `private-ai-draft-benchmark-${provider.id}` ? "Checking..." : "Check draft-wording compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability can only prepare review-only wording for a saved action. It cannot approve, publish, send, or execute work.
                                          </p>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-cyan-500/20 bg-cyan-500/5 p-3">
                                          <p className="font-semibold text-white">Unclear search review</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can sort one made-up unclear search against a made-up service and work area. No customer searches, website information, or account data are sent.
                                          </p>
                                          {keywordReviewQualification?.state === "unavailable" || !keywordReviewQualification ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              This compatibility check is unavailable. Managed AI remains unchanged.
                                            </p>
                                          ) : keywordReviewQualification.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited unclear-search check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of owner-requested unclear-search reviews may use this provider. Explanations, saved questions, drafts, and search reviews share one total private prompt per day. Any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {keywordReviewQualification.usage.private_successes} · Managed fallbacks: {keywordReviewQualification.usage.managed_fallbacks} · Automatic stops: {keywordReviewQualification.usage.automatic_rollbacks}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-keyword-review-${provider.id}`}
                                                onClick={() => void updatePrivateAIKeywordReviewCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-keyword-review-${provider.id}` ? "Stopping..." : "Stop unclear-search check"}
                                              </button>
                                            </div>
                                          ) : keywordReviewQualification.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Synthetic unclear-search check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_keyword_review_check", "I reviewed the unclear-search compatibility result."],
                                                  ["understands_real_saved_search_context", "I understand this can send selected unclear searches plus confirmed services and work areas to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand explanations, questions, drafts, and search reviews share one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_saved_search_classification_only", "I understand a valid result may sort or hide only the unclear saved searches I asked InsightOS to review. It cannot add searches, start tracking, create work, or publish anything."],
                                                ] as Array<[keyof PrivateAIKeywordReviewAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={keywordReviewAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIKeywordReviewAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...keywordReviewAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allKeywordReviewAcknowledged || busyAction === `private-ai-keyword-review-${provider.id}`}
                                                onClick={() => void updatePrivateAIKeywordReviewCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-keyword-review-${provider.id}` ? "Starting..." : "Start fixed 5% unclear-search check"}
                                              </button>
                                            </div>
                                          ) : keywordReviewQualification.state === "eligible_for_later_review" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Synthetic unclear-search check passed</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                This only proves the provider understood the fixed example. Customer traffic remains off because this release does not include the owner approval boundary.
                                              </p>
                                            </div>
                                          ) : keywordReviewQualification.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited unclear-search capability.</p>
                                          ) : (
                                            <div className="mt-3">
                                              {keywordReviewQualification.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last synthetic check did not pass. No customer information was sent.</p>
                                              ) : keywordReviewQualification.state === "needs_attention" ? (
                                                <p className="mb-2 text-sm text-amber-100">The saved check is no longer current. Refresh health evidence, then run it again.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-keyword-review-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIKeywordReviewQualification(provider.id)}
                                              >
                                                {busyAction === `private-ai-keyword-review-benchmark-${provider.id}` ? "Checking..." : "Check unclear-search compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability can only classify the server-selected unclear searches in an owner-requested review. It cannot add or track searches, create work, change a website or business profile, or publish anything.
                                          </p>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-cyan-500/20 bg-cyan-500/5 p-3">
                                          <p className="font-semibold text-white">Optional website draft wording</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can prepare safe wording for a made-up website draft and preserve the exact section order and evidence. No customer website, draft, search, or account data is sent.
                                          </p>
                                          {!contentDraftQualification || contentDraftQualification.state === "unavailable" ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              This compatibility check is unavailable. Managed AI remains unchanged.
                                            </p>
                                          ) : contentDraftQualification.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited website-draft check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of owner-requested optional website wording may use this provider. All private-AI capabilities share one total private prompt per day. Any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {contentDraftQualification.usage.private_successes} · Managed fallbacks: {contentDraftQualification.usage.managed_fallbacks} · Automatic stops: {contentDraftQualification.usage.automatic_rollbacks}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-content-draft-${provider.id}`}
                                                onClick={() => void updatePrivateAIContentDraftCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-content-draft-${provider.id}` ? "Stopping..." : "Stop website-draft check"}
                                              </button>
                                            </div>
                                          ) : contentDraftQualification.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Synthetic website-draft check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_content_draft_check", "I reviewed the website-draft compatibility result."],
                                                  ["understands_real_saved_website_draft_context", "I understand this can send one selected saved website draft, accepted brief, and allowed evidence to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand every private-AI capability shares one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_suggestion_only_no_edit_or_publish", "I understand a valid result remains a separate suggestion. It cannot edit my draft, approve wording, publish a page, or change my website or business profile."],
                                                ] as Array<[keyof PrivateAIContentDraftAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={contentDraftAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIContentDraftAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...contentDraftAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allContentDraftAcknowledged || busyAction === `private-ai-content-draft-${provider.id}`}
                                                onClick={() => void updatePrivateAIContentDraftCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-content-draft-${provider.id}` ? "Starting..." : "Start fixed 5% website-draft check"}
                                              </button>
                                            </div>
                                          ) : contentDraftQualification.state === "eligible_for_later_review" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Synthetic website-draft check passed</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                This only proves the provider understood the fixed example. Customer traffic remains off, and there is no approval or enable control in this release.
                                              </p>
                                            </div>
                                          ) : contentDraftQualification.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited website-draft capability.</p>
                                          ) : (
                                            <div className="mt-3">
                                              {contentDraftQualification.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last synthetic check did not pass. No customer information was sent.</p>
                                              ) : contentDraftQualification.state === "needs_attention" ? (
                                                <p className="mb-2 text-sm text-amber-100">The saved check is no longer current. Refresh health evidence, then run it again.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-content-draft-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIContentDraftQualification(provider.id)}
                                              >
                                                {busyAction === `private-ai-content-draft-benchmark-${provider.id}` ? "Checking..." : "Check website-draft compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability can only prepare a separate review-only suggestion for the exact saved draft the owner selected. It cannot edit the owner draft, approve wording, publish a page, or change a website or business profile.
                                          </p>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-cyan-500/20 bg-cyan-500/5 p-3">
                                          <p className="font-semibold text-white">Optional baseline explanation</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can explain a made-up onboarding baseline without changing its saved score, diagnosis, evidence, or fixed priorities. No customer website, Google data, traffic, ranking, or account information is sent.
                                          </p>
                                          {!baselineQualification || baselineQualification.state === "unavailable" ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              This compatibility check is unavailable. Managed AI remains unchanged.
                                            </p>
                                          ) : baselineQualification.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited baseline explanation check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of owner-requested baseline explanations may use this provider. Every private-AI capability shares one total private prompt per day. Any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {baselineQualification.usage.private_successes} · Managed fallbacks: {baselineQualification.usage.managed_fallbacks} · Automatic stops: {baselineQualification.usage.automatic_rollbacks}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-baseline-${provider.id}`}
                                                onClick={() => void updatePrivateAIBaselineCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-baseline-${provider.id}` ? "Stopping..." : "Stop baseline explanation check"}
                                              </button>
                                            </div>
                                          ) : baselineQualification.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Made-up baseline check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_baseline_check", "I reviewed the baseline compatibility result."],
                                                  ["understands_real_saved_baseline_context", "I understand this can send one selected saved baseline's minimized evidence, deterministic scores, and fixed priority order to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand every private-AI capability shares one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_explanation_only_no_changes", "I understand this can only explain saved results. It cannot change scores, diagnoses, fixes, priorities, the website, the business profile, or approve or run work."],
                                                ] as Array<[keyof PrivateAIBaselineAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={baselineAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIBaselineAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...baselineAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allBaselineAcknowledged || busyAction === `private-ai-baseline-${provider.id}`}
                                                onClick={() => void updatePrivateAIBaselineCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-baseline-${provider.id}` ? "Starting..." : "Start fixed 5% baseline explanation check"}
                                              </button>
                                            </div>
                                          ) : baselineQualification.state === "eligible_for_later_review" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Made-up baseline check passed</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                This only proves the provider understood the fixed example. Real onboarding baseline data remains off, and there is no approval or enable control in this release.
                                              </p>
                                            </div>
                                          ) : baselineQualification.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited baseline-explanation capability.</p>
                                          ) : (
                                            <div className="mt-3">
                                              {baselineQualification.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last made-up baseline check did not pass. No customer information was sent.</p>
                                              ) : baselineQualification.state === "needs_attention" ? (
                                                <p className="mb-2 text-sm text-amber-100">The saved check is no longer current. Refresh health evidence, then run it again.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-baseline-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIBaselineQualification(provider.id)}
                                              >
                                                {busyAction === `private-ai-baseline-benchmark-${provider.id}` ? "Checking..." : "Check baseline compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability can only explain a frozen saved baseline. It cannot change the score, diagnosis, priorities, fixes, website, or business profile, and it cannot approve or run work.
                                          </p>
                                        </div>
                                      ) : null}
                                      {canaryMonitoring?.state === "eligible_for_later_review" ? (
                                        <div className="mt-3 rounded-md border border-cyan-500/20 bg-cyan-500/5 p-3">
                                          <p className="font-semibold text-white">Optional review reply wording</p>
                                          <p className="mt-1 text-sm leading-6 text-zinc-300">
                                            Check whether this provider can draft a safe reply for a made-up review while preserving owner approval. No customer review, customer name, business account, or profile data is sent.
                                          </p>
                                          {!reviewResponseQualification || reviewResponseQualification.state === "unavailable" ? (
                                            <p className="mt-2 text-sm text-amber-100">
                                              This compatibility check is unavailable. Managed AI remains unchanged.
                                            </p>
                                          ) : reviewResponseQualification.state === "capability_canary" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Limited review-reply wording check is on</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                Up to 5% of owner-requested reply drafts may use this provider. Every private-AI capability shares one total private prompt per day. Any failure stops this capability and uses managed AI.
                                              </p>
                                              <p className="mt-2 text-xs text-zinc-400">
                                                Private successes: {reviewResponseQualification.usage?.private_successes || 0} · Managed fallbacks: {reviewResponseQualification.usage?.managed_fallbacks || 0} · Automatic stops: {reviewResponseQualification.usage?.automatic_rollbacks || 0}
                                              </p>
                                              <button
                                                type="button"
                                                className={`${secondaryButtonClass} mt-3`}
                                                disabled={busyAction === `private-ai-review-response-${provider.id}`}
                                                onClick={() => void updatePrivateAIReviewResponseCapability(provider.id, "disable")}
                                              >
                                                {busyAction === `private-ai-review-response-${provider.id}` ? "Stopping..." : "Stop review-reply wording check"}
                                              </button>
                                            </div>
                                          ) : reviewResponseQualification.state === "eligible_for_owner_approval" ? (
                                            <div className="mt-3">
                                              <p className="text-sm font-medium text-emerald-100">Made-up review reply check passed</p>
                                              <div className="mt-3 space-y-2">
                                                {([
                                                  ["reviewed_review_reply_check", "I reviewed the made-up review-reply compatibility result."],
                                                  ["understands_real_saved_review_context", "I understand this can send one selected saved review and the minimum confirmed business context to my private provider."],
                                                  ["understands_shared_daily_limit", "I understand every private-AI capability shares one private prompt per day."],
                                                  ["understands_managed_fallback_and_rollback", "I understand managed AI remains reserved and any private failure stops this capability."],
                                                  ["understands_draft_only_no_posting", "I understand every result remains a separate draft. It cannot approve or post a reply, change review status, publish, or change the business profile."],
                                                ] as Array<[keyof PrivateAIReviewResponseAcknowledgements, string]>).map(([key, label]) => (
                                                  <label key={key} className="flex items-start gap-2 text-sm leading-5 text-zinc-300">
                                                    <input
                                                      type="checkbox"
                                                      className="mt-0.5"
                                                      checked={reviewResponseAcknowledgements[key]}
                                                      onChange={(event) => setPrivateAIReviewResponseAcks((current) => ({
                                                        ...current,
                                                        [provider.id]: {
                                                          ...reviewResponseAcknowledgements,
                                                          [key]: event.target.checked,
                                                        },
                                                      }))}
                                                    />
                                                    <span>{label}</span>
                                                  </label>
                                                ))}
                                              </div>
                                              <button
                                                type="button"
                                                className={`${primaryButtonClass} mt-3`}
                                                disabled={!allReviewResponseAcknowledged || busyAction === `private-ai-review-response-${provider.id}`}
                                                onClick={() => void updatePrivateAIReviewResponseCapability(provider.id, "enable")}
                                              >
                                                {busyAction === `private-ai-review-response-${provider.id}` ? "Starting..." : "Start fixed 5% review-reply wording check"}
                                              </button>
                                            </div>
                                          ) : reviewResponseQualification.state === "eligible_for_later_review" ? (
                                            <div className="mt-3 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-3">
                                              <p className="font-medium text-emerald-50">Made-up review reply check passed</p>
                                              <p className="mt-1 text-sm leading-6 text-zinc-300">
                                                This proves only compatibility. Customer reviews remain off, and there is no approval or enable control in this release.
                                              </p>
                                            </div>
                                          ) : reviewResponseQualification.state === "capability_canary_elsewhere" ? (
                                            <p className="mt-2 text-sm text-amber-100">Another private provider already owns this limited review-reply capability.</p>
                                          ) : (
                                            <div className="mt-3">
                                              {reviewResponseQualification.state === "qualification_failed" ? (
                                                <p className="mb-2 text-sm text-amber-100">The last made-up review reply check did not pass. No customer information was sent.</p>
                                              ) : reviewResponseQualification.state === "needs_attention" ? (
                                                <p className="mb-2 text-sm text-amber-100">The saved check is no longer current. Refresh health evidence, then run it again.</p>
                                              ) : null}
                                              <button
                                                type="button"
                                                className={secondaryButtonClass}
                                                disabled={busyAction === `private-ai-review-response-benchmark-${provider.id}`}
                                                onClick={() => void benchmarkPrivateAIReviewResponseQualification(provider.id)}
                                              >
                                                {busyAction === `private-ai-review-response-benchmark-${provider.id}` ? "Checking..." : "Check review-reply compatibility"}
                                              </button>
                                            </div>
                                          )}
                                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                                            This capability would only prepare a separate draft. It cannot approve or post a reply, change review status, publish, or change the business profile.
                                          </p>
                                        </div>
                                      ) : null}
                                    </div>
                                    <button
                                      type="button"
                                      className={`${secondaryButtonClass} mt-3`}
                                      disabled={busyAction === `private-ai-standby-${provider.id}`}
                                      onClick={() => void updatePrivateAIStandby(provider.id, null, "disable")}
                                    >
                                      {busyAction === `private-ai-standby-${provider.id}` ? "Removing..." : "Remove from standby"}
                                    </button>
                                  </div>
                                ) : standby?.state === "standby_elsewhere" ? (
                                  <p className="mt-3 text-amber-100">
                                    Another candidate is already in standby. Remove it before selecting this one.
                                  </p>
                                ) : (
                                  <div className="mt-3 rounded-md border border-sky-500/20 bg-sky-500/5 p-3">
                                    <p className="font-semibold text-white">Register as zero-traffic standby</p>
                                    <p className="mt-1 text-zinc-300">
                                      This records operational readiness and a manual removal path. It does not send customer data or change the live managed route.
                                    </p>
                                    <div className="mt-3 space-y-2">
                                      {([
                                        ["reviewed_standby_boundary", "I reviewed what zero-traffic standby means."],
                                        ["understands_zero_customer_prompts", "I understand this provider will receive no customer prompts."],
                                        ["understands_managed_route_unchanged", "I understand InsightOS's managed AI remains the only live route."],
                                        ["understands_manual_disable_available", "I understand I can remove this standby registration here."],
                                      ] as Array<[keyof PrivateAIStandbyAcknowledgements, string]>).map(([key, label]) => (
                                        <label key={key} className="flex items-start gap-2">
                                          <input
                                            type="checkbox"
                                            className="mt-1"
                                            checked={standbyAcknowledgements[key]}
                                            onChange={(event) =>
                                              setPrivateAIStandbyAcks((current) => ({
                                                ...current,
                                                [savedReview.id]: {
                                                  ...(current[savedReview.id] || EMPTY_PRIVATE_AI_STANDBY_ACKNOWLEDGEMENTS),
                                                  [key]: event.target.checked,
                                                },
                                              }))
                                            }
                                          />
                                          <span>{label}</span>
                                        </label>
                                      ))}
                                    </div>
                                    <button
                                      type="button"
                                      className={`${primaryButtonClass} mt-3`}
                                      disabled={!allStandbyAcknowledged || busyAction === `private-ai-standby-${provider.id}`}
                                      onClick={() => void updatePrivateAIStandby(provider.id, savedReview.id, "enable")}
                                    >
                                      {busyAction === `private-ai-standby-${provider.id}` ? "Registering..." : "Register zero-traffic standby"}
                                    </button>
                                  </div>
                                )
                              ) : null}
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="mt-5 text-sm text-zinc-400">No private AI candidate has been saved.</p>
                )}

                {privateAIProviderPlanEligible && privateAIProviderLoadState === "ready" ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-5">
                    <h3 className="font-semibold text-white">Add an inactive candidate</h3>
                    <p className="mt-1 text-sm leading-6 text-zinc-400">
                      Use a reachable HTTPS OpenAI-compatible endpoint. Localhost and private network addresses cannot be reached from InsightOS.
                    </p>
                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      <label className="text-sm font-medium text-zinc-300">
                        Connection name
                        <input
                          className={`${selectClass} mt-1.5`}
                          value={privateAIName}
                          maxLength={120}
                          onChange={(event) => setPrivateAIName(event.target.value)}
                          placeholder="Approved private model"
                        />
                      </label>
                      <label className="text-sm font-medium text-zinc-300">
                        Model identifier
                        <input
                          className={`${selectClass} mt-1.5`}
                          value={privateAIModel}
                          maxLength={200}
                          onChange={(event) => setPrivateAIModel(event.target.value)}
                          placeholder="organization/model-name"
                        />
                      </label>
                      <label className="text-sm font-medium text-zinc-300 lg:col-span-2">
                        HTTPS chat-completions endpoint
                        <input
                          className={`${selectClass} mt-1.5`}
                          type="url"
                          value={privateAIEndpoint}
                          maxLength={2000}
                          onChange={(event) => setPrivateAIEndpoint(event.target.value)}
                          placeholder="https://models.example.com/v1/chat/completions"
                        />
                      </label>
                      <label className="text-sm font-medium text-zinc-300 lg:col-span-2">
                        API key (optional)
                        <input
                          className={`${selectClass} mt-1.5`}
                          type="password"
                          autoComplete="new-password"
                          value={privateAIApiKey}
                          maxLength={4096}
                          onChange={(event) => setPrivateAIApiKey(event.target.value)}
                          placeholder="Stored encrypted and never shown again"
                        />
                      </label>
                    </div>
                    <button
                      type="button"
                      className={`${primaryButtonClass} mt-4`}
                      disabled={
                        !privateAIName.trim() ||
                        !privateAIEndpoint.trim() ||
                        !privateAIModel.trim() ||
                        busyAction === "private-ai-create"
                      }
                      onClick={() => void createPrivateAIProvider()}
                    >
                      {busyAction === "private-ai-create" ? "Saving encrypted candidate..." : "Save inactive candidate"}
                    </button>
                  </div>
                ) : !privateAIProviderPlanEligible ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-4 text-sm leading-6 text-zinc-400">
                    Adding or approving a new private AI provider requires Enterprise. Existing candidates and permanent review history remain visible.
                  </div>
                ) : null}
              </section>
            ) : null}

            <section id="google-search-console-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Google Search Console
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.connected
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.connected ? "Google connected" : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    Shows how often your website appears in Google Search, how many visits it
                    earns, and its average search position. Search Console normally reports with
                    a short delay, so the newest available day may be about two days old.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={!payload?.google_oauth.connected || loadingResources}
                    onClick={() => void loadResources(organizationId)}
                  >
                    {loadingResources ? "Loading websites..." : "Load available websites"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-gsc"}
                    onClick={() => void connectGoogle()}
                  >
                    {payload?.google_oauth.connected ? "Reconnect Google" : "Connect Google"}
                  </button>
                </div>
              </div>
            </section>

            {!payload?.google_oauth.connected ? (
              <EmptyState
                title="Connect Google to begin"
                summary="You will approve read-only Search Console access. InsightOS stores the connection securely and never receives your Google password."
                actionLabel="Connect Google Search Console"
                onAction={() => void connectGoogle()}
              />
            ) : manageableCampaigns.length === 0 ? (
              <EmptyState
                title="Add a business location first"
                summary="Every automatic data source must map to a real business location so results never blend between accounts."
                actionLabel="Manage locations"
                onAction={() => window.location.assign("/locations")}
              />
            ) : (
              <section id="website-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match websites to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Each location keeps its own mapping and sync history. A shared domain property
                    represents the whole website unless that location owns a separate URL-prefix property.
                  </p>
                </div>

                {manageableCampaigns.map((campaign) => {
                  const connection = connectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource = resourceDrafts[campaign.id] || connection?.external_resource_id || "";
                  return (
                    <article
                      key={campaign.id}
                      className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
                    >
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.8fr)_auto] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-semibold text-white">{campaign.name}</h3>
                            {statusView ? (
                              <span
                                className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClasses(statusView.tone)}`}
                              >
                                {statusView.label}
                              </span>
                            ) : (
                              <span className="rounded-full border border-zinc-500/25 bg-zinc-500/10 px-2.5 py-1 text-xs font-semibold text-zinc-300">
                                Website not matched
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-sm text-zinc-400">
                            {connection?.business_location_name || campaign.domain}
                          </p>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful update: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the Search Console property that belongs to this location's website."}
                          </p>
                          {connection?.last_error_message ? (
                            <p className="mt-2 text-xs leading-5 text-rose-200">
                              {connection.last_error_message}
                            </p>
                          ) : null}
                        </div>

                        <div>
                          <label
                            htmlFor={`resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Search Console website
                          </label>
                          <select
                            id={`resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={resources.length === 0 || Boolean(connection?.last_success_at)}
                            onChange={(event) =>
                              setResourceDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {resources.length === 0
                                ? "Load available websites first"
                                : "Choose a website"}
                            </option>
                            {resources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name} · {resource.permission_level.replaceAll("_", " ")}
                              </option>
                            ))}
                            {connection && !resources.some((resource) => resource.id === connection.external_resource_id) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                          {connection ? (
                            <p className="mt-1.5 text-xs text-zinc-500">
                              {connection.resource_scope === "domain_property"
                                ? "Whole-domain website property"
                                : "URL-prefix website property"}
                            </p>
                          ) : null}
                        </div>

                        <div className="flex lg:justify-end">
                          {connection ? (
                            <button
                              className={secondaryButtonClass}
                              disabled={
                                busyAction === `sync-${connection.id}` ||
                                connection.status === "syncing"
                              }
                              onClick={() => void syncConnection(connection)}
                            >
                              {busyAction === `sync-${connection.id}`
                                ? "Updating..."
                                : statusView?.action || "Check now"}
                            </button>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveMapping(campaign)}
                            >
                              {busyAction === `mapping-${campaign.id}`
                                ? "Connecting..."
                                : "Connect and start first sync"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            )}

            <section id="google-business-profile-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Google business listing
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.approved_access?.business_profile
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.approved_access?.business_profile
                        ? "Access approved"
                        : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    Match each location to the listing customers see on Google. InsightOS will
                    check its details, save changes, and show calls, website clicks, directions,
                    appearances, and customer search terms when Google makes them available.
                  </p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                    InsightOS will not edit the listing automatically. Any future change will
                    require review and approval first.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={
                      !payload?.google_oauth.approved_access?.business_profile || loadingResources
                    }
                    onClick={() => void loadProfileResources(organizationId)}
                  >
                    {loadingResources ? "Loading listings..." : "Load available listings"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-gbp"}
                    onClick={() => void connectGoogle("gbp")}
                  >
                    {payload?.google_oauth.approved_access?.business_profile
                      ? "Reconnect listing access"
                      : "Connect business listings"}
                  </button>
                </div>
              </div>
            </section>

            {!payload?.google_oauth.approved_access?.business_profile ? (
              <EmptyState
                title="Connect the Google account that manages your listings"
                summary="Google requires separate permission before InsightOS can read a business listing. Your Google password is never shared with InsightOS."
                actionLabel="Connect Google business listings"
                onAction={() => void connectGoogle("gbp")}
              />
            ) : manageableCampaigns.length > 0 ? (
              <section id="profile-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match listings to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    One listing can belong to only one location. This prevents results from two
                    locations being mixed together.
                  </p>
                </div>
                {manageableCampaigns.map((campaign) => {
                  const connection = profileConnectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource =
                    profileDrafts[campaign.id] || connection?.external_resource_id || "";
                  const selectedProfile = profileResources.find(
                    (resource) => resource.id === selectedResource,
                  );
                  return (
                    <article
                      key={`profile-${campaign.id}`}
                      className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
                    >
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.9fr)_auto] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-semibold text-white">{campaign.name}</h3>
                            <span
                              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                                statusView
                                  ? toneClasses(statusView.tone)
                                  : "border-zinc-500/25 bg-zinc-500/10 text-zinc-300"
                              }`}
                            >
                              {statusView?.label || "Listing not matched"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful check: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the listing customers see for this business location."}
                          </p>
                          {connection?.last_error_message ? (
                            <p className="mt-2 text-xs leading-5 text-rose-200">
                              {connection.last_error_message}
                            </p>
                          ) : null}
                        </div>
                        <div>
                          <label
                            htmlFor={`profile-resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Google business listing
                          </label>
                          <select
                            id={`profile-resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={
                              profileResources.length === 0 || Boolean(connection?.last_success_at)
                            }
                            onChange={(event) =>
                              setProfileDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {profileResources.length === 0
                                ? "Load available listings first"
                                : "Choose a listing"}
                            </option>
                            {profileResources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name}
                                {resource.address ? ` · ${resource.address}` : ""}
                              </option>
                            ))}
                            {connection &&
                            !profileResources.some(
                              (resource) => resource.id === connection.external_resource_id,
                            ) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                          {selectedProfile ? (
                            <p className="mt-1.5 text-xs leading-5 text-zinc-500">
                              {selectedProfile.primary_category || "Category not returned"}
                              {selectedProfile.verified ? " · Verified listing" : ""}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {connection?.last_success_at ? (
                            <button
                              className={secondaryButtonClass}
                              onClick={() => window.location.assign("/local-visibility")}
                            >
                              See listing results
                            </button>
                          ) : null}
                          {connection ? (
                            <button
                              className={secondaryButtonClass}
                              disabled={
                                busyAction === `sync-${connection.id}` ||
                                connection.status === "syncing"
                              }
                              onClick={() => void syncConnection(connection)}
                            >
                              {busyAction === `sync-${connection.id}`
                                ? "Checking..."
                                : statusView?.action || "Check now"}
                            </button>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `profile-mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveProfileMapping(campaign)}
                            >
                              {busyAction === `profile-mapping-${campaign.id}`
                                ? "Matching..."
                                : "Match and run first check"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : null}

            <section id="google-analytics-connection" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                      Website visits and inquiries
                    </h2>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        payload?.google_oauth.approved_access?.website_analytics
                          ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100"
                          : "border-amber-500/25 bg-amber-500/10 text-amber-100"
                      }`}
                    >
                      {payload?.google_oauth.approved_access?.website_analytics
                        ? "Access approved"
                        : "Connection required"}
                    </span>
                  </div>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-300">
                    See how many people visit the website, how many stay and engage, and how many
                    complete an approved inquiry action. Each location keeps its own history.
                  </p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                    This is read-only. CRM, call tracking, sales, and payment data are not included.
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className={secondaryButtonClass}
                    disabled={
                      !payload?.google_oauth.approved_access?.website_analytics || loadingResources
                    }
                    onClick={() => void loadAnalyticsResources(organizationId)}
                  >
                    {loadingResources ? "Loading properties..." : "Load analytics properties"}
                  </button>
                  <button
                    className={primaryButtonClass}
                    disabled={busyAction === "oauth-analytics"}
                    onClick={() => void connectGoogle("analytics")}
                  >
                    {payload?.google_oauth.approved_access?.website_analytics
                      ? "Reconnect website analytics"
                      : "Connect website analytics"}
                  </button>
                </div>
              </div>
            </section>

            {payload?.google_oauth.approved_access?.website_analytics && manageableCampaigns.length > 0 ? (
              <section id="analytics-mappings" className="space-y-3">
                <div>
                  <h2 className="text-xl font-semibold tracking-[-0.03em] text-white">
                    Match analytics to locations
                  </h2>
                  <p className="mt-1 text-sm text-zinc-400">
                    Choose the property that measures each location&apos;s website. This keeps results
                    from separate businesses from being mixed together.
                  </p>
                </div>
                {manageableCampaigns.map((campaign) => {
                  const connection = analyticsConnectionByCampaign.get(campaign.id);
                  const statusView = connection ? getConnectionStatusView(connection) : null;
                  const selectedResource =
                    analyticsDrafts[campaign.id] || connection?.external_resource_id || "";
                  return (
                    <article
                      key={`analytics-${campaign.id}`}
                      className="rounded-md border border-[#292a2f] bg-[#141518] p-5"
                    >
                      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(300px,0.9fr)_auto] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-semibold text-white">{campaign.name}</h3>
                            <span
                              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                                statusView
                                  ? toneClasses(statusView.tone)
                                  : "border-zinc-500/25 bg-zinc-500/10 text-zinc-300"
                              }`}
                            >
                              {statusView?.label || "Analytics not matched"}
                            </span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-zinc-500">
                            {connection
                              ? `${statusView?.summary} Last successful update: ${formatTimestamp(connection.last_success_at)}.`
                              : "Choose the website analytics property for this business location."}
                          </p>
                          {connection?.website_event_key_configured ? (
                            <p className="mt-2 text-xs font-medium text-emerald-200">
                              Secure website inquiry connection created
                            </p>
                          ) : null}
                          {connection && websiteEventKeys[connection.id] ? (
                            <div className="mt-3 rounded-md border border-amber-500/25 bg-amber-500/10 p-3">
                              <p className="text-xs font-semibold text-amber-100">
                                Copy this private form key now
                              </p>
                              <code className="mt-2 block break-all text-xs leading-5 text-amber-50">
                                {websiteEventKeys[connection.id].token}
                              </code>
                              <p className="mt-2 text-xs leading-5 text-amber-100/75">
                                Event address: {websiteEventKeys[connection.id].event_path}
                              </p>
                            </div>
                          ) : null}
                        </div>
                        <div>
                          <label
                            htmlFor={`analytics-resource-${campaign.id}`}
                            className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500"
                          >
                            Website analytics property
                          </label>
                          <select
                            id={`analytics-resource-${campaign.id}`}
                            className={selectClass}
                            value={selectedResource}
                            disabled={
                              analyticsResources.length === 0 || Boolean(connection?.last_success_at)
                            }
                            onChange={(event) =>
                              setAnalyticsDrafts((current) => ({
                                ...current,
                                [campaign.id]: event.target.value,
                              }))
                            }
                          >
                            <option value="">
                              {analyticsResources.length === 0
                                ? "Load available properties first"
                                : "Choose a property"}
                            </option>
                            {analyticsResources.map((resource) => (
                              <option key={resource.id} value={resource.id}>
                                {resource.name} · {resource.account_name}
                              </option>
                            ))}
                            {connection &&
                            !analyticsResources.some(
                              (resource) => resource.id === connection.external_resource_id,
                            ) ? (
                              <option value={connection.external_resource_id}>
                                {connection.external_resource_name || connection.external_resource_id}
                              </option>
                            ) : null}
                          </select>
                        </div>
                        <div className="flex flex-wrap gap-2 lg:justify-end">
                          {connection ? (
                            <>
                              <button
                                className={secondaryButtonClass}
                                disabled={busyAction === `website-event-key-${connection.id}`}
                                onClick={() => void createWebsiteEventKey(connection)}
                              >
                                {busyAction === `website-event-key-${connection.id}`
                                  ? "Creating..."
                                  : connection.website_event_key_configured
                                    ? "Replace form key"
                                    : "Create form connection"}
                              </button>
                              <button
                                className={secondaryButtonClass}
                                disabled={
                                  busyAction === `sync-${connection.id}` ||
                                  connection.status === "syncing"
                                }
                                onClick={() => void syncConnection(connection)}
                              >
                                {busyAction === `sync-${connection.id}`
                                  ? "Updating..."
                                  : statusView?.action || "Check now"}
                              </button>
                            </>
                          ) : (
                            <button
                              className={primaryButtonClass}
                              disabled={
                                busyAction === `analytics-mapping-${campaign.id}` ||
                                !selectedResource
                              }
                              onClick={() => void saveAnalyticsMapping(campaign)}
                            >
                              {busyAction === `analytics-mapping-${campaign.id}`
                                ? "Connecting..."
                                : "Match and start first update"}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : null}

            {me?.org_role === "org_owner" ? (
              <section aria-labelledby="account-data-heading" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Your account data
                    </p>
                    <h2 id="account-data-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      Download a copy of your saved business information
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      Create a portable JSON file containing your locations, members, tracked searches, measurements, recommendations, report records, recipients, and import history.
                    </p>
                  </div>
                  <button
                    type="button"
                    className={primaryButtonClass}
                    disabled={busyAction === "data-export-create"}
                    onClick={() => void createAccountExport()}
                  >
                    {busyAction === "data-export-create" ? "Creating export..." : "Create account export"}
                  </button>
                </div>

                <div className="mt-5 grid gap-4 border-t border-[#292a2f] pt-5 lg:grid-cols-2">
                  <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4">
                    <p className="text-sm font-semibold text-emerald-100">Private by design</p>
                    <p className="mt-1 text-sm leading-6 text-zinc-300">
                      Passwords, login sessions, connected-account credentials, payment-provider identifiers, and internal security evidence are never placed in the file.
                    </p>
                  </div>
                  <div className="rounded-md border border-sky-500/20 bg-sky-500/5 p-4">
                    <p className="text-sm font-semibold text-sky-100">Available for seven days</p>
                    <p className="mt-1 text-sm leading-6 text-zinc-300">
                      Only an account owner can create or download an export. The downloadable copy expires after seven days; its audit record remains.
                    </p>
                  </div>
                </div>

                {dataExports.length > 0 ? (
                  <div className="mt-5 border-t border-[#292a2f] pt-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Recent exports
                    </p>
                    <div className="mt-3 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                      {dataExports.slice(0, 5).map((item) => {
                        const savedRecords = Object.values(item.record_counts || {}).reduce(
                          (total, value) => total + Number(value || 0),
                          0,
                        );
                        const statusLabel = item.status === "ready"
                          ? "Ready"
                          : item.status === "expired"
                            ? "Expired"
                            : "Could not be created";
                        return (
                          <div key={item.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                            <div>
                              <p className="text-sm font-semibold text-white">{statusLabel}</p>
                              <p className="mt-1 text-xs leading-5 text-zinc-500">
                                Created {formatTimestamp(item.completed_at || item.requested_at)} · {savedRecords.toLocaleString()} saved records · {formatFileSize(item.artifact_byte_size)}
                              </p>
                              <p className="mt-1 text-xs leading-5 text-zinc-500">
                                {item.download_available
                                  ? `Download available until ${formatTimestamp(item.expires_at)}`
                                  : item.failure_code
                                    ? "This export was not stored. Create a new copy or contact support."
                                    : "The downloadable copy is no longer stored."}
                              </p>
                            </div>
                            {item.download_available ? (
                              <button
                                type="button"
                                className={secondaryButtonClass}
                                disabled={busyAction === `data-export-download-${item.id}`}
                                onClick={() => void downloadAccountExport(item)}
                              >
                                {busyAction === `data-export-download-${item.id}` ? "Downloading..." : "Download JSON"}
                              </button>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <p className="mt-5 border-t border-[#292a2f] pt-5 text-sm text-zinc-400">
                    No account exports have been created yet.
                  </p>
                )}
              </section>
            ) : null}

            {me?.org_role === "org_owner" && closurePreview ? (
              <section aria-labelledby="workspace-closure-heading" className="rounded-md border border-rose-500/20 bg-[#141518] p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Workspace control
                    </p>
                    <h2 id="workspace-closure-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      Delete this workspace safely
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      Account deletion is staged so a mistake does not erase the business&apos;s history. The workspace becomes read-only for {closurePreview.recovery_days} days before credentials and login sessions are removed.
                    </p>
                  </div>
                  {!closurePreview.current_request && closureReviewStep === 0 ? (
                    <button
                      type="button"
                      className="inline-flex items-center justify-center rounded-md border border-rose-500/35 bg-rose-500/10 px-3.5 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={!closurePreview.can_request}
                      onClick={() => setClosureReviewStep(1)}
                    >
                      Review account deletion
                    </button>
                  ) : null}
                </div>

                {closurePreview.blockers.length > 0 ? (
                  <div className="mt-5 rounded-md border border-amber-500/25 bg-amber-500/10 p-4">
                    <p className="text-sm font-semibold text-amber-100">Finish this first</p>
                    {closurePreview.blockers.map((blocker) => (
                      <p key={blocker.code} className="mt-1 text-sm leading-6 text-amber-50/80">
                        {blocker.message}
                      </p>
                    ))}
                  </div>
                ) : null}

                {closurePreview.current_request ? (
                  <div className="mt-5 rounded-md border border-sky-500/25 bg-sky-500/5 p-5">
                    <p className="text-base font-semibold text-white">
                      {closurePreview.current_request.status === "recovery_window"
                        ? "Closure scheduled — recovery window open"
                        : closurePreview.current_request.status === "on_hold"
                          ? "Closure paused by a retention requirement"
                          : "Workspace closed — verified deletion is pending"}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      {closurePreview.current_request.status === "recovery_window"
                        ? `The workspace is read-only. An account owner can reopen it until ${formatTimestamp(closurePreview.current_request.recovery_until)}.`
                        : closurePreview.current_request.status === "on_hold"
                          ? "Data cannot move to deletion while a required retention hold is active. The private reason is not shown in the customer workspace."
                          : "Connected credentials and login sessions were removed. Primary business data is not claimed deleted until dependency-order, backup, and verification checks finish."}
                    </p>
                    {closurePreview.current_request.can_cancel ? (
                      <button
                        type="button"
                        className={`${secondaryButtonClass} mt-4`}
                        disabled={busyAction === "workspace-reopen"}
                        onClick={() => void cancelWorkspaceClosure(closurePreview.current_request!)}
                      >
                        {busyAction === "workspace-reopen" ? "Reopening safely..." : "Keep workspace open"}
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {closureReviewStep === 1 && !closurePreview.current_request ? (
                  <div className="mt-5 rounded-md border border-rose-500/30 bg-rose-500/5 p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-rose-200">
                      Step 1 of {closurePreview.confirmation_steps}
                    </p>
                    <p className="mt-1 text-base font-semibold text-rose-100">Review what account deletion will do</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Create and download an account export first if you need a portable copy. Starting deletion revokes public report links and cancels queued work immediately; those security actions are not reversed if you reopen the workspace.
                    </p>
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      <div>
                        <p className="text-sm font-semibold text-white">This stops immediately</p>
                        <ul className="mt-2 space-y-2 text-sm leading-5 text-zinc-300">
                          {closurePreview.what_stops.map((item) => (
                            <li key={item}>× {item}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">These safeguards remain</p>
                        <ul className="mt-2 space-y-2 text-sm leading-5 text-zinc-300">
                          {closurePreview.what_stays.map((item) => (
                            <li key={item}>✓ {item}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    <div className="mt-5 flex flex-wrap gap-3 border-t border-rose-500/20 pt-4">
                      <button
                        type="button"
                        className="inline-flex items-center justify-center rounded-md border border-rose-500/40 bg-rose-500/15 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/25"
                        onClick={() => setClosureReviewStep(2)}
                      >
                        Continue to final confirmation
                      </button>
                      <button
                        type="button"
                        className={secondaryButtonClass}
                        onClick={() => {
                          setClosureReviewStep(0);
                          setClosureConfirmation("");
                          setClosureExportChoiceAcknowledged(false);
                          setClosureRecoveryAcknowledged(false);
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}

                {closureReviewStep === 2 && !closurePreview.current_request ? (
                  <div className="mt-5 rounded-md border border-rose-500/40 bg-rose-500/5 p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-rose-200">
                      Step 2 of {closurePreview.confirmation_steps}
                    </p>
                    <p className="mt-1 text-base font-semibold text-rose-100">Final account-deletion confirmation</p>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      This starts a {closurePreview.recovery_days}-day recovery window. The workspace becomes read-only now; permanent deletion is not claimed until the later deletion and verification work finishes.
                    </p>

                    <div className="mt-5 space-y-3">
                      <label className="flex cursor-pointer items-start gap-3 rounded-md border border-[#303137] bg-[#101114] p-4 text-sm leading-6 text-zinc-200">
                        <input
                          id="closure-export-choice"
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-rose-500"
                          checked={closureExportChoiceAcknowledged}
                          onChange={(event) => setClosureExportChoiceAcknowledged(event.target.checked)}
                        />
                        <span>I downloaded an account export, or I decided I do not need one.</span>
                      </label>
                      <label className="flex cursor-pointer items-start gap-3 rounded-md border border-[#303137] bg-[#101114] p-4 text-sm leading-6 text-zinc-200">
                        <input
                          id="closure-recovery-acknowledgement"
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-rose-500"
                          checked={closureRecoveryAcknowledged}
                          onChange={(event) => setClosureRecoveryAcknowledged(event.target.checked)}
                        />
                        <span>
                          I understand that I have {closurePreview.recovery_days} days to reopen the workspace before permanent deletion work can begin.
                        </span>
                      </label>
                    </div>

                    <div className="mt-5 border-t border-rose-500/20 pt-4">
                      <label htmlFor="workspace-closure-confirmation" className="block text-sm font-semibold text-white">
                        Type <span className="font-mono text-rose-200">{closurePreview.confirmation_text}</span> to confirm
                      </label>
                      <input
                        id="workspace-closure-confirmation"
                        type="text"
                        autoComplete="off"
                        spellCheck={false}
                        className="mt-2 w-full max-w-md rounded-md border border-[#3a3b41] bg-[#101114] px-3 py-2.5 text-sm text-white outline-none focus:border-rose-400/60"
                        value={closureConfirmation}
                        onChange={(event) => setClosureConfirmation(event.target.value)}
                      />
                      <p className="mt-2 text-xs leading-5 text-zinc-500">
                        The word must match exactly, including the capital D.
                      </p>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          type="button"
                          className="inline-flex items-center justify-center rounded-md border border-rose-500/40 bg-rose-500/15 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={
                            closureConfirmation !== closurePreview.confirmation_text ||
                            !closureExportChoiceAcknowledged ||
                            !closureRecoveryAcknowledged ||
                            busyAction === "workspace-closure" ||
                            !closurePreview.can_request
                          }
                          onClick={() => void scheduleWorkspaceClosure()}
                        >
                          {busyAction === "workspace-closure" ? "Starting safely..." : "Start account deletion"}
                        </button>
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          disabled={busyAction === "workspace-closure"}
                          onClick={() => setClosureReviewStep(1)}
                        >
                          Back
                        </button>
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          disabled={busyAction === "workspace-closure"}
                          onClick={() => {
                            setClosureReviewStep(0);
                            setClosureConfirmation("");
                            setClosureExportChoiceAcknowledged(false);
                            setClosureRecoveryAcknowledged(false);
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}

                {closureHistory.some((item) => item.status === "cancelled") && !closurePreview.current_request ? (
                  <p className="mt-5 border-t border-[#292a2f] pt-4 text-xs leading-5 text-zinc-500">
                    A previous closure request was canceled. Its audit history remains, while revoked public links and canceled jobs stay closed for safety.
                  </p>
                ) : null}
              </section>
            ) : null}

            {usageAllowance.external_automation ? (
                  <section id="external-automation" aria-labelledby="workflow-tools-heading" className="scroll-mt-24 rounded-md border border-[#292a2f] bg-[#141518] p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                      Workflow tools
                    </p>
                    <h2 id="workflow-tools-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                      {usageAllowance.external_automation.gateway_enabled
                        ? "Connect Zapier, Make, Pipedream, or n8n"
                        : `Workflow connections require ${usageAllowance.external_automation.required_plan}`}
                    </h2>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                      Start with the result you want: send InsightOS updates to another tool, or let a workflow request only the saved work you explicitly allow. InsightOS never needs your workflow-tool password.
                    </p>
                    {usageAllowance.external_automation.gateway_enabled ? (
                      <div className="mt-4 grid gap-3 md:grid-cols-2" aria-label="Choose a workflow direction">
                        <button
                          type="button"
                          aria-pressed={automationWorkflowDirection === "outgoing"}
                          className={`rounded-md border p-4 text-left transition ${automationWorkflowDirection === "outgoing" ? "border-sky-500/40 bg-sky-500/10" : "border-[#303137] bg-[#101114] hover:border-[#414249]"}`}
                          onClick={() => setAutomationWorkflowDirection("outgoing")}
                        >
                          <p className="text-sm font-semibold text-white">Send updates to another tool</p>
                          <p className="mt-1 text-xs leading-5 text-zinc-400">Notify a workflow when a report, recommendation, or approved result is ready.</p>
                          <span className="mt-3 inline-flex text-xs font-semibold text-sky-300">
                            {automationWorkflowDirection === "outgoing" ? "Selected" : "Choose outgoing updates"}
                          </span>
                        </button>
                        <button
                          type="button"
                          aria-pressed={automationWorkflowDirection === "incoming"}
                          className={`rounded-md border p-4 text-left transition ${automationWorkflowDirection === "incoming" ? "border-sky-500/40 bg-sky-500/10" : "border-[#303137] bg-[#101114] hover:border-[#414249]"}`}
                          onClick={() => setAutomationWorkflowDirection("incoming")}
                        >
                          <p className="text-sm font-semibold text-white">Let a workflow request saved work</p>
                          <p className="mt-1 text-xs leading-5 text-zinc-400">Create a private key with exact location and action permissions.</p>
                          <span className="mt-3 inline-flex text-xs font-semibold text-sky-300">
                            {automationWorkflowDirection === "incoming" ? "Selected" : "Choose incoming requests"}
                          </span>
                        </button>
                      </div>
                    ) : null}
                    {automationWorkflowDirection === "outgoing" ? (
                    <div id="workflow-updates" className="scroll-mt-24">
                    <h3 className="mt-5 text-sm font-semibold text-white">Send updates to another tool</h3>
                    <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                      Choose what InsightOS should notify you about, paste the receiving URL from your workflow tool, then send a test.
                    </p>
                    {usageAllowance.external_automation.gateway_enabled ? (
                      <ol className="mt-4 grid gap-2 md:grid-cols-3">
                        {[
                          ["1", "Create a receiving webhook", "Open your workflow tool and add its webhook trigger."],
                          ["2", "Paste its URL here", "Use the production URL generated by that tool."],
                          ["3", "Save and send a test", "Confirm the test arrives before relying on live updates."],
                        ].map(([number, title, description]) => (
                          <li key={number} className="rounded-md border border-[#303137] bg-[#101114] p-3">
                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-white">{number}</span>
                            <p className="mt-2 text-sm font-semibold text-white">{title}</p>
                            <p className="mt-1 text-xs leading-5 text-zinc-400">{description}</p>
                          </li>
                        ))}
                      </ol>
                    ) : null}

                    {automationSigningSecret ? (
                      <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-4">
                        <p className="text-sm font-semibold text-amber-100">Keep this workflow security key private</p>
                        <p className="mt-1 text-xs leading-5 text-amber-100/80">
                          Advanced workflows use this one-time key to confirm that updates came from InsightOS. Save it in your workflow tool&apos;s private credential area. It will not be shown again after you leave this page.
                        </p>
                        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                          <input
                            aria-label="Workflow security key"
                            readOnly
                            className="min-w-0 flex-1 rounded-md border border-amber-500/30 bg-[#101114] px-3 py-2 font-mono text-xs text-amber-50"
                            value={automationSigningSecret}
                          />
                          <button type="button" className={secondaryButtonClass} onClick={() => void copyAutomationSecret()}>
                            Copy security key
                          </button>
                          {automationConnectionReadyToTest ? (
                            <button
                              type="button"
                              className={primaryButtonClass}
                              disabled={busyAction === `automation-test-${automationConnectionReadyToTest}`}
                              onClick={() => void testAutomationConnection(automationConnectionReadyToTest)}
                            >
                              {busyAction === `automation-test-${automationConnectionReadyToTest}`
                                ? "Sending safe test..."
                                : "I saved it — send safe test"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ) : null}

                    {usageAllowance.external_automation.gateway_enabled && me?.org_role === "org_owner" ? (
                      <div className="mt-4 rounded-md border border-[#303137] bg-[#101114] p-4">
                        <p className="text-sm font-semibold text-white">Connect a workflow tool</p>
                        <div className="mt-3 grid gap-3 lg:grid-cols-3">
                          <div>
                            <label htmlFor="automation-provider" className="mb-1.5 block text-xs font-medium text-zinc-300">
                              Tool
                            </label>
                            <select
                              id="automation-provider"
                              className={selectClass}
                              value={automationProvider}
                              onChange={(event) => setAutomationProvider(event.target.value as "zapier" | "make" | "pipedream" | "n8n")}
                            >
                              {(automationProviders.length ? automationProviders : [
                                { code: "zapier" as const, label: "Zapier" },
                                { code: "make" as const, label: "Make" },
                                { code: "pipedream" as const, label: "Pipedream" },
                                { code: "n8n" as const, label: "n8n Cloud" },
                              ]).map((provider) => (
                                <option key={provider.code} value={provider.code}>{provider.label}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label htmlFor="automation-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
                              Name this connection
                            </label>
                            <input
                              id="automation-name"
                              className={selectClass}
                              value={automationName}
                              maxLength={120}
                              placeholder="Send new reports to my team"
                              onChange={(event) => setAutomationName(event.target.value)}
                            />
                          </div>
                          <div>
                            <label htmlFor="automation-destination" className="mb-1.5 block text-xs font-medium text-zinc-300">
                              Paste the receiving address from {selectedAutomationProviderSetup?.label || "your tool"}
                            </label>
                            <input
                              id="automation-destination"
                              type="password"
                              autoComplete="off"
                              className={selectClass}
                              value={automationDestination}
                              placeholder="Paste the complete HTTPS address"
                              onChange={(event) => setAutomationDestination(event.target.value)}
                            />
                            {automationProvider === "n8n" ? (
                              <p className="mt-1.5 text-xs leading-5 text-zinc-500">
                                In n8n, publish the workflow and copy the Webhook node&apos;s Production URL. The temporary Test URL will not work here.
                              </p>
                            ) : null}
                          </div>
                        </div>
                        {selectedAutomationProviderSetup ? (
                          <div className="mt-4 rounded-md border border-sky-500/20 bg-sky-500/5 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-xs font-semibold text-sky-100">
                                Set up {selectedAutomationProviderSetup.webhook_source}
                              </p>
                              <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">
                                Setup guide ready
                              </span>
                            </div>
                            <p className="mt-1 text-xs leading-5 text-sky-100/75">
                              {selectedAutomationProviderSetup.production_url_note}
                            </p>
                            <p className="mt-1 text-xs leading-5 text-zinc-400">
                              {selectedAutomationProviderSetup.account_note}
                            </p>
                            <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs leading-5 text-zinc-300">
                              {selectedAutomationProviderSetup.setup_steps.map((step) => (
                                <li key={step}>{step}</li>
                              ))}
                            </ol>
                            <div className="mt-3 grid gap-2 md:grid-cols-2">
                              <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                                <p className="text-xs font-semibold text-emerald-200">How to know the test arrived</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-300">
                                  {selectedAutomationProviderSetup.test_confirmation}
                                </p>
                              </div>
                              <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
                                <p className="text-xs font-semibold text-amber-200">If the test does not arrive</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-300">
                                  {selectedAutomationProviderSetup.recovery_note}
                                </p>
                              </div>
                            </div>
                            <a
                              className="mt-2 inline-flex text-xs font-medium text-sky-300 underline decoration-sky-300/40 underline-offset-4 hover:text-sky-200"
                              href={selectedAutomationProviderSetup.official_docs_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open the official {selectedAutomationProviderSetup.label} setup guide
                            </a>
                            <p className="mt-3 text-xs leading-5 text-zinc-400">
                              After you save, keep the one-time security key private and use the button beside it to send a safe test.
                            </p>
                            <details className="group mt-3 border-t border-sky-500/15 pt-3">
                              <summary className="cursor-pointer text-xs font-semibold text-zinc-300">
                                Technical verification details (advanced)
                              </summary>
                              <div className="mt-3 rounded-md border border-[#303137] bg-[#101114] p-3">
                                <div className="flex flex-wrap items-center gap-3">
                                  <button
                                    type="button"
                                    className={secondaryButtonClass}
                                    disabled={busyAction === `automation-conformance-${automationProvider}`}
                                    onClick={() => void downloadAutomationConformanceKit()}
                                  >
                                    {busyAction === `automation-conformance-${automationProvider}` ? "Preparing test..." : "Download developer test file"}
                                  </button>
                                  <span className="text-xs leading-5 text-zinc-500">
                                    Uses sample data only. It contains no customer information or live password.
                                  </span>
                                </div>
                                <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
                                  <div>
                                    <dt className="text-zinc-500">Payload path</dt>
                                    <dd className="mt-0.5 break-all font-mono text-[11px] text-zinc-300">{selectedAutomationProviderSetup.payload_path}</dd>
                                  </div>
                                  <div>
                                    <dt className="text-zinc-500">Header path</dt>
                                    <dd className="mt-0.5 break-all font-mono text-[11px] text-zinc-300">{selectedAutomationProviderSetup.headers_path}</dd>
                                  </div>
                                  <div>
                                    <dt className="text-zinc-500">Routing field</dt>
                                    <dd className="mt-0.5 break-all font-mono text-[11px] text-zinc-300">{selectedAutomationProviderSetup.route_field}</dd>
                                  </div>
                                </dl>
                                <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-zinc-300">
                                  {selectedAutomationProviderSetup.workflow_steps.map((step) => (
                                    <li key={step}>{step}</li>
                                  ))}
                                </ol>
                                <div className="mt-3 overflow-hidden rounded-md border border-[#303137] bg-[#141518]">
                                  {selectedAutomationProviderSetup.field_map.map((field) => (
                                    <div key={field.source} className="grid gap-1 border-b border-[#292a2f] px-3 py-2 last:border-b-0 sm:grid-cols-[9rem_1fr]">
                                      <code className="text-[11px] text-orange-200">{field.source}</code>
                                      <span className="text-xs leading-5 text-zinc-400">{field.purpose}</span>
                                    </div>
                                  ))}
                                </div>
                                <p className="mt-3 text-xs leading-5 text-zinc-500">
                                  Verification contract: {selectedAutomationProviderSetup.signature_contract.algorithm} over <code className="text-zinc-300">{selectedAutomationProviderSetup.signature_contract.signed_input}</code>. Compare the <code className="text-zinc-300">{selectedAutomationProviderSetup.signature_contract.signature_header}</code> value, reject timestamps older than {selectedAutomationProviderSetup.signature_contract.replay_window_seconds / 60} minutes, and deduplicate with <code className="text-zinc-300">{selectedAutomationProviderSetup.signature_contract.event_id_header}</code>.
                                </p>
                              </div>
                            </details>
                          </div>
                        ) : null}
                        {automationRecipes.length > 0 ? (
                          <div className="mt-4">
                            <p className="text-xs font-medium text-zinc-300">Start with a safe event recipe</p>
                            <p className="mt-1 text-xs leading-5 text-zinc-500">
                              A recipe only chooses signed outbound notifications. Finish the task or message steps inside your workflow tool; it cannot approve or run InsightOS work.
                            </p>
                            <div className="mt-2 grid gap-2 lg:grid-cols-3">
                              {automationRecipes.map((recipe) => (
                                <div key={recipe.code} className="rounded-md border border-[#292a2f] bg-[#141518] p-3">
                                  <p className="text-xs font-semibold text-zinc-200">{recipe.label}</p>
                                  <p className="mt-1 text-xs leading-5 text-zinc-500">{recipe.summary}</p>
                                  <p className="mt-2 text-xs leading-5 text-zinc-400">{recipe.external_result}</p>
                                  <button
                                    type="button"
                                    className={`${secondaryButtonClass} mt-3`}
                                    aria-pressed={automationSelectedRecipe === recipe.code}
                                    onClick={() => {
                                      const liveEvents = new Set(automationEvents.map((event) => event.code));
                                      setAutomationSelectedRecipe(recipe.code);
                                      setAutomationSelectedEvents(recipe.event_types.filter((code) => liveEvents.has(code)));
                                      setAutomationName((current) => current.trim() || recipe.label);
                                    }}
                                  >
                                    {automationSelectedRecipe === recipe.code ? "Recipe selected" : "Use this recipe"}
                                  </button>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <details className="group mt-4 rounded-md border border-[#292a2f] bg-[#141518]">
                          <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium text-zinc-300">
                            Choose individual updates instead (optional)
                          </summary>
                          <fieldset className="border-t border-[#292a2f] p-3">
                            <legend className="sr-only">Choose individual updates this workflow can receive</legend>
                            <p className="mb-2 text-xs leading-5 text-zinc-500">
                              Use this only if none of the simple recipes above matches what you need.
                            </p>
                            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                              {automationEvents.map((event) => (
                                <label key={event.code} className="flex items-start gap-2 rounded-md border border-[#292a2f] px-3 py-2 text-xs text-zinc-300">
                                  <input
                                    type="checkbox"
                                    className="mt-0.5 h-4 w-4 accent-orange-500"
                                    checked={automationSelectedEvents.includes(event.code)}
                                    onChange={(inputEvent) => {
                                      setAutomationSelectedRecipe("");
                                      setAutomationSelectedEvents((current) =>
                                        inputEvent.target.checked
                                          ? Array.from(new Set([...current, event.code]))
                                          : current.filter((code) => code !== event.code),
                                      );
                                    }}
                                  />
                                  <span>{event.label}</span>
                                </label>
                              ))}
                            </div>
                          </fieldset>
                        </details>
                        <button
                          type="button"
                          className={`${primaryButtonClass} mt-4`}
                          disabled={
                            busyAction === "automation-create" ||
                            automationName.trim().length < 2 ||
                            !automationDestination.trim() ||
                            automationSelectedEvents.length === 0
                          }
                          onClick={() => void createAutomationConnection()}
                        >
                          {busyAction === "automation-create" ? "Saving securely..." : "Save connection"}
                        </button>
                      </div>
                    ) : usageAllowance.external_automation.gateway_enabled ? (
                      <p className="mt-4 rounded-md border border-[#303137] bg-[#101114] p-3 text-xs leading-5 text-zinc-400">
                        Ask the workspace owner to add, test, rotate, or disconnect workflow endpoints.
                      </p>
                    ) : null}

                    {automationMonthlyUsage && usageAllowance.external_automation.gateway_enabled ? (
                      <details className="group mt-4 rounded-md border border-[#303137] bg-[#101114]">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-4">
                          <span>
                            <span className="block text-xs font-semibold text-zinc-200">Workflow activity this month</span>
                            <span className="mt-1 block text-xs text-zinc-500">
                              {automationMonthlyUsage.accepted} accepted · {automationMonthlyUsage.waiting_or_retrying + automationMonthlyUsage.needs_recovery} need attention
                            </span>
                          </span>
                          <span className="text-xs font-semibold text-zinc-400 group-open:hidden">View</span>
                          <span className="hidden text-xs font-semibold text-zinc-400 group-open:inline">Close</span>
                        </summary>
                        <div className="border-t border-[#292a2f] p-4">
                          <p className="text-xs leading-5 text-zinc-500">
                            Since {formatTimestamp(automationMonthlyUsage.period_start)}. Each update is counted once; retries are shown separately.
                          </p>
                          <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                          {[
                            ["Product updates", automationMonthlyUsage.product_events],
                            ["Connection tests", automationMonthlyUsage.test_events],
                            ["Accepted", automationMonthlyUsage.accepted],
                            ["Needs attention", automationMonthlyUsage.waiting_or_retrying + automationMonthlyUsage.needs_recovery],
                          ].map(([label, value]) => (
                            <div key={String(label)} className="rounded-md border border-[#292a2f] bg-[#141518] px-3 py-2">
                              <dt className="text-xs text-zinc-500">{label}</dt>
                              <dd className="mt-1 text-lg font-semibold text-zinc-100">{value}</dd>
                            </div>
                          ))}
                          </dl>
                          <p className="mt-3 text-xs leading-5 text-zinc-500">
                            {automationMonthlyUsage.attempts} total delivery {automationMonthlyUsage.attempts === 1 ? "attempt" : "attempts"}. This is activity history, not an extra charge.
                          </p>
                        </div>
                      </details>
                    ) : null}

                    {automationConnections.length > 0 ? (
                      <div className="mt-4 space-y-3">
                        {automationConnections.map((connection) => {
                          const delivery = connection.last_delivery;
                          const destinationSaved = connection.destination_url_saved;
                          const signedTestAccepted = connection.verification_status === "verified";
                          const realUpdateAccepted = connection.conformance_proof.production_proven;
                          const connectionStatusLabel =
                            connection.status === "disconnected"
                              ? "Disconnected"
                              : connection.status === "paused"
                                ? "Updates paused"
                                : connection.status === "unhealthy"
                                  ? "Needs attention"
                                  : realUpdateAccepted
                                    ? "Connected and proven with a real update"
                                    : signedTestAccepted
                                      ? "Test received — ready for automatic updates"
                                      : "Not connected yet — send a test";
                          const setupProgress = [
                            {
                              label: "Receiving address saved",
                              complete: destinationSaved,
                              needsAttention: false,
                              detail: destinationSaved
                                ? "The private destination is stored securely."
                                : "Paste and save the production webhook URL from your workflow tool.",
                            },
                            {
                              label: "Signed test received",
                              complete: signedTestAccepted,
                              needsAttention: connection.verification_status === "failed",
                              detail: signedTestAccepted
                                ? `Accepted${connection.last_tested_at ? ` ${formatTimestamp(connection.last_tested_at)}` : ""}.`
                                : connection.verification_status === "failed"
                                  ? "The last test was not accepted. Use Retry last test after checking the workflow."
                                  : "Send one safe test and confirm it appears in your workflow tool.",
                            },
                            {
                              label: "First real update received",
                              complete: realUpdateAccepted,
                              needsAttention: false,
                              detail: realUpdateAccepted
                                ? "A real InsightOS update was accepted after the current test."
                                : "This completes automatically after the first selected InsightOS update is accepted.",
                            },
                          ];
                          return (
                            <div id={`automation-connection-${connection.id}`} key={connection.id} className="scroll-mt-24 rounded-md border border-[#303137] bg-[#101114] p-4">
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                <div>
                                  <p className="font-medium text-white">{connection.name}</p>
                                  <p className="mt-1 text-xs text-zinc-400">
                                    {connection.provider_label} · {connectionStatusLabel}
                                  </p>
                                  <ol
                                    className="mt-3 grid gap-2 md:grid-cols-3"
                                    aria-label={`${connection.provider_label} connection progress`}
                                  >
                                    {setupProgress.map((step) => (
                                      <li
                                        key={step.label}
                                        className={`rounded-md border p-3 ${step.complete ? "border-emerald-500/20 bg-emerald-500/5" : step.needsAttention ? "border-rose-500/20 bg-rose-500/5" : "border-[#303137] bg-[#141518]"}`}
                                      >
                                        <p className="text-xs font-semibold text-zinc-100">{step.label}</p>
                                        <p className={`mt-1 text-[11px] font-semibold ${step.complete ? "text-emerald-300" : step.needsAttention ? "text-rose-300" : "text-amber-300"}`}>
                                          {step.complete ? "Complete" : step.needsAttention ? "Needs attention" : "Waiting"}
                                        </p>
                                        <p className="mt-1 text-[11px] leading-4 text-zinc-500">{step.detail}</p>
                                      </li>
                                    ))}
                                  </ol>
                                  <div className={`mt-2 rounded-md border px-3 py-2 ${connection.conformance_proof.state === "product_event_accepted" ? "border-emerald-500/20 bg-emerald-500/5" : connection.conformance_proof.state === "needs_attention" ? "border-rose-500/20 bg-rose-500/5" : "border-amber-500/20 bg-amber-500/5"}`}>
                                    <p className="text-xs font-medium text-zinc-200">
                                      Connection check: {connection.conformance_proof.label}
                                    </p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-500">
                                      {connection.conformance_proof.summary}
                                      {connection.conformance_proof.evidence_at ? ` Last evidence: ${formatTimestamp(connection.conformance_proof.evidence_at)}.` : ""}
                                    </p>
                                  </div>
                                  <details className="group mt-2 rounded-md border border-[#292a2f] bg-[#141518]">
                                    <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-zinc-400">
                                      Connection details (advanced)
                                    </summary>
                                    <div className="space-y-1 border-t border-[#292a2f] px-3 py-2 text-xs leading-5 text-zinc-500">
                                      <p>Receiving address: {connection.endpoint_host}</p>
                                      <p>{connection.event_types.length} selected {connection.event_types.length === 1 ? "update" : "updates"}. The full destination URL stays private.</p>
                                      <p>Signing-secret version {connection.signing_secret_version}.</p>
                                      <p>
                                        This month: {connection.monthly_delivery_usage.product_events} live updates, {connection.monthly_delivery_usage.test_events} tests, and {connection.monthly_delivery_usage.attempts} delivery attempts.
                                      </p>
                                    </div>
                                  </details>
                                  {connection.dead_letter_count > 0 ? (
                                    <div className="mt-2 space-y-2 rounded-md border border-rose-500/20 bg-rose-500/5 p-3">
                                      <p className="text-xs font-medium text-rose-300">
                                        {connection.dead_letter_count} event {connection.dead_letter_count === 1 ? "needs" : "need"} owner recovery.
                                      </p>
                                      {(connection.recoverable_deliveries || []).map((item) => (
                                        <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                                          <span>{item.event_type} · {item.attempt_count} attempts exhausted</span>
                                          {me?.org_role === "org_owner" ? (
                                            <button
                                              type="button"
                                              className={secondaryButtonClass}
                                              disabled={busyAction === `automation-recover-${item.id}`}
                                              onClick={() => void recoverAutomationDelivery(item.id)}
                                            >
                                              {busyAction === `automation-recover-${item.id}` ? "Queuing..." : "Recover event"}
                                            </button>
                                          ) : null}
                                        </div>
                                      ))}
                                    </div>
                                  ) : null}
                                  {delivery ? (
                                    <div className="mt-2">
                                      <p className={`text-xs ${delivery.status === "delivered" ? "text-emerald-300" : delivery.status === "failed" || delivery.status === "dead_letter" ? "text-rose-300" : "text-amber-300"}`}>
                                        Last {delivery.delivery_kind === "test" ? "test" : "product event"}: {delivery.status === "delivered" ? "Accepted" : delivery.status === "failed" ? "Retry scheduled" : delivery.status === "dead_letter" ? "Attempts exhausted" : delivery.status === "cancelled" ? "Stopped before delivery" : "Queued"} · {delivery.attempt_count} of {delivery.max_attempts} attempts
                                      </p>
                                      {delivery.next_attempt_at && delivery.status === "failed" ? (
                                        <p className="mt-1 text-xs text-zinc-500">Next bounded retry: {formatTimestamp(delivery.next_attempt_at)}</p>
                                      ) : null}
                                    </div>
                                  ) : (
                                    <p className="mt-2 text-xs text-amber-300">No test event sent yet.</p>
                                  )}
                                </div>
                                {me?.org_role === "org_owner" && connection.status !== "disconnected" ? (
                                  <div className="flex flex-wrap gap-2">
                                    {connection.status !== "paused" ? (
                                      <button
                                        type="button"
                                        className={secondaryButtonClass}
                                        disabled={busyAction === `automation-test-${connection.id}`}
                                        onClick={() => void testAutomationConnection(connection.id)}
                                      >
                                        {busyAction === `automation-test-${connection.id}` ? "Sending..." : "Send test"}
                                      </button>
                                    ) : null}
                                    {delivery?.can_retry ? (
                                      <button
                                        type="button"
                                        className={secondaryButtonClass}
                                        disabled={busyAction === `automation-retry-${delivery.id}`}
                                        onClick={() => void retryAutomationDelivery(delivery.id)}
                                      >
                                        {busyAction === `automation-retry-${delivery.id}` ? "Retrying..." : "Retry last test"}
                                      </button>
                                    ) : null}
                                    <details className="group relative">
                                      <summary className={`${secondaryButtonClass} cursor-pointer list-none`}>More options</summary>
                                      <div className="mt-2 flex flex-col gap-2 rounded-md border border-[#303137] bg-[#141518] p-2 sm:min-w-44">
                                        <button
                                          type="button"
                                          className={secondaryButtonClass}
                                          disabled={busyAction === `automation-${connection.status === "paused" ? "resume" : "pause"}-${connection.id}`}
                                          onClick={() => void setAutomationConnectionPaused(connection.id, connection.status !== "paused")}
                                        >
                                          {connection.status === "paused" ? "Resume updates" : "Pause updates"}
                                        </button>
                                        <button
                                          type="button"
                                          className={secondaryButtonClass}
                                          disabled={busyAction === `automation-rotate-${connection.id}`}
                                          onClick={() => void rotateAutomationSecret(connection.id)}
                                        >
                                          Replace signing secret
                                        </button>
                                        <button
                                          type="button"
                                          className="inline-flex items-center justify-center rounded-md border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-sm font-medium text-rose-100 disabled:opacity-50"
                                          disabled={busyAction === `automation-disconnect-${connection.id}`}
                                          onClick={() => void disconnectAutomationConnection(connection.id)}
                                        >
                                          Disconnect
                                        </button>
                                      </div>
                                    </details>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : usageAllowance.external_automation.gateway_enabled ? (
                      <p className="mt-4 text-xs leading-5 text-zinc-500">No workflow tools connected yet.</p>
                    ) : null}
                    <p className="mt-3 text-xs leading-5 text-zinc-500">
                      A saved address alone is not connected. InsightOS shows a connection as ready only after the workflow tool accepts a signed test, and shows production proof only after it accepts a real selected update.
                    </p>
                    </div>
                    ) : null}

                    {usageAllowance.external_automation.gateway_enabled && automationWorkflowDirection === "incoming" ? (
                      <div id="workflow-requests" className="mt-5 scroll-mt-24 rounded-md border border-sky-500/20 bg-sky-500/5 p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-sky-200/70">
                          Let a workflow request saved work
                        </p>
                        <h4 className="mt-1 text-sm font-semibold text-white">
                          {activeAutomationServiceAccount?.allowed_commands.includes("report.generate_saved")
                            ? "Let a workflow tool retrieve and create private reports"
                            : "Give a workflow tool read-only access to saved reports"}
                        </h4>
                        <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-300">
                          Create one short-lived workflow key for Zapier, Make, n8n, Pipedream, or another HTTPS tool. It can retrieve a report InsightOS already generated; it cannot start paid checks, approve work, publish content, or change your website or business profile.
                        </p>

                        {automationConnectorCatalog ? (
                          <div className="mt-4 rounded-md border border-[#303137] bg-[#101114] p-4">
                            <p className="text-sm font-semibold text-white">Choose your workflow tool</p>
                            <p className="mt-1 text-xs leading-5 text-zinc-400">
                              {automationConnectorCatalog.truth.summary}
                            </p>
                            <label htmlFor="automation-command-provider" className="mt-3 block text-xs font-medium text-zinc-300">
                              Workflow tool
                            </label>
                            <select
                              id="automation-command-provider"
                              className={`${selectClass} mt-1.5 max-w-sm`}
                              value={automationCommandProvider}
                              onChange={(event) => setAutomationCommandProvider(
                                event.target.value as AutomationConnectorCatalog["items"][number]["code"],
                              )}
                            >
                              {automationConnectorCatalog.items.map((connector) => (
                                <option key={connector.code} value={connector.code}>{connector.name}</option>
                              ))}
                            </select>
                            {selectedAutomationCommandConnector ? (
                              <div className="mt-3 rounded-md border border-[#292a2f] bg-[#141518] p-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <div>
                                    <p className="text-sm font-semibold text-zinc-100">
                                      Set up {selectedAutomationCommandConnector.name}
                                    </p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-400">
                                      {selectedAutomationCommandConnector.setup}
                                    </p>
                                  </div>
                                  <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-100">
                                    Setup guide available
                                  </span>
                                </div>
                                <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs leading-5 text-zinc-300">
                                  {selectedAutomationCommandConnector.setup_steps.map((step) => <li key={step}>{step}</li>)}
                                </ol>
                                {activeAutomationServiceAccount ? (
                                  <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                                    <p className="text-xs font-semibold text-emerald-100">Your next step</p>
                                    <p className="mt-1 text-xs leading-5 text-zinc-300">
                                      {selectedAutomationCommandConnector.code === "n8n"
                                        ? "Download the inactive starter, add the private workflow key, run it once, and confirm InsightOS shows a contact time."
                                        : "Download the connection guide, add the private workflow key in this tool, run one request, and confirm InsightOS shows a contact time."}
                                    </p>
                                    <div className="mt-3 flex flex-wrap gap-2">
                                      <button
                                        type="button"
                                        className={primaryButtonClass}
                                        disabled={busyAction === (
                                          selectedAutomationCommandConnector.code === "n8n"
                                            ? `automation-command-template-${activeAutomationServiceAccount.id}`
                                            : `automation-command-guide-${activeAutomationServiceAccount.id}`
                                        )}
                                        onClick={() => void (
                                          selectedAutomationCommandConnector.code === "n8n"
                                            ? downloadN8nReportWorkflow(activeAutomationServiceAccount.id)
                                            : downloadAutomationConnectionGuide(activeAutomationServiceAccount.id)
                                        )}
                                      >
                                        {selectedAutomationCommandConnector.code === "n8n"
                                          ? "Download n8n starter"
                                          : `Download ${selectedAutomationCommandConnector.name} guide`}
                                      </button>
                                      {isAutomationConformanceProvider(selectedAutomationCommandConnector.code) ? (
                                        <button
                                          type="button"
                                          className={secondaryButtonClass}
                                          disabled={busyAction === `automation-conformance-${selectedAutomationCommandConnector.code}`}
                                          onClick={() => void downloadAutomationConformanceKit(selectedAutomationCommandConnector.code)}
                                        >
                                          {busyAction === `automation-conformance-${selectedAutomationCommandConnector.code}`
                                            ? "Preparing sample..."
                                            : "Download sample request"}
                                        </button>
                                      ) : null}
                                    </div>
                                    <p className="mt-2 text-[11px] leading-4 text-zinc-500">
                                      The sample checks field mapping only. The connection is proven only after this tool contacts InsightOS and a first allowed request is saved.
                                    </p>
                                  </div>
                                ) : (
                                  <p className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-5 text-amber-100">
                                    First create report access below. InsightOS will then show the private key and the next setup action for {selectedAutomationCommandConnector.name}.
                                  </p>
                                )}
                              </div>
                            ) : null}
                          </div>
                        ) : null}

                        {automationCommandLoadState === "unavailable" ? (
                          <p className="mt-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-5 text-amber-100">
                            Report access could not be checked. Existing InsightOS work is still available, and no new workflow key was created.
                          </p>
                        ) : null}

                        {automationCommandToken ? (
                          <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/10 p-4">
                            <p className="text-sm font-semibold text-amber-100">Copy this workflow key now</p>
                            <p className="mt-1 text-xs leading-5 text-amber-100/80">
                              Save it in your workflow tool as a private Bearer credential. InsightOS stores only a protected fingerprint and will not show the key again.
                            </p>
                            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                              <input
                                aria-label="workflow tool key"
                                readOnly
                                className="min-w-0 flex-1 rounded-md border border-amber-500/30 bg-[#101114] px-3 py-2 font-mono text-xs text-amber-50"
                                value={automationCommandToken}
                              />
                              <button type="button" className={secondaryButtonClass} onClick={() => void copyAutomationCommandToken()}>
                                Copy key
                              </button>
                            </div>
                          </div>
                        ) : null}

                        {activeAutomationServiceAccount ? (
                          <div className="mt-4 rounded-md border border-[#303137] bg-[#101114] p-4">
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                              <div>
                                <p className="text-sm font-semibold text-white">{activeAutomationServiceAccount.name}</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-400">
                                  {activeAutomationServiceAccount.location_name} · {activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved")
                                    ? "Retrieve and create private reports"
                                    : "Saved reports only"} · Key ends in {activeAutomationServiceAccount.token_hint}
                                </p>
                                <p className="mt-1 text-xs leading-5 text-zinc-500">
                                  Expires {formatTimestamp(activeAutomationServiceAccount.expires_at)}
                                  {activeAutomationServiceAccount.last_used_at
                                    ? ` · Last used ${formatTimestamp(activeAutomationServiceAccount.last_used_at)}`
                                    : " · Not used yet"}
                                </p>
                              </div>
                              {me?.org_role === "org_owner" ? (
                                <details className="group relative">
                                  <summary className={`${secondaryButtonClass} cursor-pointer list-none`}>Manage connection</summary>
                                  <div className="mt-2 flex flex-col gap-2 rounded-md border border-[#303137] bg-[#141518] p-2 sm:min-w-52">
                                    <button
                                      type="button"
                                      className={secondaryButtonClass}
                                      disabled={busyAction === `automation-command-template-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void downloadN8nReportWorkflow(activeAutomationServiceAccount.id)}
                                    >
                                      {busyAction === `automation-command-template-${activeAutomationServiceAccount.id}` ? "Downloading..." : "Download n8n starter"}
                                    </button>
                                    <button
                                      type="button"
                                      className={secondaryButtonClass}
                                      disabled={busyAction === `automation-command-guide-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void downloadAutomationConnectionGuide(activeAutomationServiceAccount.id)}
                                    >
                                      {busyAction === `automation-command-guide-${activeAutomationServiceAccount.id}` ? "Preparing..." : "Download connection guide"}
                                    </button>
                                    <button
                                      type="button"
                                      className={secondaryButtonClass}
                                      disabled={busyAction === `automation-command-openapi-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void downloadAutomationOpenApi(activeAutomationServiceAccount.id)}
                                    >
                                      {busyAction === `automation-command-openapi-${activeAutomationServiceAccount.id}` ? "Preparing..." : "Download API file"}
                                    </button>
                                    <button
                                      type="button"
                                      className={secondaryButtonClass}
                                      disabled={busyAction === `automation-command-rotate-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void rotateAutomationCommandAccess(activeAutomationServiceAccount.id)}
                                    >
                                      {busyAction === `automation-command-rotate-${activeAutomationServiceAccount.id}` ? "Replacing..." : "Replace key"}
                                    </button>
                                    <button
                                      type="button"
                                      className="inline-flex items-center justify-center rounded-md border border-rose-500/30 bg-rose-500/10 px-3.5 py-2 text-sm font-medium text-rose-100 disabled:opacity-50"
                                      disabled={busyAction === `automation-command-revoke-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void revokeAutomationCommandAccess(activeAutomationServiceAccount.id)}
                                    >
                                      {busyAction === `automation-command-revoke-${activeAutomationServiceAccount.id}` ? "Turning off..." : "Turn off access"}
                                    </button>
                                  </div>
                                </details>
                              ) : null}
                            </div>
                            <div className="mt-4 rounded-md border border-[#292a2f] bg-[#141518] p-3">
                              <p className="text-xs font-semibold text-zinc-200">Workflow setup progress</p>
                              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                                {[
                                  {
                                    label: "Private key ready",
                                    complete: true,
                                    detail: "Created in InsightOS",
                                  },
                                  {
                                    label: "InsightOS contacted",
                                    complete: Boolean(activeAutomationServiceAccount.last_used_at),
                                    detail: activeAutomationServiceAccount.last_used_at
                                      ? `Last contact ${formatTimestamp(activeAutomationServiceAccount.last_used_at)}`
                                      : "Run the safe connection check",
                                  },
                                  {
                                    label: "First request saved",
                                    complete: activeAutomationServiceAccount.command_count > 0,
                                    detail: activeAutomationServiceAccount.command_count > 0
                                      ? `${activeAutomationServiceAccount.command_count} saved request${activeAutomationServiceAccount.command_count === 1 ? "" : "s"}`
                                      : "Test one allowed action",
                                  },
                                ].map((step) => (
                                  <div key={step.label} className="rounded-md border border-[#303137] bg-[#101114] p-2.5">
                                    <p className={`text-xs font-medium ${step.complete ? "text-emerald-100" : "text-zinc-300"}`}>
                                      {step.complete ? "Complete" : "Next"} · {step.label}
                                    </p>
                                    <p className="mt-1 text-[11px] leading-4 text-zinc-500">{step.detail}</p>
                                  </div>
                                ))}
                              </div>
                              <p className="mt-2 text-[11px] leading-4 text-zinc-500">
                                These milestones confirm only what InsightOS has received. Turn on the external workflow yourself after its saved result looks correct.
                              </p>
                            </div>
                            {me?.org_role === "org_owner" && automationCommandLocations.length > 1 ? (
                              <details className="mt-4 rounded-md border border-[#303137] bg-[#141518] p-3">
                                <summary className="cursor-pointer text-sm font-semibold text-white">
                                  Saved-report locations ({activeAutomationServiceAccount.location_count})
                                </summary>
                                <p className="mt-2 text-xs leading-5 text-zinc-400">
                                  The primary location is always included. Check only the other locations whose saved reports this key should read.
                                </p>
                                <div className="mt-3 space-y-2">
                                  {automationCommandLocations.map((location) => {
                                    const isPrimary = location.id === activeAutomationServiceAccount.location_id;
                                    const isChecked = activeAutomationServiceAccount.location_ids.includes(location.id);
                                    return (
                                      <label key={location.id} className="flex items-start gap-2 text-xs text-zinc-300">
                                        <input
                                          type="checkbox"
                                          className="mt-0.5"
                                          checked={isChecked}
                                          disabled={isPrimary || busyAction === `automation-command-location-scope-${activeAutomationServiceAccount.id}`}
                                          onChange={(event) => {
                                            const next = event.target.checked
                                              ? [...activeAutomationServiceAccount.location_ids, location.id]
                                              : activeAutomationServiceAccount.location_ids.filter((item) => item !== location.id);
                                            void updateAutomationCommandLocations(activeAutomationServiceAccount, next);
                                          }}
                                        />
                                        <span>{location.label}{isPrimary ? " · Primary" : ""}</span>
                                      </label>
                                    );
                                  })}
                                </div>
                                <p className="mt-3 text-xs leading-5 text-amber-100/80">
                                  Every change replaces the workflow key. Removing a location blocks future reads immediately but preserves its reports and prior request history.
                                </p>
                              </details>
                            ) : null}
                            {me?.org_role === "org_owner" ? (
                              <details className="group mt-4 rounded-md border border-[#303137] bg-[#141518]">
                                <summary className="cursor-pointer list-none p-4">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div>
                                      <p className="text-sm font-semibold text-white">Add more things this workflow may do</p>
                                      <p className="mt-1 text-xs leading-5 text-zinc-400">
                                        Keep the basic saved-report connection, or deliberately add reports, recommendations, refreshes, listing checks, drafts, or review routing.
                                      </p>
                                    </div>
                                    <span className="rounded-full border border-[#3a3b41] bg-[#101114] px-2.5 py-1 text-xs font-semibold text-zinc-300">
                                      {automationExtraAbilityCount === 0
                                        ? "No extras enabled"
                                        : `${automationExtraAbilityCount} ${automationExtraAbilityCount === 1 ? "extra" : "extras"} enabled`}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-xs font-semibold text-sky-300 group-open:hidden">Review optional abilities</p>
                                  <p className="mt-2 hidden text-xs font-semibold text-zinc-400 group-open:block">Close optional abilities</p>
                                </summary>
                                <div className="border-t border-[#292a2f] p-4">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                  <div>
                                    <p className="text-sm font-semibold text-white">
                                      Let a workflow tool create private reports from saved results
                                    </p>
                                    <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                      This can assemble a new report using data already inside InsightOS. It cannot start a crawl or paid check, send the report, publish content, or change your website or business profile.
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    className={activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved") ? secondaryButtonClass : primaryButtonClass}
                                    disabled={busyAction === `automation-command-scope-${activeAutomationServiceAccount.id}`}
                                    onClick={() => void setAutomationReportCreation(
                                      activeAutomationServiceAccount.id,
                                      !activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved"),
                                    )}
                                  >
                                    {busyAction === `automation-command-scope-${activeAutomationServiceAccount.id}`
                                      ? "Updating..."
                                      : activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved")
                                        ? "Turn off report creation"
                                        : "Allow private report creation"}
                                  </button>
                                </div>
                                <p className="mt-2 text-xs leading-5 text-amber-100/80">
                                  Changing this access replaces the workflow key, so the old key stops working immediately.
                                </p>
                                {activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved") && activeAutomationCampaign ? (
                                  <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                                    <p className="text-xs leading-5 text-emerald-50">
                                      Download an inactive n8n workflow that creates this location&apos;s private report on the first day of each month. You can review its day, time, and timezone before publishing.
                                    </p>
                                    <button
                                      type="button"
                                      className={`${secondaryButtonClass} mt-3`}
                                      disabled={busyAction === `automation-command-monthly-template-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void downloadN8nMonthlyReportWorkflow(
                                        activeAutomationServiceAccount.id,
                                        activeAutomationCampaign.id,
                                      )}
                                    >
                                      {busyAction === `automation-command-monthly-template-${activeAutomationServiceAccount.id}`
                                        ? "Downloading..."
                                        : "Download monthly report workflow"}
                                    </button>
                                  </div>
                                ) : null}
                                <div className="mt-4 border-t border-[#292a2f] pt-4">
                                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Let a workflow tool route saved recommendations for owner review
                                      </p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        When InsightOS finds a recommendation, your workflow can retrieve its plain-language facts and place it in the InsightOS owner-review queue before continuing to email, CRM, or a task tool. It cannot approve, schedule, execute, or publish anything.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("recommendation.retrieve") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-recommendation-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationRecommendationAccess(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("recommendation.retrieve"),
                                      )}
                                    >
                                      {busyAction === `automation-command-recommendation-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("recommendation.retrieve")
                                          ? "Turn off recommendation access"
                                          : "Allow owner-review routing"}
                                    </button>
                                  </div>
                                  {activeAutomationServiceAccount.allowed_commands.includes("recommendation.retrieve") ? (
                                    <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                                      <p className="text-xs leading-5 text-emerald-50">
                                        Download an inactive n8n workflow that listens only for this location&apos;s Recommendation ready updates and retrieves the matching saved recommendation.
                                      </p>
                                      <button
                                        type="button"
                                        className={`${secondaryButtonClass} mt-3`}
                                        disabled={busyAction === `automation-command-recommendation-template-${activeAutomationServiceAccount.id}`}
                                        onClick={() => void downloadN8nRecommendationWorkflow(activeAutomationServiceAccount.id)}
                                      >
                                        {busyAction === `automation-command-recommendation-template-${activeAutomationServiceAccount.id}`
                                          ? "Downloading..."
                                          : "Download recommendation workflow"}
                                      </button>
                                    </div>
                                  ) : null}
                                </div>
                                <div className="mt-4 border-t border-[#292a2f] pt-4">
                                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Let a workflow tool refresh connected data
                                      </p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        Your workflow can request a fresh check from a Google source you already connected to this location. InsightOS keeps the request in its own job history and applies the same access and location checks as this screen. It cannot connect a new account, change settings, publish, or run an unrelated action.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("connection.refresh_saved") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-refresh-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationConnectionRefresh(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("connection.refresh_saved"),
                                      )}
                                    >
                                      {busyAction === `automation-command-refresh-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("connection.refresh_saved")
                                          ? "Turn off data refresh"
                                          : "Allow connected-data refresh"}
                                    </button>
                                  </div>
                                  {activeAutomationServiceAccount.allowed_commands.includes("connection.refresh_saved") ? (
                                    <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs leading-5 text-emerald-50">
                                      Use command <code>connection.refresh_saved</code> with the exact connected-source ID. The receipt returns a safe job ID and current queued, running, completed, or failed status for polling.
                                    </div>
                                  ) : null}
                                </div>
                                <div className="mt-4 border-t border-[#292a2f] pt-4">
                                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Let a workflow tool check public business listings
                                      </p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        This starts one inventory check across supported public listing sources for this location. Each accepted check uses the same Insight Credit balance, daily plan limit, price setup, and connection safeguards as the Listings screen. It cannot correct a listing, publish, or change your Business Profile.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("listing.check_public") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-listing-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationPublicListingCheck(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("listing.check_public"),
                                      )}
                                    >
                                      {busyAction === `automation-command-listing-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("listing.check_public")
                                          ? "Turn off listing checks"
                                          : "Allow public listing checks"}
                                    </button>
                                  </div>
                                  <p className="mt-2 text-xs leading-5 text-amber-100/80">
                                    This is the first workflow action that can consume Insight Credits. InsightOS safely declines it before any outside call when the allowance, daily limit, location, provider health, or price setup is unavailable.
                                  </p>
                                </div>
                                <div className="mt-4 border-t border-[#292a2f] pt-4">
                                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Let a workflow tool start accepted working drafts and request review
                                      </p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        After an owner accepts a saved content brief, your workflow can create its private editable outline and place an exact draft beside the owner for review. It cannot generate AI copy, approve, schedule, publish, or change your website.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("content.create_working_draft") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-draft-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationWorkingDraftCreation(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("content.create_working_draft"),
                                      )}
                                    >
                                      {busyAction === `automation-command-draft-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("content.create_working_draft")
                                          ? "Turn off draft creation"
                                          : "Allow accepted draft creation"}
                                    </button>
                                  </div>
                                  {activeAutomationServiceAccount.allowed_commands.includes("content.create_working_draft")
                                    && activeAutomationServiceAccount.allowed_commands.includes("content.request_draft_review")
                                    && activeAutomationCampaign ? (
                                    <button
                                      type="button"
                                      className={`${secondaryButtonClass} mt-3`}
                                      disabled={busyAction === `automation-command-content-template-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void downloadN8nContentDraftWorkflow(
                                        activeAutomationServiceAccount.id,
                                        activeAutomationCampaign.id,
                                      )}
                                    >
                                      {busyAction === `automation-command-content-template-${activeAutomationServiceAccount.id}`
                                        ? "Preparing download..."
                                        : "Download private-draft workflow"}
                                    </button>
                                  ) : null}
                                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                                    The download starts inactive, contains no workflow key, and requires you to replace the accepted brief ID before testing.
                                  </p>
                                </div>
                                <div className="mt-4 border-t border-[#292a2f] pt-4">
                                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Let a workflow tool route saved review facts
                                      </p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        Your workflow can read the rating, review date, reply state, and whether a comment exists for one exact saved review. Reviewer names and comment text stay in InsightOS. It cannot create, approve, or post a reply or change your Business Profile.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("review.retrieve") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-review-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationReviewRetrieval(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("review.retrieve"),
                                      )}
                                    >
                                      {busyAction === `automation-command-review-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("review.retrieve")
                                          ? "Turn off review routing"
                                          : "Allow saved-review routing"}
                                    </button>
                                  </div>
                                  {activeAutomationServiceAccount.allowed_commands.includes("review.retrieve") ? (
                                    <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs leading-5 text-emerald-50">
                                      <p>Use <code>review.retrieve</code> with the exact saved review ID. InsightOS returns only routing facts and never sends the reviewer&apos;s identity or comment text.</p>
                                      <button
                                        type="button"
                                        className={`${secondaryButtonClass} mt-3`}
                                        disabled={busyAction === `automation-command-review-template-${activeAutomationServiceAccount.id}`}
                                        onClick={() => void downloadN8nSavedReviewWorkflow(activeAutomationServiceAccount.id)}
                                      >
                                        {busyAction === `automation-command-review-template-${activeAutomationServiceAccount.id}`
                                          ? "Preparing download..."
                                          : "Download saved-review workflow"}
                                      </button>
                                    </div>
                                  ) : null}
                                  <div className="mt-3 flex flex-col gap-3 rounded-md border border-[#303137] bg-[#141518] p-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div>
                                      <p className="text-xs font-semibold text-white">Optionally prepare a private reply draft</p>
                                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-400">
                                        Your workflow may request one governed draft for the exact saved review. The draft text stays in InsightOS. A person must still review and approve it, and the workflow cannot post it or change the Business Profile.
                                      </p>
                                    </div>
                                    <button
                                      type="button"
                                      className={activeAutomationServiceAccount.allowed_commands.includes("review.create_response_draft") ? secondaryButtonClass : primaryButtonClass}
                                      disabled={busyAction === `automation-command-review-draft-scope-${activeAutomationServiceAccount.id}`}
                                      onClick={() => void setAutomationReviewDraftCreation(
                                        activeAutomationServiceAccount.id,
                                        !activeAutomationServiceAccount.allowed_commands.includes("review.create_response_draft"),
                                      )}
                                    >
                                      {busyAction === `automation-command-review-draft-scope-${activeAutomationServiceAccount.id}`
                                        ? "Updating..."
                                        : activeAutomationServiceAccount.allowed_commands.includes("review.create_response_draft")
                                          ? "Turn off reply drafting"
                                          : "Allow private reply drafts"}
                                    </button>
                                    {activeAutomationServiceAccount.allowed_commands.includes("review.create_response_draft") ? (
                                      <button
                                        type="button"
                                        className={secondaryButtonClass}
                                        disabled={busyAction === `automation-command-review-draft-template-${activeAutomationServiceAccount.id}`}
                                        onClick={() => void downloadN8nReviewDraftWorkflow(activeAutomationServiceAccount.id)}
                                      >
                                        {busyAction === `automation-command-review-draft-template-${activeAutomationServiceAccount.id}`
                                          ? "Preparing download..."
                                          : "Download private reply-draft workflow"}
                                      </button>
                                    ) : null}
                                  </div>
                                </div>
                                </div>
                              </details>
                            ) : null}
                          </div>
                        ) : me?.org_role === "org_owner" && automationCommandLoadState === "ready" ? (
                          <div className="mt-4 grid gap-3 rounded-md border border-[#303137] bg-[#101114] p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
                            <div>
                              <label htmlFor="automation-command-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
                                Name this report access
                              </label>
                              <input
                                id="automation-command-name"
                                className={selectClass}
                                value={automationCommandName}
                                maxLength={120}
                                onChange={(event) => setAutomationCommandName(event.target.value)}
                              />
                            </div>
                            <div>
                              <label htmlFor="automation-command-location" className="mb-1.5 block text-xs font-medium text-zinc-300">
                                Primary location for this workflow
                              </label>
                              <select
                                id="automation-command-location"
                                className={selectClass}
                                value={automationCommandLocationId}
                                onChange={(event) => {
                                  setAutomationCommandLocationId(event.target.value);
                                  setAutomationCommandAdditionalLocationIds((current) => current.filter((item) => item !== event.target.value));
                                }}
                              >
                                {automationCommandLocations.map((location) => (
                                  <option key={location.id} value={location.id}>{location.label}</option>
                                ))}
                              </select>
                              {automationCommandLocations.length > 1 ? (
                                <details className="mt-2 rounded-md border border-[#303137] bg-[#141518] p-2">
                                  <summary className="cursor-pointer text-xs font-medium text-zinc-300">
                                    Add report access for other locations
                                  </summary>
                                  <div className="mt-2 space-y-2">
                                    {automationCommandLocations
                                      .filter((location) => location.id !== automationCommandLocationId)
                                      .map((location) => (
                                        <label key={location.id} className="flex items-start gap-2 text-xs text-zinc-300">
                                          <input
                                            type="checkbox"
                                            className="mt-0.5"
                                            checked={automationCommandAdditionalLocationIds.includes(location.id)}
                                            onChange={(event) => setAutomationCommandAdditionalLocationIds((current) => (
                                              event.target.checked
                                                ? [...current, location.id].slice(0, 9)
                                                : current.filter((item) => item !== location.id)
                                            ))}
                                          />
                                          <span>{location.label}</span>
                                        </label>
                                      ))}
                                  </div>
                                  <p className="mt-2 text-xs leading-5 text-zinc-500">
                                    Additional locations allow saved-report retrieval only. Paid checks, refreshes, recommendations, drafts, review requests, approvals, and publishing remain limited to the primary location.
                                  </p>
                                </details>
                              ) : null}
                            </div>
                            <button
                              type="button"
                              className={primaryButtonClass}
                              disabled={
                                busyAction === "automation-command-create" ||
                                automationCommandName.trim().length < 2 ||
                                !automationCommandLocationId
                              }
                              onClick={() => void createAutomationCommandAccess()}
                            >
                              {busyAction === "automation-command-create" ? "Creating..." : "Create report access"}
                            </button>
                          </div>
                        ) : automationCommandLoadState === "ready" ? (
                          <p className="mt-3 rounded-md border border-[#303137] bg-[#101114] p-3 text-xs leading-5 text-zinc-400">
                            Ask the workspace owner to create or replace the workflow key.
                          </p>
                        ) : null}

                        {activeAutomationServiceAccount ? (
                          <div className="mt-3 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-4">
                            <p className="text-sm font-semibold text-emerald-100">Connect any supported workflow tool</p>
                            <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs leading-5 text-zinc-300">
                              <li>Download the connection guide, or import the API file into a compatible builder.</li>
                              <li>Save the one-time workflow key in the tool&apos;s private Bearer credential setting.</li>
                              <li>Run the safe connection check before choosing an enabled action.</li>
                              <li>Test the workflow once, then turn it on only when the saved result looks correct.</li>
                            </ol>
                            <p className="mt-2 text-xs leading-5 text-zinc-500">
                              The downloads never contain your workflow key. The separate n8n starter remains available as an optional shortcut.
                            </p>
                          </div>
                        ) : null}

                        {activeAutomationServiceAccount ? (
                          <details className="group mt-3 rounded-md border border-[#303137] bg-[#101114]">
                            <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium text-zinc-300">
                              Manual request examples (advanced)
                            </summary>
                            <div className="space-y-3 border-t border-[#292a2f] p-3 text-xs leading-5 text-zinc-400">
                              <ol className="list-decimal space-y-1 pl-5">
                                <li>Add an HTTP Request node and choose POST.</li>
                                <li>Use <code className="text-zinc-200">/api/v1/automation/commands</code> on your InsightOS domain.</li>
                                <li>Add an Authorization header with <code className="text-zinc-200">Bearer YOUR_WORKFLOW_KEY</code>.</li>
                                <li>Send the JSON body below, replacing the report ID and the two run IDs.</li>
                              </ol>
                              <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                schema_version: "insightos.automation.command.v1",
                                command_type: "report.retrieve",
                                organization_id: organizationId,
                                location_id: activeAutomationServiceAccount.location_id,
                                correlation_id: "n8n-run-REPLACE",
                                idempotency_key: "n8n-report-REPLACE",
                                reason: "Copy a saved report into this workflow",
                                target: { report_id: "REPLACE-WITH-REPORT-ID" },
                              }, null, 2)}</pre>
                              <p>
                                Reusing the same idempotency key safely returns the first result instead of running the command twice. The workflow receives only saved report facts and ready file references.
                              </p>
                              {activeAutomationServiceAccount.allowed_commands.includes("report.generate_saved") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Create a private report from saved results</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "report.generate_saved",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-report-month-REPLACE",
                                    idempotency_key: "n8n-report-month-REPLACE",
                                    reason: "Create a private report from saved InsightOS results",
                                    target: { campaign_id: "REPLACE-WITH-CAMPAIGN-ID" },
                                  }, null, 2)}</pre>
                                  <p>
                                    Use one stable idempotency key for each reporting period. This only assembles saved evidence; it does not collect fresh data or deliver the report.
                                  </p>
                                </>
                              ) : null}
                              {activeAutomationServiceAccount.allowed_commands.includes("recommendation.retrieve") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Retrieve a saved recommendation for owner review</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "recommendation.retrieve",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-recommendation-REPLACE",
                                    idempotency_key: "n8n-recommendation-REPLACE",
                                    reason: "Copy a saved recommendation into this workflow",
                                    target: { recommendation_id: "REPLACE-WITH-RECOMMENDATION-ID" },
                                  }, null, 2)}</pre>
                                  <p>This returns saved owner-facing facts only. It does not approve or execute the recommendation.</p>
                                </>
                              ) : null}
                              {activeAutomationServiceAccount.allowed_commands.includes("connection.refresh_saved") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Refresh one connected source</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "connection.refresh_saved",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-refresh-REPLACE",
                                    idempotency_key: "n8n-refresh-REPLACE",
                                    reason: "Refresh data from an existing connection",
                                    target: { connection_id: "REPLACE-WITH-CONNECTION-ID" },
                                  }, null, 2)}</pre>
                                  <p>This queues only the named existing connection and returns a job status. Reusing the idempotency key cannot create a second request.</p>
                                </>
                              ) : null}
                              {activeAutomationServiceAccount.allowed_commands.includes("listing.check_public") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Run one priced public listing check</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "listing.check_public",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-listings-REPLACE",
                                    idempotency_key: "n8n-listings-REPLACE",
                                    reason: "Check supported public listings for this location",
                                    target: { campaign_id: activeAutomationCampaign?.id || "REPLACE-WITH-CAMPAIGN-ID" },
                                  }, null, 2)}</pre>
                                  <p>Use a new stable key for each intended check. A retry with the same key returns the first run and cannot reserve credits twice.</p>
                                </>
                              ) : null}
                              {activeAutomationServiceAccount.allowed_commands.includes("content.create_working_draft") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Start one accepted working draft</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "content.create_working_draft",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-draft-REPLACE",
                                    idempotency_key: "n8n-draft-REPLACE",
                                    reason: "Start the owner-accepted content brief",
                                    target: {
                                      campaign_id: activeAutomationCampaign?.id || "REPLACE-WITH-CAMPAIGN-ID",
                                      brief_id: "REPLACE-WITH-ACCEPTED-BRIEF-ID",
                                    },
                                  }, null, 2)}</pre>
                                  <p>A draft is created only for an already accepted brief at this location. Reusing the key returns the same private draft.</p>
                                </>
                              ) : null}
                              {activeAutomationServiceAccount.allowed_commands.includes("content.request_draft_review") ? (
                                <>
                                  <p className="font-medium text-zinc-300">Ask the owner to review one private draft</p>
                                  <pre className="overflow-x-auto rounded-md border border-[#292a2f] bg-[#141518] p-3 font-mono text-[11px] leading-5 text-zinc-300">{JSON.stringify({
                                    schema_version: "insightos.automation.command.v1",
                                    command_type: "content.request_draft_review",
                                    organization_id: organizationId,
                                    location_id: activeAutomationServiceAccount.location_id,
                                    correlation_id: "n8n-draft-review-REPLACE",
                                    idempotency_key: "n8n-draft-review-REPLACE",
                                    reason: "Ask the owner to review the private draft",
                                    target: {
                                      campaign_id: activeAutomationCampaign?.id || "REPLACE-WITH-CAMPAIGN-ID",
                                      draft_id: "REPLACE-WITH-WORKING-DRAFT-ID",
                                    },
                                  }, null, 2)}</pre>
                                  <p>The request appears beside that exact private draft. It cannot approve, schedule, publish, or change the website.</p>
                                </>
                              ) : null}
                            </div>
                          </details>
                        ) : null}

                        {automationCommandHistory.length > 0 ? (
                          <details className="group mt-3 rounded-md border border-[#303137] bg-[#101114]">
                            <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium text-zinc-300">
                              Recent workflow requests ({automationCommandHistory.length})
                            </summary>
                            <div className="space-y-2 border-t border-[#292a2f] p-3">
                              {automationCommandHistory.slice(0, 10).map((receipt) => (
                                <div key={receipt.id} className="rounded-md border border-[#292a2f] bg-[#141518] px-3 py-2 text-xs">
                                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                                    <span className={receipt.status === "succeeded" ? "text-emerald-300" : "text-amber-300"}>
                                    {receipt.status === "succeeded"
                                      ? receipt.command_type === "report.generate_saved"
                                        ? "Private report created"
                                        : receipt.command_type === "recommendation.request_review"
                                          ? "Owner review requested"
                                        : receipt.command_type === "recommendation.retrieve"
                                          ? "Saved recommendation returned"
                                        : receipt.command_type === "connection.refresh_saved"
                                          ? "Connected data refresh accepted"
                                        : receipt.command_type === "listing.check_public"
                                          ? "Public listing check accepted"
                                        : receipt.command_type === "content.create_working_draft"
                                          ? "Private working draft created"
                                        : receipt.command_type === "content.request_draft_review"
                                          ? "Private draft review requested"
                                        : receipt.command_type === "review.retrieve"
                                          ? "Saved review facts returned"
                                        : receipt.command_type === "review.create_response_draft"
                                          ? "Private reply draft requested"
                                          : "Saved report returned"
                                      : "Request safely declined"}
                                    </span>
                                    <span className="text-zinc-500">{formatTimestamp(receipt.completed_at)}</span>
                                  </div>
                                  <p className="mt-1 leading-5 text-zinc-400">{receipt.result.message}</p>
                                  {receipt.result.resource?.href ? (
                                    <a className="mt-1 inline-flex text-xs font-medium text-sky-300 hover:text-sky-200" href={receipt.result.resource.href}>
                                      Open saved result
                                    </a>
                                  ) : receipt.status === "denied" ? (
                                    <p className="mt-1 text-[11px] leading-4 text-zinc-500">
                                      Nothing was changed. Review the message above, then retry with the same request key after fixing the issue.
                                    </p>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          </details>
                        ) : null}
                      </div>
                    ) : null}

                    {automationWorkflowDirection === "outgoing" && usageAllowance.external_automation.outbound_contract?.supported_events.length ? (
                      <details className="group mt-3 rounded-md border border-[#292a2f] bg-[#101114]">
                        <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-medium text-zinc-300">
                          See every update InsightOS can send
                        </summary>
                        <div className="border-t border-[#292a2f] p-3">
                          <p className="text-xs leading-5 text-zinc-500">
                            Reports, recommendations, and completed approved actions can be sent after a successful test.
                          </p>
                          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                            {usageAllowance.external_automation.outbound_contract?.supported_events.map((event) => (
                              <li key={event.code} className="rounded-lg border border-[#292a2f] bg-[#141518] px-3 py-2">
                                <p className="text-xs font-medium text-zinc-200">{event.label}</p>
                                <p className="mt-1 text-xs leading-5 text-zinc-500">{event.summary}</p>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </details>
                    ) : null}
                    <p className="mt-4 border-t border-[#292a2f] pt-3 text-xs leading-5 text-zinc-500">
                      Workflow tools can receive updates. They cannot approve recommendations, publish content, edit WordPress, or change a Google Business Profile.
                    </p>
                  </section>
            ) : null}

            <section aria-labelledby="migration-heading" className="rounded-md border border-[#292a2f] bg-[#141518] p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Moving from another SEO tool
                  </p>
                  <h2 id="migration-heading" className="mt-1 text-xl font-semibold tracking-[-0.03em] text-white">
                    Bring over your setup and useful history
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-300">
                    Add locations, searches, competitors, past rankings, listing history, and report recipients. Check every match before anything is added; imported recipients stay off.
                  </p>
                </div>
                <button type="button" className={secondaryButtonClass} onClick={downloadMigrationTemplate}>
                  Download CSV template
                </button>
              </div>

              <div className="mt-5 grid gap-4 border-t border-[#292a2f] pt-5 lg:grid-cols-[220px_minmax(0,1fr)_auto] lg:items-end">
                <div>
                  <label htmlFor="migration-source" className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Coming from
                  </label>
                  <select
                    id="migration-source"
                    className={selectClass}
                    value={migrationSource}
                    onChange={(event) => {
                      setMigrationSource(event.target.value as "semrush" | "brightlocal" | "other");
                      setMigrationReview(null);
                      setMigrationConfirmed(false);
                      setMigrationUploadId("");
                      setMigrationUploadProgress(0);
                    }}
                  >
                    <option value="other">Another spreadsheet</option>
                    <option value="semrush">Semrush</option>
                    <option value="brightlocal">BrightLocal</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="migration-file" className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Completed template
                  </label>
                  <input
                    id="migration-file"
                    type="file"
                    accept=".csv,text/csv"
                    className="block w-full rounded-md border border-[#303137] bg-[#101114] px-3 py-2 text-sm text-zinc-200 file:mr-3 file:rounded file:border-0 file:bg-accent-500/15 file:px-3 file:py-1.5 file:font-semibold file:text-accent-100"
                    onChange={(event) => void chooseMigrationFile(event.target.files?.[0])}
                  />
                  <p className="mt-1.5 text-xs text-zinc-500">
                    {migrationFileName || "CSV only · up to 25,000 rows · large files resume after an interruption · no changes are made during review"}
                  </p>
                  {busyAction === "migration-dry-run" && migrationUploadId ? (
                    <p className="mt-1.5 text-xs font-medium text-sky-200" role="status">
                      Secure upload {migrationUploadProgress}% complete. Uploaded parts are saved for seven days.
                    </p>
                  ) : null}
                </div>
                <button
                  type="button"
                  className={primaryButtonClass}
                  disabled={!migrationCsv || busyAction === "migration-dry-run"}
                  onClick={() => void reviewMigrationFile()}
                >
                  {busyAction === "migration-dry-run" ? "Checking file..." : "Review file"}
                </button>
              </div>

              {migrationReview ? (
                <div className="mt-5 border-t border-[#292a2f] pt-5">
                  <p className="mb-4 text-xs leading-5 text-zinc-500">
                    Using {migrationReview.adapter.replaceAll("_", " ")} to match this file&apos;s familiar headings.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
                    {[
                      ["Ready to add", migrationReview.summary.ready, "text-emerald-200"],
                      ["Already saved", migrationReview.summary.already_saved, "text-sky-200"],
                      ["Repeated rows", migrationReview.summary.duplicates_in_file, "text-zinc-300"],
                      ["Needs attention", migrationReview.summary.needs_attention, "text-amber-200"],
                      ["Past rankings", migrationReview.summary.ranking_history, "text-violet-200"],
                      ["Past listings", migrationReview.summary.listing_history, "text-violet-200"],
                      ["Report recipients", migrationReview.summary.report_recipients, "text-sky-200"],
                    ].map(([label, value, color]) => (
                      <div key={String(label)} className="border-l-2 border-[#35363c] pl-3">
                        <p className="text-xs text-zinc-500">{label}</p>
                        <p className={`mt-1 text-2xl font-semibold ${color}`}>{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-4 text-sm leading-6 text-zinc-300">{migrationReview.next_step}</p>

                  {migrationReview.ignored_columns.length > 0 ? (
                    <div className="mt-4 rounded-md border border-amber-500/25 bg-amber-500/5 p-4">
                      <p className="text-sm font-semibold text-amber-100">
                        {migrationReview.ignored_columns.length} file column{migrationReview.ignored_columns.length === 1 ? " is" : "s are"} not being imported
                      </p>
                      <p className="mt-1 text-sm leading-6 text-zinc-300">
                        These columns stay in your original file and are listed here so nothing is silently treated as an InsightOS measurement.
                      </p>
                      <ul className="mt-3 space-y-2 text-sm text-zinc-300">
                        {migrationReview.ignored_columns.map((item) => (
                          <li key={item.column}>
                            <strong className="text-white">{item.column}</strong> · {item.populated_rows} filled row{item.populated_rows === 1 ? "" : "s"} · {item.reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="mt-4 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                    {migrationReview.rows
                      .filter((row) => row.status === "needs_attention" || row.status === "duplicate")
                      .map((row) => (
                        <article key={`${row.row_number}-${row.record_type}`} className="grid gap-2 py-3 sm:grid-cols-[90px_minmax(0,1fr)]">
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Row {row.row_number}</p>
                          <div>
                            <p className="text-sm font-semibold text-white">
                              {row.location_name || "Location name missing"} · {row.record_type || "Unknown row"}
                            </p>
                            <p className="mt-1 text-sm text-amber-100">
                              {row.issues[0]?.message || row.detail}
                            </p>
                          </div>
                        </article>
                      ))}
                    {migrationReview.summary.needs_attention === 0 && migrationReview.summary.duplicates_in_file === 0 ? (
                      <p className="py-4 text-sm font-medium text-emerald-200">
                        Every row is ready for final review. Nothing has been imported yet.
                      </p>
                    ) : null}
                  </div>

                  {migrationReview.pagination?.has_more ? (
                    <button
                      type="button"
                      className={`${secondaryButtonClass} mt-4`}
                      disabled={busyAction === "migration-review-more"}
                      onClick={() => void loadMoreMigrationReviewRows()}
                    >
                      {busyAction === "migration-review-more"
                        ? "Loading more rows..."
                        : `Review more rows (${migrationReview.rows.length} of ${migrationReview.pagination.total_rows} loaded)`}
                    </button>
                  ) : null}

                  {migrationReview.summary.needs_attention === 0 && migrationReview.summary.ready > 0 && !migrationBatch ? (
                    <div className="mt-5 rounded-md border border-emerald-500/25 bg-emerald-500/5 p-4">
                      <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-zinc-200">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-orange-500"
                          checked={migrationConfirmed}
                          onChange={(event) => setMigrationConfirmed(event.target.checked)}
                        />
                        <span>
                          I reviewed this file. Add the {migrationReview.summary.ready} ready rows and skip anything already saved or repeated.
                        </span>
                      </label>
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          className={primaryButtonClass}
                          disabled={!migrationConfirmed || !migrationRequestId || busyAction === "migration-apply"}
                          onClick={() => void applyMigrationFile()}
                        >
                          {busyAction === "migration-apply" ? "Adding reviewed rows..." : "Import reviewed rows"}
                        </button>
                        <p className="text-xs leading-5 text-zinc-500">
                          The reviewed file is locked to this action. If it changes, InsightOS will require a new review.
                        </p>
                      </div>
                    </div>
                  ) : null}

                  {migrationBatch ? (
                    <div className="mt-5 flex flex-col gap-4 rounded-md border border-sky-500/25 bg-sky-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-sky-100">
                          {migrationBatch.status === "rolled_back" ? "Import removed safely" : "Import complete"}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-zinc-300">
                          {migrationBatch.status === "rolled_back"
                            ? "The records created by this import were removed, and its audit history was kept."
                            : `${migrationBatch.summary.locations_created || 0} locations, ${migrationBatch.summary.keywords_created || 0} searches, ${migrationBatch.summary.competitors_created || 0} competitors, ${migrationBatch.summary.ranking_history_created || 0} past ranking points, ${migrationBatch.summary.listing_history_created || 0} past listing records, and ${migrationBatch.summary.report_recipients_created || 0} report recipients were added. Imported recipients are off until reviewed.`}
                        </p>
                      </div>
                      {migrationBatch.rollback_available ? (
                        <button
                          type="button"
                          className={secondaryButtonClass}
                          disabled={busyAction === `migration-rollback-${migrationBatch.id}`}
                          onClick={() => void rollbackMigration(migrationBatch)}
                        >
                          {busyAction === `migration-rollback-${migrationBatch.id}` ? "Checking rollback..." : "Undo this import"}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {migrationHistory.length > 0 ? (
                <div className="mt-5 border-t border-[#292a2f] pt-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                    Recent imports
                  </p>
                  <div className="mt-3 divide-y divide-[#292a2f] border-y border-[#292a2f]">
                    {migrationHistory.slice(0, 5).map((batch) => (
                      <div key={batch.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <p className="text-sm font-medium text-white">
                            {batch.source_filename || "Imported setup"}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500">
                            {formatTimestamp(batch.applied_at)} · {batch.summary.records_applied || 0} rows · {batch.status === "rolled_back" ? "Undone" : "Applied"}
                          </p>
                        </div>
                        {batch.rollback_available ? (
                          <button
                            type="button"
                            className={secondaryButtonClass}
                            disabled={busyAction === `migration-rollback-${batch.id}`}
                            onClick={() => void rollbackMigration(batch)}
                          >
                            Undo import
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="mt-5 border-t border-[#292a2f] pt-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
                  Switching checklist
                </p>
                <h3 className="mt-1 text-lg font-semibold text-white">Finish the move with fresh measurements</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-400">
                  Imported rankings and listings give you background history. They never count as a new InsightOS check. Complete these steps before using the new workspace as your current source of truth.
                </p>
                <ol className="mt-4 grid gap-3 lg:grid-cols-2">
                  {[
                    {
                      title: "Review and import the old setup",
                      detail: "Keep the source file and confirm every row before adding it.",
                      done: migrationHistory.some((batch) => batch.status === "applied"),
                    },
                    {
                      title: "Connect the business Google account",
                      detail: "This allows current website and business profile data to be collected.",
                      done: Boolean(payload?.google_oauth.connected),
                    },
                    {
                      title: "Match each location to its live source",
                      detail: "A saved location needs its own website or business profile connection.",
                      done: connections.length > 0,
                    },
                    {
                      title: "Run the first fresh checks",
                      detail: "Use the new results as the baseline; use imported history only for context.",
                      done: healthyConnectionItems.some((item) => Boolean(item.last_success_at)),
                    },
                  ].map((step, index) => (
                    <li key={step.title} className="flex gap-3 rounded-md border border-[#292a2f] bg-[#101114] p-4">
                      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${step.done ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-100" : "border-zinc-700 text-zinc-400"}`}>
                        {step.done ? "✓" : index + 1}
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-white">{step.title}</p>
                        <p className="mt-1 text-sm leading-5 text-zinc-400">{step.detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </section>
          </>
        )}
      </section>
    </AppShell>
  );
}
