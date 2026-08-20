"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { platformApi } from "../api";

const STATE_LABELS = {
  passed: "Passed",
  failed: "Failed",
  stale: "Needs a new review",
  missing: "Not reviewed",
};

function localDateTime(daysFromNow = 0) {
  const value = new Date(Date.now() + daysFromNow * 24 * 60 * 60 * 1000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

function reviewState(value) {
  return STATE_LABELS[value] || "Not reviewed";
}

export default function PlatformLaunchExperiencePage() {
  const [payload, setPayload] = useState(null);
  const [viewer, setViewer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({
    reviewKind: "route_audit",
    subjectCode: "overview",
    viewport: "desktop",
    result: "passed",
    sessionReference: "",
    summary: "",
    issueCount: "0",
    blockingIssueCount: "0",
    evidenceReference: "",
    observedAt: localDateTime(),
    expiresAt: localDateTime(30),
  });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [readiness, currentViewer] = await Promise.all([
        platformApi("/system/launch-experience"),
        platformApi("/auth/me", { method: "GET" }),
      ]);
      setPayload(readiness);
      setViewer(currentViewer);
      if (readiness.route_audit?.routes?.[0]?.code) {
        setForm((current) => ({ ...current, subjectCode: readiness.route_audit.routes[0].code }));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Experience evidence could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function setKind(reviewKind) {
    setForm((current) => ({
      ...current,
      reviewKind,
      subjectCode: reviewKind === "route_audit"
        ? (payload?.route_audit?.routes?.[0]?.code || "overview")
        : "first_use_complete_journey",
      viewport: reviewKind === "route_audit" ? "desktop" : "not_applicable",
      sessionReference: "",
    }));
  }

  async function recordReview(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setFormError("");
    try {
      const response = await platformApi("/system/launch-experience/reviews", {
        method: "POST",
        body: JSON.stringify({
          review_kind: form.reviewKind,
          subject_code: form.subjectCode,
          viewport: form.viewport,
          result: form.result,
          session_reference: form.reviewKind === "moderated_session" ? form.sessionReference : null,
          summary: form.summary,
          issue_count: Number(form.issueCount),
          blocking_issue_count: Number(form.blockingIssueCount),
          evidence_reference: form.evidenceReference,
          observed_at: new Date(form.observedAt).toISOString(),
          expires_at: new Date(form.expiresAt).toISOString(),
        }),
      });
      setPayload(response.readiness);
      setNotice(response.created ? "The review was added to the permanent evidence history." : "That exact review was already saved.");
      setForm((current) => ({
        ...current,
        summary: "",
        evidenceReference: "",
        sessionReference: current.reviewKind === "moderated_session" ? "" : current.sessionReference,
      }));
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "The review could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const isOwner = viewer?.platform_role === "platform_owner";
  const routes = payload?.route_audit?.routes || [];
  const sessions = payload?.moderated_sessions?.sessions || [];

  return (
    <main style={{ maxWidth: 1120, margin: "40px auto", padding: 24 }}>
      <p><Link href="/platform">Back to Platform Home</Link></p>
      <h1>Whole-product experience proof</h1>
      <p>
        <Link href="/platform/readiness">Return to Paid Launch Readiness</Link>
      </p>
      <p style={{ maxWidth: 780, lineHeight: 1.6 }}>
        This board answers two plain questions: has every customer page worked on both desktop and
        mobile, and have at least five non-technical people completed the first-use journey without
        operator rescue? Automated tests do not count as either proof.
      </p>

      {loading ? <p role="status">Loading saved experience reviews...</p> : null}
      {error ? (
        <div role="alert" style={{ border: "1px solid #991b1b", padding: 16 }}>
          <strong>Experience evidence is unavailable.</strong>
          <p>{error}</p>
          <button type="button" onClick={load}>Try again</button>
        </div>
      ) : null}

      {payload ? (
        <>
          <section aria-labelledby="experience-summary" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
            <h2 id="experience-summary" style={{ marginTop: 0 }}>Evidence summary</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
              <div style={{ border: "1px solid #ddd", padding: 14 }}>
                <strong>Customer pages</strong>
                <p style={{ fontSize: 24, margin: "8px 0" }}>
                  {payload.route_audit.counts.passed} of {payload.route_audit.required_route_count}
                </p>
                <span>{payload.route_audit.evidence_state === "ready" ? "Desktop and mobile complete" : "Reviews still needed"}</span>
              </div>
              <div style={{ border: "1px solid #ddd", padding: 14 }}>
                <strong>Non-technical participants</strong>
                <p style={{ fontSize: 24, margin: "8px 0" }}>
                  {payload.moderated_sessions.counts.passed} of {payload.moderated_sessions.counts.required}
                </p>
                <span>{payload.moderated_sessions.evidence_state === "ready" ? "Minimum reached" : `${payload.moderated_sessions.counts.remaining} still needed`}</span>
              </div>
            </div>
          </section>

          <section aria-labelledby="route-matrix" style={{ marginTop: 32 }}>
            <h2 id="route-matrix">Desktop and mobile route matrix</h2>
            <p>
              Each review includes the normal page, loading, empty, error, recovery, and navigation
              behavior. A page is complete only when both viewports pass.
            </p>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #bbb", padding: 10 }}>Customer page</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #bbb", padding: 10 }}>Desktop</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #bbb", padding: 10 }}>Mobile</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #bbb", padding: 10 }}>Overall</th>
                  </tr>
                </thead>
                <tbody>
                  {routes.map((route) => (
                    <tr key={route.code}>
                      <td style={{ borderBottom: "1px solid #eee", padding: 10 }}><strong>{route.label}</strong><br /><small>{route.path}</small></td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{reviewState(route.viewports.desktop.state)}</td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{reviewState(route.viewports.mobile.state)}</td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{reviewState(route.state)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="moderated-sessions" style={{ marginTop: 32 }}>
            <h2 id="moderated-sessions">Moderated first-use sessions</h2>
            <p>
              Participants connect a search account, understand optional analytics, receive a
              baseline, choose a next action, set up a workflow, review billing, and sign out or
              revoke a session. Only opaque aliases are stored here—never names, emails, recordings,
              or links.
            </p>
            {sessions.length ? (
              <ul>
                {sessions.map((session) => (
                  <li key={session.session_reference} style={{ marginTop: 8 }}>
                    <strong>{session.session_reference}</strong> — {reviewState(session.state)} · {session.review.issue_count} issue{session.review.issue_count === 1 ? "" : "s"}
                  </li>
                ))}
              </ul>
            ) : <p role="status">No moderated sessions have been recorded.</p>}
          </section>

          {isOwner ? (
            <section aria-labelledby="record-experience-review" style={{ border: "1px solid #ccc", padding: 20, marginTop: 32 }}>
              <h2 id="record-experience-review" style={{ marginTop: 0 }}>Record a current review</h2>
              <p>
                Use an internal receipt and plain findings. Do not paste links, names, emails,
                supplier names, credentials, recordings, or raw error messages.
              </p>
              <form onSubmit={recordReview} style={{ display: "grid", gap: 14, maxWidth: 760 }}>
                <label>
                  Review type
                  <select value={form.reviewKind} onChange={(event) => setKind(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                    <option value="route_audit">Customer page — desktop or mobile</option>
                    <option value="moderated_session">Non-technical first-use session</option>
                  </select>
                </label>
                {form.reviewKind === "route_audit" ? (
                  <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 14 }}>
                    <label>
                      Customer page
                      <select value={form.subjectCode} onChange={(event) => setForm((current) => ({ ...current, subjectCode: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                        {routes.map((route) => <option key={route.code} value={route.code}>{route.label}</option>)}
                      </select>
                    </label>
                    <label>
                      Viewport
                      <select value={form.viewport} onChange={(event) => setForm((current) => ({ ...current, viewport: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                        <option value="desktop">Desktop</option>
                        <option value="mobile">Mobile</option>
                      </select>
                    </label>
                  </div>
                ) : (
                  <label>
                    Opaque participant alias
                    <input required pattern="[A-Z][A-Z0-9-]{5,39}" value={form.sessionReference} onChange={(event) => setForm((current) => ({ ...current, sessionReference: event.target.value.toUpperCase() }))} placeholder="UX-0001" style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
                  <label>
                    Result
                    <select value={form.result} onChange={(event) => setForm((current) => ({ ...current, result: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                      <option value="passed">Passed</option>
                      <option value="failed">Failed — blocks launch</option>
                    </select>
                  </label>
                  <label>
                    Issues found
                    <input type="number" min="0" max="999" required value={form.issueCount} onChange={(event) => setForm((current) => ({ ...current, issueCount: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                  <label>
                    Blocking issues
                    <input type="number" min="0" max="999" required value={form.blockingIssueCount} onChange={(event) => setForm((current) => ({ ...current, blockingIssueCount: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                </div>
                <label>
                  Plain result summary
                  <textarea required minLength={20} maxLength={400} value={form.summary} onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))} style={{ display: "block", width: "100%", minHeight: 100, marginTop: 6 }} />
                </label>
                <label>
                  Internal evidence reference
                  <input required minLength={8} maxLength={160} value={form.evidenceReference} onChange={(event) => setForm((current) => ({ ...current, evidenceReference: event.target.value }))} placeholder="UX-REVIEW-2026-08-001" style={{ display: "block", width: "100%", marginTop: 6 }} />
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <label>
                    Observed
                    <input type="datetime-local" required value={form.observedAt} onChange={(event) => setForm((current) => ({ ...current, observedAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                  <label>
                    Recheck by
                    <input type="datetime-local" required value={form.expiresAt} onChange={(event) => setForm((current) => ({ ...current, expiresAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                </div>
                <button type="submit" disabled={busy} style={{ width: "fit-content" }}>{busy ? "Saving review..." : "Save permanent review"}</button>
              </form>
              {notice ? <p role="status" style={{ color: "#166534" }}>{notice}</p> : null}
              {formError ? <p role="alert" style={{ color: "#991b1b" }}>{formError}</p> : null}
            </section>
          ) : <p>Platform administrators can review evidence. A platform owner must record reviews.</p>}

          <section aria-labelledby="experience-limitations" style={{ marginTop: 32 }}>
            <h2 id="experience-limitations">What this evidence does not do</h2>
            <ul>{payload.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        </>
      ) : null}
    </main>
  );
}
