"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function DashboardPage() {
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadMe() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        setError("No token found. Login first.");
        return;
      }
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const json = await res.json();
      if (!res.ok) {
        setError("Session invalid");
        return;
      }
      setMe(json.data);
    }
    loadMe();
  }, []);

  return (
    <main style={{ maxWidth: 720, margin: "80px auto", padding: 24 }}>
      <h1>Dashboard</h1>
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
      {me ? (
        <pre style={{ background: "#fff", padding: 12, borderRadius: 8 }}>
          {JSON.stringify(me, null, 2)}
        </pre>
      ) : (
        <p>Loading user context...</p>
      )}
    </main>
  );
}
