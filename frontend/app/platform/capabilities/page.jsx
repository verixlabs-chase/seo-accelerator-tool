"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { platformApi } from "../api";

const STATE_LABELS = {
  proven: "Production proven",
  limited: "Available with a limitation",
  unavailable: "Not currently available",
  stale: "Proof expired",
  needs_live_proof: "Needs production proof",
};

const STATE_COLORS = {
  proven: "#166534",
  limited: "#854d0e",
  unavailable: "#991b1b",
  stale: "#854d0e",
  needs_live_proof: "#1e40af",
};

function localDateTime(daysFromNow = 0) {
  const value = new Date(Date.now() + daysFromNow * 24 * 60 * 60 * 1000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

export default function ProductionCapabilitiesPage() {
  const [matrix, setMatrix] = useState(null);
  const [viewer, setViewer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [form, setForm] = useState({
    capabilityCode: "",
    result: "proven",
    summary: "",
    customerLimitation: "",
    evidenceReference: "",
    observedAt: localDateTime(),
    expiresAt: localDateTime(30),
  });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [currentMatrix, currentViewer] = await Promise.all([
        platformApi("/system/production-capabilities", { method: "GET" }),
        platformApi("/auth/me", { method: "GET" }),
      ]);
      setMatrix(currentMatrix);
      setViewer(currentViewer);
      setForm((current) => ({
        ...current,
        capabilityCode: current.capabilityCode || currentMatrix.capabilities?.[0]?.code || "",
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The capability matrix could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function recordProof(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await platformApi("/system/production-capabilities/proofs", {
        method: "POST",
        body: JSON.stringify({
          capability_code: form.capabilityCode,
          result: form.result,
          summary: form.summary,
          customer_limitation: form.result === "proven" ? null : form.customerLimitation,
          evidence_reference: form.evidenceReference,
          observed_at: new Date(form.observedAt).toISOString(),
          expires_at: new Date(form.expiresAt).toISOString(),
        }),
      });
      setMatrix(response.matrix);
      setNotice(response.created ? "The capability proof was added to permanent history." : "That exact proof was already saved.");
      setForm((current) => ({
        ...current,
        summary: "",
        customerLimitation: "",
        evidenceReference: "",
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The capability proof could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const visibleCapabilities = useMemo(
    () => (matrix?.capabilities || []).filter((item) => filter === "all" || item.claim_state === filter),
    [filter, matrix],
  );
  const isOwner = viewer?.platform_role === "platform_owner";

  return (
    <main style={{ maxWidth: 1120, margin: "40px auto", padding: 24 }}>
      <p><Link href="/platform/readiness">Back to Paid Launch Readiness</Link></p>
      <h1>Production Capabilities and Limitations</h1>
      <p style={{ maxWidth: 780, lineHeight: 1.6 }}>
        This is the source of truth for launch claims. Plan inclusion shows what a customer may buy;
        current production proof shows what sales, demos, Help, and support may describe as available.
      </p>

      {loading ? <p role="status">Checking current capability proof...</p> : null}
      {error ? <p role="alert" style={{ color: "#991b1b" }}>{error}</p> : null}
      {notice ? <p role="status" style={{ color: "#166534" }}>{notice}</p> : null}

      {matrix ? (
        <>
          <section aria-labelledby="capability-summary" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
            <h2 id="capability-summary" style={{ marginTop: 0 }}>
              Evidence: {matrix.evidence_state === "ready" ? "complete for review" : "incomplete"}
            </h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              {Object.entries(STATE_LABELS).map(([state, label]) => (
                <button
                  key={state}
                  type="button"
                  onClick={() => setFilter(filter === state ? "all" : state)}
                  style={{ minWidth: 150, border: filter === state ? "2px solid #333" : "1px solid #ddd", padding: 12, textAlign: "left", background: "transparent" }}
                >
                  <span style={{ color: STATE_COLORS[state], fontWeight: 700 }}>{label}</span>
                  <span style={{ display: "block", fontSize: 28 }}>{matrix.counts[state] ?? 0}</span>
                </button>
              ))}
            </div>
            <p style={{ marginBottom: 0 }}>
              A complete matrix may contain limited or unavailable capabilities. It is complete only
              when every limitation is current and explicit.
            </p>
          </section>

          {isOwner ? (
            <section aria-labelledby="record-capability-proof" style={{ border: "1px solid #ccc", padding: 20, marginTop: 24 }}>
              <h2 id="record-capability-proof" style={{ marginTop: 0 }}>Record current production proof</h2>
              <p>
                Use an internal receipt code. Do not paste a URL, supplier name, credential, raw
                response, or customer information.
              </p>
              <form onSubmit={recordProof} style={{ display: "grid", gap: 14, maxWidth: 760 }}>
                <label>
                  Capability
                  <select value={form.capabilityCode} onChange={(event) => setForm((current) => ({ ...current, capabilityCode: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                    {matrix.capabilities.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                  </select>
                </label>
                <label>
                  Current result
                  <select value={form.result} onChange={(event) => setForm((current) => ({ ...current, result: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }}>
                    <option value="proven">Production proven</option>
                    <option value="limited">Available with a customer limitation</option>
                    <option value="unavailable">Not currently available</option>
                  </select>
                </label>
                <label>
                  Internal result summary
                  <textarea required minLength={20} maxLength={300} value={form.summary} onChange={(event) => setForm((current) => ({ ...current, summary: event.target.value }))} placeholder="What production journey was checked and what happened?" style={{ display: "block", width: "100%", minHeight: 90, marginTop: 6 }} />
                </label>
                {form.result !== "proven" ? (
                  <label>
                    Exact customer limitation
                    <textarea required minLength={20} maxLength={300} value={form.customerLimitation} onChange={(event) => setForm((current) => ({ ...current, customerLimitation: event.target.value }))} placeholder="What must pricing, demos, Help, and support tell the customer?" style={{ display: "block", width: "100%", minHeight: 90, marginTop: 6 }} />
                  </label>
                ) : null}
                <label>
                  Internal evidence reference
                  <input required minLength={8} maxLength={160} value={form.evidenceReference} onChange={(event) => setForm((current) => ({ ...current, evidenceReference: event.target.value }))} placeholder="CAPABILITY-RECEIPT-2026-08" style={{ display: "block", width: "100%", marginTop: 6 }} />
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                  <label>
                    Observed
                    <input type="datetime-local" required value={form.observedAt} onChange={(event) => setForm((current) => ({ ...current, observedAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                  <label>
                    Recheck by
                    <input type="datetime-local" required value={form.expiresAt} onChange={(event) => setForm((current) => ({ ...current, expiresAt: event.target.value }))} style={{ display: "block", width: "100%", marginTop: 6 }} />
                  </label>
                </div>
                <button type="submit" disabled={busy} style={{ width: "fit-content" }}>
                  {busy ? "Saving proof..." : "Add proof to history"}
                </button>
              </form>
            </section>
          ) : <p>Platform administrators can review this matrix. A platform owner must record proof.</p>}

          <section aria-labelledby="capability-list" style={{ marginTop: 32 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
              <h2 id="capability-list">Capability claims</h2>
              {filter !== "all" ? <button type="button" onClick={() => setFilter("all")}>Show all</button> : null}
            </div>
            <div style={{ display: "grid", gap: 14 }}>
              {visibleCapabilities.map((item) => (
                <article key={item.code} style={{ border: "1px solid #ddd", padding: 18 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start" }}>
                    <div>
                      <h3 style={{ margin: 0 }}>{item.label}</h3>
                      <p>{item.summary}</p>
                    </div>
                    <strong style={{ color: STATE_COLORS[item.claim_state], whiteSpace: "nowrap" }}>
                      {STATE_LABELS[item.claim_state]}
                    </strong>
                  </div>
                  <p><strong>Included with:</strong> {item.included_plans.join(", ")} · starts with {item.minimum_plan}</p>
                  {item.proof ? (
                    <div style={{ borderLeft: "3px solid #777", paddingLeft: 12 }}>
                      <p><strong>Latest production result:</strong> {item.proof.summary}</p>
                      {item.proof.customer_limitation ? <p><strong>Required customer limitation:</strong> {item.proof.customer_limitation}</p> : null}
                      <p style={{ marginBottom: 0 }}>
                        {item.proof.evidence_reference} · observed {new Date(item.proof.observed_at).toLocaleString()} · recheck by {new Date(item.proof.expires_at).toLocaleString()}
                      </p>
                    </div>
                  ) : <p>No production receipt has been saved. Do not describe this capability as live.</p>}
                </article>
              ))}
            </div>
          </section>

          <section aria-labelledby="matrix-limitations" style={{ marginTop: 32 }}>
            <h2 id="matrix-limitations">Rules for using this matrix</h2>
            <ul>{matrix.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        </>
      ) : null}
    </main>
  );
}
