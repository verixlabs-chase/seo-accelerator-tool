"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { platformApi } from "../api";

const STATE_LABELS = {
  pass: "Passed",
  attention: "Needs attention",
  needs_live_proof: "Needs live proof",
  blocker: "Blocking",
};

const STATE_COLORS = {
  pass: "#166534",
  attention: "#854d0e",
  needs_live_proof: "#1e40af",
  blocker: "#991b1b",
};

const MANUAL_GATES = {
  critical_journeys: { label: "Paid customer journeys", proofKind: "production_smoke" },
  recovery_drills: { label: "Recovery and rollback drills", proofKind: "recovery_drill" },
  customer_communications: { label: "Incident and status communication", proofKind: "communication_test" },
  first_use_comprehension: { label: "Non-technical first-use proof", proofKind: "moderated_test" },
  known_limitations: { label: "Sales claims and known limitations", proofKind: "capability_review" },
};

const STATUS_SURFACES = {
  dashboard: "Overview",
  website_analysis: "Website analysis",
  rankings: "Rank tracking",
  local_visibility: "Local visibility",
  reviews: "Reviews",
  reports: "Reports",
  automations: "Automations",
  billing: "Billing",
  connections: "Connections",
  sign_in: "Sign in",
};

function localDateTime(daysFromNow = 0) {
  const value = new Date(Date.now() + daysFromNow * 24 * 60 * 60 * 1000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

function titleCase(value) {
  return String(value || "Other")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function decisionLabel(value) {
  if (value === "go") return "Go";
  if (value === "no_go") return "No go";
  if (value === "ready_for_decision") return "Ready for owner decision";
  return "Hold";
}

export default function PlatformLaunchReadinessPage() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [proofBusy, setProofBusy] = useState(false);
  const [proofNotice, setProofNotice] = useState("");
  const [proofError, setProofError] = useState("");
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionNotice, setDecisionNotice] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const [viewer, setViewer] = useState(null);
  const [statusPayload, setStatusPayload] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusNotice, setStatusNotice] = useState("");
  const [proofForm, setProofForm] = useState({
    gateCode: "critical_journeys",
    result: "passed",
    summary: "",
    evidenceReference: "",
    observedAt: localDateTime(),
    expiresAt: localDateTime(30),
  });
  const [decisionForm, setDecisionForm] = useState({
    decision: "no_go",
    releaseReference: "",
    rationale: "",
    knownLimitations: false,
    supportOwner: false,
    rollbackOwner: false,
    evidenceCurrent: false,
  });
  const [statusForm, setStatusForm] = useState({
    incidentKey: "",
    state: "investigating",
    impact: "minor",
    title: "",
    message: "",
    affectedSurfaces: ["dashboard"],
    visibleToCustomers: true,
    startsAt: localDateTime(),
    endsAt: "",
  });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [readiness, currentViewer] = await Promise.all([
        platformApi("/system/launch-readiness"),
        platformApi("/auth/me", { method: "GET" }),
      ]);
      setPayload(readiness);
      setViewer(currentViewer);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Launch readiness could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    loadCustomerStatus();
  }, []);

  async function loadCustomerStatus() {
    setStatusError("");
    try {
      setStatusPayload(await platformApi("/system/customer-status", { method: "GET" }));
    } catch (caught) {
      setStatusError(caught instanceof Error ? caught.message : "Customer status history could not be loaded.");
    }
  }

  async function recordCustomerStatus(event) {
    event.preventDefault();
    setStatusBusy(true);
    setStatusError("");
    setStatusNotice("");
    try {
      const response = await platformApi("/system/customer-status", {
        method: "POST",
        body: JSON.stringify({
          incident_key: statusForm.incidentKey,
          state: statusForm.state,
          impact: statusForm.impact,
          title: statusForm.title,
          message: statusForm.message,
          affected_surfaces: statusForm.affectedSurfaces,
          visible_to_customers: statusForm.visibleToCustomers,
          starts_at: new Date(statusForm.startsAt).toISOString(),
          ends_at: statusForm.endsAt ? new Date(statusForm.endsAt).toISOString() : null,
        }),
      });
      setStatusPayload(response.status);
      setStatusNotice(response.created ? "The customer update was published and saved permanently." : "That exact update was already saved.");
      setStatusForm((current) => ({ ...current, title: "", message: "" }));
    } catch (caught) {
      setStatusError(caught instanceof Error ? caught.message : "The customer update could not be saved.");
    } finally {
      setStatusBusy(false);
    }
  }

  function toggleStatusSurface(code) {
    setStatusForm((current) => ({
      ...current,
      affectedSurfaces: current.affectedSurfaces.includes(code)
        ? current.affectedSurfaces.filter((item) => item !== code)
        : [...current.affectedSurfaces, code],
    }));
  }

  async function recordProof(event) {
    event.preventDefault();
    setProofBusy(true);
    setProofError("");
    setProofNotice("");
    try {
      const response = await platformApi("/system/launch-readiness/proofs", {
        method: "POST",
        body: JSON.stringify({
          gate_code: proofForm.gateCode,
          result: proofForm.result,
          proof_kind: MANUAL_GATES[proofForm.gateCode].proofKind,
          summary: proofForm.summary,
          evidence_reference: proofForm.evidenceReference,
          observed_at: new Date(proofForm.observedAt).toISOString(),
          expires_at: new Date(proofForm.expiresAt).toISOString(),
        }),
      });
      setPayload(response.readiness);
      setProofNotice(response.created ? "The proof was added to the permanent history." : "That exact proof was already saved.");
      setProofForm((current) => ({ ...current, summary: "", evidenceReference: "" }));
    } catch (caught) {
      setProofError(caught instanceof Error ? caught.message : "The proof could not be saved.");
    } finally {
      setProofBusy(false);
    }
  }

  async function recordDecision(event) {
    event.preventDefault();
    setDecisionBusy(true);
    setDecisionError("");
    setDecisionNotice("");
    try {
      const response = await platformApi("/system/launch-readiness/decisions", {
        method: "POST",
        body: JSON.stringify({
          decision: decisionForm.decision,
          release_reference: decisionForm.releaseReference,
          rationale: decisionForm.rationale,
          known_limitations_acknowledged: decisionForm.knownLimitations,
          support_owner_confirmed: decisionForm.supportOwner,
          rollback_owner_confirmed: decisionForm.rollbackOwner,
          evidence_current_confirmed: decisionForm.evidenceCurrent,
        }),
      });
      setPayload(response.readiness);
      setDecisionNotice(response.created ? "The owner decision was added to the permanent history." : "That exact decision was already saved.");
      setDecisionForm((current) => ({ ...current, releaseReference: "", rationale: "" }));
    } catch (caught) {
      setDecisionError(caught instanceof Error ? caught.message : "The decision could not be saved.");
    } finally {
      setDecisionBusy(false);
    }
  }

  const groupedItems = useMemo(() => {
    const groups = new Map();
    for (const item of payload?.items || []) {
      const items = groups.get(item.category) || [];
      items.push(item);
      groups.set(item.category, items);
    }
    return Array.from(groups.entries());
  }, [payload]);
  const isPlatformOwner = viewer?.platform_role === "platform_owner";

  return (
    <main style={{ maxWidth: 1080, margin: "40px auto", padding: 24 }}>
      <p>
        <Link href="/platform">Back to Platform Home</Link>
      </p>
      <h1>Paid Launch Readiness</h1>
      <p>
        <Link href="/platform/capabilities">Review production capabilities and limitations</Link>
      </p>
      <p>
        <Link href="/platform/experience">Review desktop, mobile, and non-technical experience proof</Link>
      </p>
      <p style={{ maxWidth: 760, lineHeight: 1.6 }}>
        This internal board keeps saved automated facts separate from production-owned proof. It does
        not turn unlike evidence into a readiness score.
      </p>

      {loading ? <p role="status">Checking saved launch evidence...</p> : null}
      {error ? (
        <div role="alert" style={{ border: "1px solid #991b1b", padding: 16, marginTop: 16 }}>
          <strong>Readiness is unavailable.</strong>
          <p>{error}</p>
          <button type="button" onClick={load}>Try again</button>
        </div>
      ) : null}

      {payload ? (
        <>
          <section aria-labelledby="launch-decision" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
            <h2 id="launch-decision" style={{ marginTop: 0 }}>
              Current decision: {decisionLabel(payload.overall_state)}
            </h2>
            <p>{payload.headline}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {Object.entries(STATE_LABELS).map(([state, label]) => (
                <div key={state} style={{ minWidth: 150, border: "1px solid #ddd", padding: 12 }}>
                  <div style={{ color: STATE_COLORS[state], fontWeight: 700 }}>{label}</div>
                  <div style={{ fontSize: 28 }}>{payload.counts?.[state] ?? 0}</div>
                </div>
              ))}
            </div>
            <p style={{ marginBottom: 0 }}>
              Checked {new Date(payload.evaluated_at).toLocaleString()}
            </p>
            {payload.latest_decision ? (
              <div style={{ borderTop: "1px solid #ddd", marginTop: 16, paddingTop: 16 }}>
                <strong>Latest recorded owner decision: {decisionLabel(payload.latest_decision.decision)}</strong>
                <p>{payload.latest_decision.rationale}</p>
                <p style={{ marginBottom: 0 }}>
                  {payload.latest_decision.release_reference} · {new Date(payload.latest_decision.created_at).toLocaleString()} · {payload.latest_decision.current ? "Current evidence" : "Superseded by newer evidence"}
                </p>
              </div>
            ) : null}
          </section>

          <section aria-labelledby="customer-status-updates" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
            <h2 id="customer-status-updates" style={{ marginTop: 0 }}>Customer service updates</h2>
            <p>
              Publish clear notices that appear inside the customer product. Do not include supplier
              names, raw errors, customer identifiers, links, or credentials.
            </p>
            {statusPayload?.active?.incidents?.length ? (
              <div role="status" style={{ borderLeft: "4px solid #854d0e", paddingLeft: 12, marginBottom: 18 }}>
                <strong>{statusPayload.active.incidents.length} customer notice{statusPayload.active.incidents.length === 1 ? "" : "s"} active</strong>
                <ul>
                  {statusPayload.active.incidents.map((incident) => (
                    <li key={incident.id}>{incident.title} — {titleCase(incident.state)}</li>
                  ))}
                </ul>
              </div>
            ) : <p role="status">No customer notices are active.</p>}

            {isPlatformOwner ? (
              <form onSubmit={recordCustomerStatus} style={{ display: "grid", gap: 14, maxWidth: 760 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14 }}>
                  <label>
                    Incident key
                    <input required minLength={3} maxLength={64} value={statusForm.incidentKey} onChange={(event) => setStatusForm((current) => ({ ...current, incidentKey: event.target.value }))} placeholder="reports-delayed-2026-08" style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                  <label>
                    Update state
                    <select value={statusForm.state} onChange={(event) => setStatusForm((current) => ({ ...current, state: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                      <option value="investigating">Investigating</option>
                      <option value="identified">Issue identified</option>
                      <option value="monitoring">Fix in place</option>
                      <option value="resolved">Resolved</option>
                      <option value="maintenance">Planned maintenance</option>
                    </select>
                  </label>
                  <label>
                    Customer impact
                    <select value={statusForm.impact} onChange={(event) => setStatusForm((current) => ({ ...current, impact: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                      <option value="none">No current impact</option>
                      <option value="minor">Minor</option>
                      <option value="major">Major</option>
                      <option value="critical">Critical</option>
                    </select>
                  </label>
                </div>
                <label>
                  Customer-facing title
                  <input required minLength={8} maxLength={100} value={statusForm.title} onChange={(event) => setStatusForm((current) => ({ ...current, title: event.target.value }))} placeholder="Some reports are taking longer" style={{ display: "block", width: "100%", marginTop: 6 }} />
                </label>
                <label>
                  Customer update
                  <textarea required minLength={20} maxLength={500} value={statusForm.message} onChange={(event) => setStatusForm((current) => ({ ...current, message: event.target.value }))} placeholder="What customers may notice, what is being done, and whether their saved work is safe." style={{ display: "block", width: "100%", minHeight: 100, marginTop: 6 }} />
                </label>
                <fieldset>
                  <legend>Affected areas</legend>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
                    {Object.entries(STATUS_SURFACES).map(([code, label]) => (
                      <label key={code} style={{ display: "flex", gap: 6 }}>
                        <input type="checkbox" checked={statusForm.affectedSurfaces.includes(code)} onChange={() => toggleStatusSurface(code)} />
                        {label}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                  <label>
                    Starts
                    <input type="datetime-local" required value={statusForm.startsAt} onChange={(event) => setStatusForm((current) => ({ ...current, startsAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                  <label>
                    Ends {statusForm.state === "resolved" || statusForm.state === "maintenance" ? "(required)" : "(optional)"}
                    <input type="datetime-local" required={statusForm.state === "resolved" || statusForm.state === "maintenance"} value={statusForm.endsAt} onChange={(event) => setStatusForm((current) => ({ ...current, endsAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                </div>
                <label style={{ display: "flex", gap: 8 }}>
                  <input type="checkbox" checked={statusForm.visibleToCustomers} onChange={(event) => setStatusForm((current) => ({ ...current, visibleToCustomers: event.target.checked }))} />
                  Show this update to signed-in customers
                </label>
                <button type="submit" disabled={statusBusy || statusForm.affectedSurfaces.length === 0} style={{ width: "fit-content" }}>
                  {statusBusy ? "Publishing update..." : "Publish customer update"}
                </button>
              </form>
            ) : <p>Platform administrators can review history. A platform owner must publish updates.</p>}
            {statusNotice ? <p role="status" style={{ color: "#166534" }}>{statusNotice}</p> : null}
            {statusError ? <p role="alert" style={{ color: "#991b1b" }}>{statusError}</p> : null}
            {statusPayload?.updates?.length ? (
              <details style={{ marginTop: 18 }}>
                <summary>Permanent update history ({statusPayload.updates.length})</summary>
                <ol>
                  {statusPayload.updates.slice(0, 20).map((update) => (
                    <li key={update.id} style={{ marginTop: 10 }}>
                      <strong>{update.title}</strong> — {titleCase(update.state)} · update {update.update_number} · {new Date(update.updated_at).toLocaleString()}
                    </li>
                  ))}
                </ol>
              </details>
            ) : null}
          </section>

          {isPlatformOwner ? <section aria-labelledby="record-launch-proof" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
            <h2 id="record-launch-proof" style={{ marginTop: 0 }}>Record current production proof</h2>
            <p>
              Platform owners can append a time-bounded result. Use an internal receipt or ticket
              reference—never paste a URL, credential, webhook address, or provider response.
            </p>
            <form onSubmit={recordProof} style={{ display: "grid", gap: 14, maxWidth: 720 }}>
              <label>
                Launch gate
                <select
                  value={proofForm.gateCode}
                  onChange={(event) => setProofForm((current) => ({ ...current, gateCode: event.target.value }))}
                  style={{ display: "block", width: "100%", marginTop: 6 }}
                >
                  {Object.entries(MANUAL_GATES).map(([code, gate]) => (
                    <option key={code} value={code}>{gate.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Result
                <select
                  value={proofForm.result}
                  onChange={(event) => setProofForm((current) => ({ ...current, result: event.target.value }))}
                  style={{ display: "block", width: "100%", marginTop: 6 }}
                >
                  <option value="passed">Passed</option>
                  <option value="failed">Failed — blocks launch</option>
                </select>
              </label>
              <label>
                Plain result summary
                <textarea
                  required
                  minLength={20}
                  maxLength={300}
                  value={proofForm.summary}
                  onChange={(event) => setProofForm((current) => ({ ...current, summary: event.target.value }))}
                  placeholder="What was tested and what happened?"
                  style={{ display: "block", width: "100%", minHeight: 90, marginTop: 6 }}
                />
              </label>
              <label>
                Internal evidence reference
                <input
                  required
                  minLength={8}
                  maxLength={160}
                  value={proofForm.evidenceReference}
                  onChange={(event) => setProofForm((current) => ({ ...current, evidenceReference: event.target.value }))}
                  placeholder="Example: RELEASE-2026-08-20-04"
                  style={{ display: "block", width: "100%", marginTop: 6 }}
                />
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                <label>
                  Observed
                  <input
                    type="datetime-local"
                    required
                    value={proofForm.observedAt}
                    onChange={(event) => setProofForm((current) => ({ ...current, observedAt: event.target.value }))}
                    style={{ display: "block", width: "100%", marginTop: 6 }}
                  />
                </label>
                <label>
                  Recheck by
                  <input
                    type="datetime-local"
                    required
                    value={proofForm.expiresAt}
                    onChange={(event) => setProofForm((current) => ({ ...current, expiresAt: event.target.value }))}
                    style={{ display: "block", width: "100%", marginTop: 6 }}
                  />
                </label>
              </div>
              <button type="submit" disabled={proofBusy} style={{ width: "fit-content" }}>
                {proofBusy ? "Saving proof..." : "Add proof to history"}
              </button>
            </form>
            {proofNotice ? <p role="status" style={{ color: "#166534" }}>{proofNotice}</p> : null}
            {proofError ? <p role="alert" style={{ color: "#991b1b" }}>{proofError}</p> : null}
          </section> : null}

          {isPlatformOwner ? <section aria-labelledby="record-launch-decision" style={{ border: "2px solid #555", padding: 20, marginTop: 24 }}>
            <h2 id="record-launch-decision" style={{ marginTop: 0 }}>Record the owner decision</h2>
            <p>
              A passing board is only ready for a decision. It does not approve launch automatically.
              Any later evidence change makes this decision visibly superseded.
            </p>
            <form onSubmit={recordDecision} style={{ display: "grid", gap: 14, maxWidth: 720 }}>
              <label>
                Decision
                <select
                  value={decisionForm.decision}
                  onChange={(event) => setDecisionForm((current) => ({ ...current, decision: event.target.value }))}
                  style={{ display: "block", width: "100%", marginTop: 6 }}
                >
                  <option value="no_go">No go</option>
                  <option value="go" disabled={payload.evidence_state !== "ready"}>Go — every gate must pass first</option>
                </select>
              </label>
              <label>
                Internal release reference
                <input
                  required
                  minLength={8}
                  maxLength={120}
                  value={decisionForm.releaseReference}
                  onChange={(event) => setDecisionForm((current) => ({ ...current, releaseReference: event.target.value }))}
                  placeholder="Example: LAUNCH-REVIEW-2026-08"
                  style={{ display: "block", width: "100%", marginTop: 6 }}
                />
              </label>
              <label>
                Decision rationale
                <textarea
                  required
                  minLength={20}
                  maxLength={500}
                  value={decisionForm.rationale}
                  onChange={(event) => setDecisionForm((current) => ({ ...current, rationale: event.target.value }))}
                  placeholder="Why is this the correct decision for the evidence shown?"
                  style={{ display: "block", width: "100%", minHeight: 100, marginTop: 6 }}
                />
              </label>
              {[
                ["knownLimitations", "I reviewed the current capabilities and known limitations."],
                ["supportOwner", "The launch support and escalation owner is confirmed."],
                ["rollbackOwner", "The rollback owner and recovery path are confirmed."],
                ["evidenceCurrent", "This decision uses the evidence currently shown on this board."],
              ].map(([key, label]) => (
                <label key={key} style={{ display: "flex", gap: 8, alignItems: "start" }}>
                  <input
                    type="checkbox"
                    checked={decisionForm[key]}
                    onChange={(event) => setDecisionForm((current) => ({ ...current, [key]: event.target.checked }))}
                  />
                  {label}
                </label>
              ))}
              <button type="submit" disabled={decisionBusy} style={{ width: "fit-content" }}>
                {decisionBusy ? "Recording decision..." : "Add decision to history"}
              </button>
            </form>
            {decisionNotice ? <p role="status" style={{ color: "#166534" }}>{decisionNotice}</p> : null}
            {decisionError ? <p role="alert" style={{ color: "#991b1b" }}>{decisionError}</p> : null}
          </section> : null}

          {groupedItems.map(([category, items]) => (
            <section key={category} aria-labelledby={`category-${category}`} style={{ marginTop: 32 }}>
              <h2 id={`category-${category}`}>{titleCase(category)}</h2>
              <div style={{ display: "grid", gap: 14 }}>
                {items.map((item) => (
                  <article key={item.code} style={{ border: "1px solid #ddd", padding: 18 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start" }}>
                      <h3 style={{ margin: 0 }}>{item.title}</h3>
                      <strong style={{ color: STATE_COLORS[item.state], whiteSpace: "nowrap" }}>
                        {STATE_LABELS[item.state] || titleCase(item.state)}
                      </strong>
                    </div>
                    <p>{item.summary}</p>
                    <p><strong>Evidence checked:</strong> {item.evidence}</p>
                    <p style={{ marginBottom: 0 }}><strong>Next:</strong> {item.next_action}</p>
                    {item.proof ? (
                      <div style={{ borderLeft: "3px solid #777", paddingLeft: 12, marginTop: 14 }}>
                        <strong>Latest operator proof</strong>
                        <p style={{ margin: "6px 0" }}>{item.proof.evidence_reference}</p>
                        <p style={{ margin: 0 }}>
                          Observed {new Date(item.proof.observed_at).toLocaleString()} · recheck by {new Date(item.proof.expires_at).toLocaleString()}
                        </p>
                      </div>
                    ) : null}
                    {Object.keys(item.facts || {}).length ? (
                      <details style={{ marginTop: 12 }}>
                        <summary>Saved counts</summary>
                        <dl>
                          {Object.entries(item.facts).map(([key, value]) => (
                            <div key={key} style={{ display: "flex", gap: 8 }}>
                              <dt>{titleCase(key)}:</dt>
                              <dd style={{ margin: 0 }}>{String(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      </details>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ))}

          <section aria-labelledby="readiness-limitations" style={{ marginTop: 32 }}>
            <h2 id="readiness-limitations">What this board does not prove</h2>
            <ul>
              {(payload.limitations || []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
        </>
      ) : null}
    </main>
  );
}
