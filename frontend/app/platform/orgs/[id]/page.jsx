"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { platformApi } from "../../api";

const PLAN_OPTIONS = ["internal_anchor", "standard", "enterprise"];
const BILLING_OPTIONS = ["platform_sponsored", "subscription", "custom_contract"];
const STATUS_OPTIONS = ["active", "suspended", "archived"];
const CREDENTIAL_MODE_OPTIONS = ["platform", "byo_optional", "byo_required"];

export default function PlatformOrgDetailPage({ params }) {
  const { id } = params;
  const [organization, setOrganization] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [planType, setPlanType] = useState("standard");
  const [billingMode, setBillingMode] = useState("subscription");
  const [status, setStatus] = useState("active");
  const [providerName, setProviderName] = useState("dataforseo");
  const [credentialMode, setCredentialMode] = useState("byo_optional");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await platformApi(`/platform/orgs/${id}`);
      const org = data.organization;
      setOrganization(org);
      setPolicies(data.provider_policies || []);
      setPlanType(org.plan_type);
      setBillingMode(org.billing_mode);
      setStatus(org.status);
    } catch (err) {
      setError(err.message || "Failed to load organization.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function patch(path, body) {
    setError("");
    setNotice("");
    try {
      const data = await platformApi(path, {
        method: "PATCH",
        body: JSON.stringify(body)
      });
      setOrganization(data.organization);
      setPlanType(data.organization.plan_type);
      setBillingMode(data.organization.billing_mode);
      setStatus(data.organization.status);
      setNotice("Saved.");
    } catch (err) {
      setError(err.message || "Save failed.");
    }
  }

  async function saveProviderPolicy(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await platformApi(`/platform/organizations/${id}/provider-policies/${encodeURIComponent(providerName)}`, {
        method: "PUT",
        body: JSON.stringify({ credential_mode: credentialMode })
      });
      await load();
      setNotice("Provider policy updated.");
    } catch (err) {
      setError(err.message || "Provider policy update failed.");
    }
  }

  return (
    <main style={{ maxWidth: 1100, margin: "40px auto", padding: 24 }}>
      <h1>Organization Detail</h1>
      <p>
        <Link href="/platform/orgs">Back to Organizations</Link>
      </p>
      {loading ? <p>Loading...</p> : null}
      {error ? <p style={{ color: "crimson" }}>{error}</p> : null}
      {notice ? <p style={{ color: "green" }}>{notice}</p> : null}

      {organization ? (
        <>
          <section style={{ border: "1px solid #ddd", padding: 16, marginBottom: 16 }}>
            <p>
              <strong>ID:</strong> {organization.id}
            </p>
            <p>
              <strong>Name:</strong> {organization.name}
            </p>
            <p>
              <strong>Created:</strong> {organization.created_at || "-"}
            </p>
          </section>

          <section style={{ border: "1px solid #ddd", padding: 16, marginBottom: 16 }}>
            <h2>Plan and Billing</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12 }}>
              <div>
                <label>Plan</label>
                <select value={planType} onChange={(event) => setPlanType(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                  {PLAN_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <button onClick={() => patch(`/platform/orgs/${id}/plan`, { plan_type: planType })} style={{ marginTop: 8 }}>
                  Save Plan
                </button>
              </div>
              <div>
                <label>Billing</label>
                <select value={billingMode} onChange={(event) => setBillingMode(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                  {BILLING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <button onClick={() => patch(`/platform/orgs/${id}/billing`, { billing_mode: billingMode })} style={{ marginTop: 8 }}>
                  Save Billing
                </button>
              </div>
              <div>
                <label>Status</label>
                <select value={status} onChange={(event) => setStatus(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <button onClick={() => patch(`/platform/orgs/${id}/status`, { status })} style={{ marginTop: 8 }}>
                  Save Status
                </button>
              </div>
            </div>
          </section>

          <section style={{ border: "1px solid #ddd", padding: 16, marginBottom: 16 }}>
            <h2>Provider Policy Editor</h2>
            <form onSubmit={saveProviderPolicy}>
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr auto", gap: 12, alignItems: "end" }}>
                <div>
                  <label>Provider Name</label>
                  <input value={providerName} onChange={(event) => setProviderName(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }} />
                </div>
                <div>
                  <label>Credential Mode</label>
                  <select value={credentialMode} onChange={(event) => setCredentialMode(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                    {CREDENTIAL_MODE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
                <button type="submit">Save Policy</button>
              </div>
            </form>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Provider</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Credential Mode</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Updated</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((row) => (
                  <tr key={row.provider_name}>
                    <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.provider_name}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.credential_mode}</td>
                    <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.updated_at || "-"}</td>
                  </tr>
                ))}
                {policies.length === 0 ? (
                  <tr>
                    <td colSpan={3} style={{ padding: 8 }}>
                      No provider policies configured.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}
