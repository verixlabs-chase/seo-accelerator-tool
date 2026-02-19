"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { platformApi } from "../api";

export default function PlatformOrgsPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await platformApi("/platform/orgs");
      setItems(data?.items || []);
    } catch (err) {
      setError(err.message || "Failed to load organizations.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main style={{ maxWidth: 1100, margin: "40px auto", padding: 24 }}>
      <h1>Organizations</h1>
      <p>
        <Link href="/platform">Back to Platform Home</Link>
      </p>
      {loading ? <p>Loading...</p> : null}
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Name</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Plan</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Billing</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Status</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((org) => (
            <tr key={org.id}>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{org.name}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{org.plan_type}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{org.billing_mode}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{org.status}</td>
              <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                <Link href={`/platform/orgs/${org.id}`}>Open</Link>
              </td>
            </tr>
          ))}
          {items.length === 0 && !loading ? (
            <tr>
              <td colSpan={5} style={{ padding: 8 }}>
                No organizations found.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </main>
  );
}
