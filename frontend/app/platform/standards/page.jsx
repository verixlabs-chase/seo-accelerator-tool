"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { platformApi } from "../api";

const panel = {
  border: "1px solid #29303a",
  borderRadius: 12,
  background: "#12161c",
  padding: 18,
};

const button = {
  border: "1px solid #5b6472",
  borderRadius: 8,
  background: "#202733",
  color: "#f7f7f7",
  cursor: "pointer",
  padding: "9px 13px",
};

const dangerButton = { ...button, borderColor: "#9b3f3f", background: "#351c20" };
const input = {
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid #3a424e",
  borderRadius: 8,
  background: "#0c0f13",
  color: "#f7f7f7",
  padding: 10,
};

function formatDate(value) {
  if (!value) return "Not yet";
  return new Date(value).toLocaleString();
}

function latestDecision(approvals, reportId) {
  return approvals.find((item) => item.replay_report_id === reportId);
}

function rolloutFor(rollouts, approvalId) {
  return rollouts.find((item) => item.approval_id === approvalId);
}

export default function StandardsWorkspacePage() {
  const [data, setData] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [rationale, setRationale] = useState("");
  const [acknowledgeBaseline, setAcknowledgeBaseline] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [rollbackReason, setRollbackReason] = useState("");
  const [driftReviewNote, setDriftReviewNote] = useState("");
  const [driftPeriodDays, setDriftPeriodDays] = useState(14);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await platformApi("/reference-library/standards/status"));
    } catch (err) {
      setError(err.message || "Standards workspace could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const waitingReports = useMemo(() => {
    if (!data) return [];
    return data.replays.filter((report) => !latestDecision(data.approvals, report.id));
  }, [data]);

  async function viewReplay(reportId) {
    setError("");
    try {
      setSelectedReport(
        await platformApi(`/reference-library/standards/replays/${reportId}`)
      );
    } catch (err) {
      setError(err.message || "Replay details could not be loaded.");
    }
  }

  async function decide(report, decision) {
    if (!rationale.trim()) {
      setError("Add the owner decision reason before approving or rejecting.");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    const isApproved = decision === "approved";
    const artifact = report.artifact_type === "provider_metric_contract" ? "measurement rule" : "SEO rule library";
    try {
      await platformApi(`/reference-library/standards/replays/${report.id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          rationale: rationale.trim(),
          rollout_plan: isApproved
            ? {
                summary: `Activate the reviewed ${artifact} and monitor collection health.`,
                steps: ["Activate the candidate version", "Check affected measurements", "Confirm customer results remain trustworthy"],
                monitoring_window_hours: 24,
              }
            : null,
          rollback_plan: isApproved
            ? {
                summary: `Restore the previous ${artifact} if monitoring finds a problem.`,
                steps: ["Restore the previous version", "Reopen the standards change", "Run replay again before another rollout"],
                monitoring_window_hours: 24,
              }
            : null,
          acknowledges_new_baseline: acknowledgeBaseline,
        }),
      });
      setNotice(decision === "approved" ? "Replay approved. It is ready for a controlled rollout." : "Replay rejected. Nothing was activated.");
      setRationale("");
      setAcknowledgeBaseline(false);
      await load();
    } catch (err) {
      setError(err.message || "The owner decision could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  async function createRollout(approval, scheduled) {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const payload = scheduled
        ? { rollout_mode: "scheduled", scheduled_for: new Date(scheduleAt).toISOString() }
        : { rollout_mode: "immediate" };
      const result = await platformApi(
        `/reference-library/standards/approvals/${approval.id}/rollouts`,
        { method: "POST", body: JSON.stringify(payload) }
      );
      setNotice(
        result.status === "completed"
          ? "The approved version is active and being monitored."
          : `Rollout scheduled for ${formatDate(result.scheduled_for)}.`
      );
      await load();
    } catch (err) {
      setError(err.message || "The rollout could not be created.");
    } finally {
      setWorking(false);
    }
  }

  async function executeRollout(rollout) {
    setWorking(true);
    setError("");
    try {
      await platformApi(`/reference-library/standards/rollouts/${rollout.id}/execute`, {
        method: "POST",
      });
      setNotice("The scheduled version is now active.");
      await load();
    } catch (err) {
      setError(err.message || "The rollout could not be executed.");
    } finally {
      setWorking(false);
    }
  }

  async function rollback(rollout) {
    if (!rollbackReason.trim()) {
      setError("Add a rollback reason first.");
      return;
    }
    setWorking(true);
    setError("");
    try {
      await platformApi(`/reference-library/standards/rollouts/${rollout.id}/rollback`, {
        method: "POST",
        body: JSON.stringify({ reason: rollbackReason.trim() }),
      });
      setRollbackReason("");
      setNotice("The previous version has been restored and the change was reopened.");
      await load();
    } catch (err) {
      setError(err.message || "The previous version could not be restored.");
    } finally {
      setWorking(false);
    }
  }

  async function runDriftCheck() {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const result = await platformApi("/reference-library/standards/drift/check", {
        method: "POST",
        body: JSON.stringify({
          metrics: ["clicks", "impressions", "avg_position"],
          period_days: Number(driftPeriodDays),
          minimum_organizations: 5,
        }),
      });
      const created = result.events?.length || 0;
      setNotice(
        result.status === "confounded"
          ? "Shared movement was not evaluated because a known incident or measurement change overlaps the period."
          : created
            ? `${created} shared-movement signal${created === 1 ? "" : "s"} saved for owner review.`
            : "The check found no broad movement that meets the governed minimum sample and confidence rules."
      );
      await load();
    } catch (err) {
      setError(err.message || "The shared-movement check could not be completed.");
    } finally {
      setWorking(false);
    }
  }

  async function reviewDrift(event, status) {
    if (!driftReviewNote.trim()) {
      setError("Add an investigation note before changing this review status.");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await platformApi(`/reference-library/standards/drift/events/${event.id}/review`, {
        method: "POST",
        body: JSON.stringify({ status, note: driftReviewNote.trim() }),
      });
      setDriftReviewNote("");
      setNotice("The shared-movement review was saved. No standard or customer action was changed.");
      await load();
    } catch (err) {
      setError(err.message || "The shared-movement review could not be saved.");
    } finally {
      setWorking(false);
    }
  }

  const summary = data?.summary || {};
  const cards = [
    ["Official sources healthy", summary.healthy_sources ?? 0],
    ["Sources needing attention", summary.sources_needing_attention ?? 0],
    ["Changes needing review", summary.changes_needing_review ?? 0],
    ["Replays awaiting decision", summary.replays_waiting_for_decision ?? 0],
    ["Scheduled rollouts", summary.scheduled_rollouts ?? 0],
    ["Shared movement to review", summary.performance_drift_events_needing_review ?? 0],
  ];

  return (
    <main style={{ maxWidth: 1440, margin: "32px auto", padding: 24, color: "#f7f7f7" }}>
      <p><Link href="/platform">← Platform home</Link></p>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 20, alignItems: "start" }}>
        <div>
          <div style={{ color: "#9ca6b5", fontSize: 12, letterSpacing: 2 }}>PLATFORM GOVERNANCE</div>
          <h1 style={{ marginBottom: 8 }}>Standards &amp; Measurement</h1>
          <p style={{ color: "#b7bfca", maxWidth: 760 }}>
            Review official search changes, see exactly what they would affect, and activate a new version only after an owner approves the replay and rollback plan.
          </p>
        </div>
        <button style={button} onClick={load} disabled={loading || working}>Refresh workspace</button>
      </div>

      {loading ? <p>Loading standards evidence…</p> : null}
      {error ? <p style={{ ...panel, borderColor: "#8d3f48", color: "#ffb4bb" }}>{error}</p> : null}
      {notice ? <p style={{ ...panel, borderColor: "#28785d", color: "#9de6c8" }}>{notice}</p> : null}

      {data ? (
        <>
          <section aria-label="Standards status" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, margin: "24px 0" }}>
            {cards.map(([label, value]) => (
              <article key={label} style={panel}>
                <div style={{ color: "#9ca6b5", fontSize: 12 }}>{label}</div>
                <strong style={{ display: "block", fontSize: 28, marginTop: 8 }}>{value}</strong>
              </article>
            ))}
          </section>

          <section style={{ ...panel, marginBottom: 18 }}>
            <h2 style={{ marginTop: 0 }}>Versions in use</h2>
            <p>SEO rule library: <strong>{data.active_versions.lexicon || "Not active"}</strong></p>
            <p>Measurement rules: <strong>{data.active_versions.metric_contract_count}</strong> active across version {data.active_versions.metric_contract_versions.join(", ") || "none"}</p>
            <p style={{ color: "#9ca6b5" }}>Automatic activation is off. AI cannot approve or activate these versions.</p>
          </section>

          <section style={{ ...panel, marginBottom: 18 }}>
            <h2 style={{ marginTop: 0 }}>Official source health</h2>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr><th align="left">Source</th><th align="left">Area</th><th align="left">Last success</th><th align="left">Status</th></tr></thead>
                <tbody>{data.sources.map((source) => (
                  <tr key={source.source_id}>
                    <td style={{ padding: "10px 0", borderBottom: "1px solid #29303a" }}><a href={source.source_uri} target="_blank" rel="noreferrer">{source.display_name}</a></td>
                    <td style={{ borderBottom: "1px solid #29303a" }}>{source.source_scope}</td>
                    <td style={{ borderBottom: "1px solid #29303a" }}>{formatDate(source.last_success_at)}</td>
                    <td style={{ borderBottom: "1px solid #29303a", color: source.last_error_code ? "#ff8d96" : "#83e2bd" }}>{source.last_error_code ? "Needs attention" : source.last_checked_at ? "Healthy" : "First check pending"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section style={{ ...panel, marginBottom: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 16, flexWrap: "wrap" }}>
              <div>
                <h2 style={{ marginTop: 0, marginBottom: 8 }}>Unusual shared movement</h2>
                <p style={{ color: "#b7bfca", maxWidth: 820, marginTop: 0 }}>
                  Compare equal Search Console periods across at least five separate organizations. Known incidents, incomplete dates, new accounts, legacy measurements, and changed definitions are excluded before a signal can be saved.
                </p>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "end" }}>
                <label>Days per period<input style={{ ...input, width: 90, display: "block", marginTop: 5 }} type="number" min="7" max="90" value={driftPeriodDays} onChange={(event) => setDriftPeriodDays(event.target.value)} /></label>
                <button style={button} disabled={working} onClick={runDriftCheck}>Check shared movement</button>
              </div>
            </div>
            <p style={{ color: "#9ca6b5" }}>
              A result can open an investigation only. It cannot prove an algorithm update, activate a standard, or change a customer website or profile.
            </p>
            {(data.performance_drift_events || []).length === 0 ? <p>No governed shared-movement signals have been saved.</p> : null}
            {(data.performance_drift_events || []).map((event) => (
              <article key={event.id} style={{ borderTop: "1px solid #29303a", padding: "14px 0" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <strong>{event.status === "needs_review" ? "Needs owner review" : event.status}</strong>
                  <span style={{ color: "#9ca6b5" }}>{event.baseline_start}–{event.comparison_end} · {event.organization_count} organizations</span>
                </div>
                <p>{event.plain_language_summary}</p>
                <p style={{ color: "#9ca6b5" }}>
                  Same-direction agreement: {Math.round(event.agreement_ratio * 100)}% · Contract {event.metric_contract_id} {event.metric_contract_version} · {event.excluded_sample_size} samples excluded
                </p>
                {event.investigation_note ? <p style={{ color: "#b7bfca" }}><strong>Latest owner note:</strong> {event.investigation_note}</p> : null}
                <textarea style={{ ...input, maxWidth: 860 }} rows={2} value={driftReviewNote} onChange={(change) => setDriftReviewNote(change.target.value)} placeholder="Record what was checked before changing the review status" />
                <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  <button style={button} disabled={working} onClick={() => reviewDrift(event, "investigating")}>Start investigation</button>
                  <button style={button} disabled={working} onClick={() => reviewDrift(event, "resolved")}>Mark reviewed</button>
                  <button style={dangerButton} disabled={working} onClick={() => reviewDrift(event, "dismissed")}>Dismiss with evidence</button>
                </div>
              </article>
            ))}
          </section>

          <section style={{ ...panel, marginBottom: 18 }}>
            <h2 style={{ marginTop: 0 }}>Replay evidence awaiting an owner</h2>
            <p style={{ color: "#b7bfca" }}>Open a replay to inspect its exact definition change, affected decisions, and fixed test results.</p>
            {waitingReports.length === 0 ? <p>No replay reports are waiting for a decision.</p> : null}
            <div style={{ display: "grid", gap: 10 }}>
              {waitingReports.map((report) => (
                <article key={report.id} style={{ borderTop: "1px solid #29303a", paddingTop: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div><strong>{report.artifact_key}</strong><div style={{ color: "#9ca6b5" }}>{report.base_version} → {report.candidate_version} · {report.changed_results} changed test results</div></div>
                    <button style={button} onClick={() => viewReplay(report.id)}>Inspect exact replay</button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          {selectedReport ? (
            <section style={{ ...panel, marginBottom: 18, borderColor: "#6d58a8" }}>
              <h2 style={{ marginTop: 0 }}>Owner decision: {selectedReport.artifact_key}</h2>
              <p><strong>{selectedReport.base_version} → {selectedReport.candidate_version}</strong> · {selectedReport.total_cases} replay cases · {selectedReport.invalidated_comparisons} comparisons need a new boundary</p>
              <details open><summary>Exact definition difference</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "#c7d0dc" }}>{JSON.stringify(selectedReport.definition_diff, null, 2)}</pre></details>
              <details><summary>What decisions could change</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "#c7d0dc" }}>{JSON.stringify(selectedReport.impact_report, null, 2)}</pre></details>
              <details><summary>Fixed replay results</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "#c7d0dc" }}>{JSON.stringify(selectedReport.replay_results, null, 2)}</pre></details>
              <label style={{ display: "block", margin: "14px 0 6px" }}>Owner decision reason</label>
              <textarea style={input} rows={3} value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Why is this safe to activate or why should it be rejected?" />
              {selectedReport.requires_new_baseline ? (
                <label style={{ display: "block", marginTop: 12 }}><input type="checkbox" checked={acknowledgeBaseline} onChange={(event) => setAcknowledgeBaseline(event.target.checked)} /> I understand that historical before/after comparisons must start a new baseline.</label>
              ) : null}
              <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                <button style={button} disabled={working} onClick={() => decide(selectedReport, "approved")}>Approve replay</button>
                <button style={dangerButton} disabled={working} onClick={() => decide(selectedReport, "rejected")}>Reject replay</button>
              </div>
            </section>
          ) : null}

          <section style={{ ...panel, marginBottom: 18 }}>
            <h2 style={{ marginTop: 0 }}>Approved versions ready to roll out</h2>
            <label style={{ display: "block", marginBottom: 6 }}>Optional scheduled time</label>
            <input style={{ ...input, maxWidth: 360, marginBottom: 14 }} type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
            {data.approvals.filter((item) => item.decision === "approved" && !rolloutFor(data.rollouts, item.id)).map((approval) => (
              <article key={approval.id} style={{ borderTop: "1px solid #29303a", padding: "12px 0" }}>
                <strong>{approval.artifact_key} {approval.base_version} → {approval.candidate_version}</strong>
                <p style={{ color: "#b7bfca" }}>{approval.rationale}</p>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button style={button} disabled={working} onClick={() => createRollout(approval, false)}>Roll out now</button>
                  <button style={button} disabled={working || !scheduleAt} onClick={() => createRollout(approval, true)}>Schedule rollout</button>
                </div>
              </article>
            ))}
          </section>

          <section style={{ ...panel, marginBottom: 18 }}>
            <h2 style={{ marginTop: 0 }}>Rollout and rollback history</h2>
            <textarea style={{ ...input, maxWidth: 720 }} rows={2} value={rollbackReason} onChange={(event) => setRollbackReason(event.target.value)} placeholder="Reason required when restoring a previous version" />
            {data.rollouts.map((rollout) => (
              <article key={rollout.id} style={{ borderTop: "1px solid #29303a", padding: "12px 0" }}>
                <strong>{rollout.artifact_key} {rollout.base_version} → {rollout.candidate_version}</strong>
                <div style={{ color: "#b7bfca", margin: "5px 0" }}>{rollout.status} · {formatDate(rollout.scheduled_for)}</div>
                {rollout.failure_message ? <p style={{ color: "#ff8d96" }}>{rollout.failure_message}</p> : null}
                {rollout.status === "scheduled" ? <button style={button} disabled={working} onClick={() => executeRollout(rollout)}>Run scheduled rollout</button> : null}
                {rollout.status === "completed" ? <button style={dangerButton} disabled={working} onClick={() => rollback(rollout)}>Restore previous version</button> : null}
              </article>
            ))}
          </section>

          <section style={panel}>
            <h2 style={{ marginTop: 0 }}>Standards audit history</h2>
            {data.audit_history.map((event) => (
              <div key={event.id} style={{ borderTop: "1px solid #29303a", padding: "10px 0" }}>
                <strong>{event.event_type}</strong> · {formatDate(event.created_at)}<div style={{ color: "#9ca6b5" }}>Actor: {event.actor_user_id || "system"}</div>
              </div>
            ))}
          </section>
        </>
      ) : null}
    </main>
  );
}
