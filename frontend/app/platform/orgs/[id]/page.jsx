"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { platformApi } from "../../api";

const PLAN_OPTIONS = [
  { value: "solo", label: "Solo · $299/month" },
  { value: "multi_location", label: "Multi-location · $699/month" },
  { value: "enterprise", label: "Enterprise · starts at $1,999/month" },
  { value: "internal_anchor", label: "Internal anchor (legacy)" },
  { value: "standard", label: "Standard / Solo (legacy)" },
  { value: "pro", label: "Pro / Multi-location (legacy)" },
];
const BILLING_OPTIONS = ["platform_sponsored", "subscription", "custom_contract"];
const STATUS_OPTIONS = ["active", "suspended", "archived"];
const CREDENTIAL_MODE_OPTIONS = ["platform", "byo_optional", "byo_required"];
const DATA_SOURCE_OPTIONS = [
  { value: "search_market_data", label: "Search market data" },
];

export default function PlatformOrgDetailPage({ params }) {
  const { id } = params;
  const [organization, setOrganization] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [planType, setPlanType] = useState("standard");
  const [billingMode, setBillingMode] = useState("subscription");
  const [status, setStatus] = useState("active");
  const [dataSource, setDataSource] = useState("search_market_data");
  const [credentialMode, setCredentialMode] = useState("byo_optional");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [margin, setMargin] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [data, marginData] = await Promise.all([
        platformApi(`/platform/orgs/${id}`),
        platformApi(`/platform/orgs/${id}/margin`),
      ]);
      const org = data.organization;
      setOrganization(org);
      setPolicies(data.provider_policies || []);
      setPlanType(org.plan_type);
      setBillingMode(org.billing_mode);
      setStatus(org.status);
      setMargin(marginData);
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
      await platformApi(`/platform/organizations/${id}/data-source-policies/${encodeURIComponent(dataSource)}`, {
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
                    <option key={option.value} value={option.value}>
                      {option.label}
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

          {margin ? (
            <section style={{ border: "1px solid #ddd", padding: 16, marginBottom: 16 }}>
              <h2>Margin Guardrail</h2>
              <p>
                Internal only. Customer screens show allowance and recovery choices, not margin.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
                <div><strong>Revenue</strong><br />${margin.revenue.toFixed(2)}</div>
                <div><strong>Paid API cost</strong><br />${margin.platform_api_cost.toFixed(2)}</div>
                <div><strong>Total COGS</strong><br />${margin.total_cogs.toFixed(2)}</div>
                <div><strong>Gross margin</strong><br />{margin.gross_margin_percent.toFixed(1)}%</div>
              </div>
              <p style={{ marginTop: 12 }}>
                Outstanding API reservations: ${margin.reserved_platform_api_cost.toFixed(2)} ·
                Non-API allocation: {margin.allocation_status === "configured" ? `v${margin.allocation_version}` : "not configured"}
              </p>
              <p>
                Hosting ${margin.costs.hosting.toFixed(2)} · Storage ${margin.costs.storage.toFixed(2)} ·
                Email ${margin.costs.email.toFixed(2)} · Support ${margin.costs.support.toFixed(2)} ·
                Other ${margin.costs.other.toFixed(2)}
              </p>
              <p>
                Heavy-use test: {margin.modeled_heavy_use.gross_margin_percent.toFixed(1)}% ·
                {margin.modeled_heavy_use.publishable ? " publishable" : " blocked"}
              </p>
            </section>
          ) : null}

          <section style={{ border: "1px solid #ddd", padding: 16, marginBottom: 16 }}>
            <h2>Provider Policy Editor</h2>
            <form onSubmit={saveProviderPolicy}>
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr auto", gap: 12, alignItems: "end" }}>
                <div>
                  <label>Data Source</label>
                  <select value={dataSource} onChange={(event) => setDataSource(event.target.value)} style={{ display: "block", width: "100%", marginTop: 6 }}>
                    {DATA_SOURCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
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
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Data Source</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Credential Mode</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ccc", padding: 8 }}>Updated</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((row) => (
                  <tr key={row.provider_name}>
                    <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{row.data_source_name || "Configured data source"}</td>
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
