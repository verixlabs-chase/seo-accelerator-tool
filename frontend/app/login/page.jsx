"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@local.dev");
  const [password, setPassword] = useState("admin123!");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const json = await res.json();
    if (!res.ok) {
      setError(json?.error?.message || "Login failed");
      return;
    }
    localStorage.setItem("access_token", json.data.access_token);
    localStorage.setItem("tenant_id", json.data.user.tenant_id);
    router.push("/dashboard");
  }

  return (
    <main style={{ maxWidth: 540, margin: "80px auto", padding: 24, background: "#fff", borderRadius: 8 }}>
      <h1>Tenant Login</h1>
      <form onSubmit={submit}>
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 12 }} />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 12 }} />
        <button type="submit">Login</button>
      </form>
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
    </main>
  );
}
