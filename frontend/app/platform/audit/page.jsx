"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { platformApi } from "../api";

export default function PlatformAuditPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await platformApi("/platform/audit");
      setItems(data?.items || []);
    } catch (err) {
      setError(err.message || "Failed to load audit log.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main style={{ maxWidth: 1200, margin: "40px auto", padding: 24 }}>
      <h1>Platform Audit Log</h1>
      <p>
        <Link href="/platform">Back to Platform Home</Link>
      </p>
      {loading ? <p>Loading...</p> : null}
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Created At</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Event</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Tenant</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Actor</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Payload</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.id}>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.created_at}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.event_type}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.tenant_id}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.actor_user_id || "-"}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8, fontFamily: "monospace", fontSize: 12 }}>
                {JSON.stringify(row.payload)}
              </td>
            </tr>
          ))}
          {items.length === 0 && !loading ? (
            <tr>
              <td colSpan={5} style={{ padding: 8 }}>
                No audit events found.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </main>
  );
}
