"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { platformApi } from "../api";

const cardStyle = {
  border: "1px solid #d7d9df",
  borderRadius: 10,
  padding: 18,
  background: "#fff",
};

function formatPlan(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function MetricCard({ label, value, detail }) {
  return (
    <div style={cardStyle}>
      <p style={{ margin: 0, color: "#61646d", fontSize: 13 }}>{label}</p>
      <p style={{ margin: "8px 0 4px", fontSize: 30, fontWeight: 700 }}>{value}</p>
      <p style={{ margin: 0, color: "#61646d", fontSize: 13 }}>{detail}</p>
    </div>
  );
}

export default function PlatformValuePage() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await platformApi(`/platform/product-value/summary?days=${days}`);
        if (active) setSummary(data);
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load customer value metrics.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [days]);

  const funnel = summary?.funnel || {};
  const averageHours = funnel.average_hours_to_first_value;

  return (
    <main style={{ maxWidth: 1240, margin: "40px auto", padding: 24, color: "#17181b" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 20, alignItems: "end" }}>
        <div>
          <p style={{ margin: 0 }}><Link href="/platform">Back to Platform Home</Link></p>
          <h1 style={{ marginBottom: 8 }}>Activation &amp; Customer Value</h1>
          <p style={{ margin: 0, color: "#61646d" }}>
            Aggregate product evidence only. Synthetic activity, page content, searches, and provider payloads are excluded.
          </p>
        </div>
        <label style={{ display: "grid", gap: 6, fontSize: 13 }}>
          Measurement window
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #bbb" }}
          >
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
          </select>
        </label>
      </div>

      {loading ? <p>Loading measurement...</p> : null}
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}

      {summary ? (
        <>
          <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 14, marginTop: 28 }}>
            <MetricCard label="Completed setup" value={`${funnel.activation_rate || 0}%`} detail={`${funnel.activated || 0} organizations`} />
            <MetricCard label="Reached first value" value={`${funnel.first_value_rate || 0}%`} detail={`${funnel.first_value || 0} organizations`} />
            <MetricCard label="Completed an action" value={`${funnel.action_completion_rate || 0}%`} detail={`${funnel.action_completed || 0} organizations`} />
            <MetricCard label="Returned for more value" value={`${funnel.repeated_value_rate || 0}%`} detail={`${funnel.repeated_value || 0} organizations`} />
            <MetricCard label="Time to first value" value={averageHours == null ? "Not enough data" : `${averageHours} hrs`} detail={`${funnel.time_to_first_value_samples || 0} measured journeys`} />
            <MetricCard label="May need help" value={funnel.needs_attention || 0} detail="Reached value, but no useful activity in 14 days" />
          </section>

          <section style={{ ...cardStyle, marginTop: 22 }}>
            <h2 style={{ marginTop: 0 }}>Funnel by plan</h2>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {["Plan", "Eligible", "Setup", "First value", "Action done", "Repeated value"].map((label) => (
                    <th key={label} style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 10 }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(summary.cohorts || []).map((cohort) => (
                  <tr key={cohort.plan_type}>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{formatPlan(cohort.plan_type)}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{cohort.eligible_organizations}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{cohort.activated}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{cohort.first_value}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{cohort.action_completed}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 10 }}>{cohort.repeated_value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 18, marginTop: 22 }}>
            <section style={cardStyle}>
              <h2 style={{ marginTop: 0 }}>Customer feedback</h2>
              {(summary.feedback || []).length ? (
                <ul style={{ paddingLeft: 20 }}>
                  {summary.feedback.map((item) => (
                    <li key={item.context} style={{ marginBottom: 12 }}>
                      <strong>{formatPlan(item.context)}</strong>: {item.average_rating}/5 from {item.responses} response{item.responses === 1 ? "" : "s"} ({item.positive_rate}% positive)
                    </li>
                  ))}
                </ul>
              ) : <p>No structured feedback in this period yet.</p>}
            </section>

            <section style={cardStyle}>
              <h2 style={{ marginTop: 0 }}>Instrumentation coverage</h2>
              <p style={{ color: "#61646d" }}>
                {summary.instrumentation.active_events} of {summary.instrumentation.registered_events} governed events are wired into the product.
              </p>
              <ul style={{ paddingLeft: 20 }}>
                {summary.instrumentation.coverage.map((item) => (
                  <li key={item.event_name} style={{ marginBottom: 8 }}>
                    <code>{item.event_name}</code> — {item.coverage_state.replaceAll("_", " ")} ({item.events_in_period})
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      ) : null}
    </main>
  );
}
