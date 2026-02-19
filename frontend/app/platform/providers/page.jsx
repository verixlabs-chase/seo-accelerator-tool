"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { platformApi } from "../api";

export default function PlatformProvidersPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await platformApi("/platform/provider-health/summary");
      setItems(data?.items || []);
    } catch (err) {
      setError(err.message || "Failed to load provider health.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main style={{ maxWidth: 1200, margin: "40px auto", padding: 24 }}>
      <h1>Provider Global Health</h1>
      <p>
        <Link href="/platform">Back to Platform Home</Link>
      </p>
      {loading ? <p>Loading...</p> : null}
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Organization</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Provider</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Capability</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Breaker</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Failures</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Remaining Quota</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row, idx) => (
            <tr key={`${row.organization_id}-${row.provider_name}-${row.capability}-${idx}`}>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.organization_name || row.organization_id}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.provider_name}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.capability}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.breaker_state}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.consecutive_failures}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.remaining_quota ?? "-"}</td>
            </tr>
          ))}
          {items.length === 0 && !loading ? (
            <tr>
              <td colSpan={6} style={{ padding: 8 }}>
                No provider health rows found.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </main>
  );
}
