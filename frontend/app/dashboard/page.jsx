"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [campaignDomain, setCampaignDomain] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [crawlType, setCrawlType] = useState("deep");
  const [clusterName, setClusterName] = useState("Core Terms");
  const [keyword, setKeyword] = useState("local seo agency");
  const [locationCode, setLocationCode] = useState("US");
  const [monthNumber, setMonthNumber] = useState("1");
  const [recipientEmail, setRecipientEmail] = useState("admin@local.dev");
  const [busyAction, setBusyAction] = useState("");
  const [latestRuns, setLatestRuns] = useState([]);
  const [latestTrends, setLatestTrends] = useState([]);
  const [latestReports, setLatestReports] = useState([]);

  function withScheme(domain) {
    if (!domain) return "";
    if (domain.startsWith("http://") || domain.startsWith("https://")) {
      return domain;
    }
    return `https://${domain}`;
  }

  async function api(path, options = {}) {
    async function runRequest(token) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);
      try {
        return await fetch(`${API_BASE}${path}`, {
          ...options,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...(options.headers || {})
          }
        });
      } catch (err) {
        if (err?.name === "AbortError") {
          throw new Error("Request timed out. Please try again.");
        }
        throw err;
      } finally {
        clearTimeout(timeout);
      }
    }

    let token = localStorage.getItem("access_token");
    if (!token) {
      throw new Error("No token found. Login first.");
    }
    let response = await runRequest(token);

    if (response.status === 401) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("tenant_id");
        throw new Error("Session expired. Please log in again.");
      }
      const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken })
      });
      const refreshJson = await refreshResponse.json().catch(() => ({}));
      if (!refreshResponse.ok || !refreshJson?.data?.access_token) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_id");
        throw new Error("Session expired. Please log in again.");
      }
      localStorage.setItem("access_token", refreshJson.data.access_token);
      token = refreshJson.data.access_token;
      response = await runRequest(token);
    }

    let json = {};
    try {
      json = await response.json();
    } catch {
      json = {};
    }
    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("tenant_id");
        router.push("/login");
      }
      throw new Error(json?.error?.message || `Request failed (${response.status})`);
    }
    return json.data;
  }

  async function loadCampaigns() {
    const data = await api("/campaigns");
    const items = data?.items || [];
    setCampaigns(items);
    if (!selectedCampaignId && items.length > 0) {
      setSelectedCampaignId(items[0].id);
      setSeedUrl(withScheme(items[0].domain));
    }
    return items;
  }

  async function loadLatest(campaignId) {
    if (!campaignId) return;
    const runsData = await api(`/crawl/runs?campaign_id=${encodeURIComponent(campaignId)}`);
    const trendsData = await api(`/rank/trends?campaign_id=${encodeURIComponent(campaignId)}`);
    const reportsData = await api(`/reports?campaign_id=${encodeURIComponent(campaignId)}`);
    setLatestRuns(runsData?.items || []);
    setLatestTrends(trendsData?.items || []);
    setLatestReports(reportsData?.items || []);
  }

  useEffect(() => {
    async function loadMe() {
      setLoading(true);
      setError("");
      try {
        const user = await api("/auth/me", { method: "GET" });
        setMe(user);
        const items = await loadCampaigns();
        if (items.length > 0) {
          await loadLatest(items[0].id);
        }
      } catch (err) {
        setError(err.message || "Session invalid");
      } finally {
        setLoading(false);
      }
    }
    loadMe();
  }, []);

  useEffect(() => {
    const selected = campaigns.find((item) => item.id === selectedCampaignId);
    if (selected && !seedUrl) {
      setSeedUrl(withScheme(selected.domain));
    }
  }, [selectedCampaignId, campaigns, seedUrl]);

  async function runAction(label, fn) {
    setBusyAction(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (err) {
      setError(err.message || "Action failed");
    } finally {
      setBusyAction("");
    }
  }

  async function createCampaign(event) {
    event.preventDefault();
    if (!campaignName.trim() || !campaignDomain.trim()) {
      setError("Campaign name and domain are required.");
      return;
    }
    await runAction("createCampaign", async () => {
      const created = await api("/campaigns", {
        method: "POST",
        body: JSON.stringify({ name: campaignName.trim(), domain: campaignDomain.trim() })
      });
      await loadCampaigns();
      setSelectedCampaignId(created.id);
      setSeedUrl(withScheme(created.domain));
      setCampaignName("");
      setCampaignDomain("");
      setNotice("Campaign created.");
      await loadLatest(created.id);
    });
  }

  async function scheduleCrawl() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }
    await runAction("crawl", async () => {
      const chosenCampaign = campaigns.find((item) => item.id === selectedCampaignId);
      const effectiveSeedUrl = seedUrl.trim() || withScheme(chosenCampaign?.domain || "");
      if (!effectiveSeedUrl) {
        throw new Error("Seed URL is required for crawl.");
      }
      await api("/crawl/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          crawl_type: crawlType,
          seed_url: effectiveSeedUrl
        })
      });
      setSeedUrl(effectiveSeedUrl);
      setNotice("Crawl scheduled.");
      await loadLatest(selectedCampaignId);
    });
  }

  async function addKeywordAndRunRank() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }
    if (!keyword.trim()) {
      setError("Keyword is required.");
      return;
    }
    await runAction("rank", async () => {
      await api("/rank/keywords", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          cluster_name: clusterName.trim() || "Core Terms",
          keyword: keyword.trim(),
          location_code: locationCode.trim() || "US"
        })
      });
      await api("/rank/schedule", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          location_code: locationCode.trim() || "US"
        })
      });
      setNotice("Rank snapshot scheduled.");
      await loadLatest(selectedCampaignId);
    });
  }

  async function generateReport() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }
    await runAction("report", async () => {
      const parsedMonth = Number.parseInt(monthNumber, 10);
      const safeMonth = Number.isNaN(parsedMonth) ? 1 : Math.min(12, Math.max(1, parsedMonth));
      await api("/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: selectedCampaignId,
          month_number: safeMonth
        })
      });
      setNotice(`Report generated for month ${safeMonth}.`);
      await loadLatest(selectedCampaignId);
    });
  }

  async function deliverLatestReport() {
    if (!selectedCampaignId) {
      setError("Select a campaign first.");
      return;
    }
    if (!recipientEmail.trim()) {
      setError("Recipient email is required.");
      return;
    }
    if (latestReports.length === 0) {
      setError("Generate a report first.");
      return;
    }
    await runAction("deliver", async () => {
      await api(`/reports/${latestReports[0].id}/deliver`, {
        method: "POST",
        body: JSON.stringify({ recipient: recipientEmail.trim() })
      });
      setNotice("Latest report marked as delivered.");
      await loadLatest(selectedCampaignId);
    });
  }

  return (
    <main style={{ maxWidth: 1100, margin: "40px auto", padding: 24, color: "#1b1f23" }}>
      <h1 style={{ marginBottom: 8 }}>Dashboard</h1>
      <p style={{ marginTop: 0, opacity: 0.75 }}>Campaign workflow controls for crawl, rank, and reporting.</p>
      {loading ? <p>Loading session...</p> : null}
      {error ? <p style={{ color: "crimson", marginBottom: 16 }}>{error}</p> : null}
      {notice ? <p style={{ color: "#127a2a", marginBottom: 16 }}>{notice}</p> : null}

      {me ? (
        <section
          style={{
            background: "#ffffff",
            border: "1px solid #d8dee4",
            borderRadius: 10,
            padding: 16,
            marginBottom: 16
          }}
        >
          <strong>Signed in as tenant admin</strong>
          <p style={{ margin: "8px 0 0 0", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 13 }}>
            user_id={me.id} | tenant_id={me.tenant_id}
          </p>
        </section>
      ) : null}

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 16,
          alignItems: "start"
        }}
      >
        <div style={{ background: "#fff", border: "1px solid #d8dee4", borderRadius: 10, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>1) Campaign</h2>
          <form onSubmit={createCampaign}>
            <label>Name</label>
            <input
              value={campaignName}
              onChange={(event) => setCampaignName(event.target.value)}
              style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
            />
            <label>Domain</label>
            <input
              placeholder="example.com"
              value={campaignDomain}
              onChange={(event) => setCampaignDomain(event.target.value)}
              style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
            />
            <button type="submit" disabled={busyAction !== ""}>
              {busyAction === "createCampaign" ? "Creating..." : "Create Campaign"}
            </button>
          </form>
          <hr style={{ margin: "16px 0" }} />
          <label>Active campaign</label>
          <select
            value={selectedCampaignId}
            onChange={async (event) => {
              const nextId = event.target.value;
              setSelectedCampaignId(nextId);
              const selected = campaigns.find((item) => item.id === nextId);
              setSeedUrl(withScheme(selected?.domain || ""));
              await runAction("refresh", async () => {
                await loadLatest(nextId);
              });
            }}
            style={{ display: "block", width: "100%", marginTop: 6, padding: 8 }}
          >
            <option value="">Select campaign</option>
            {campaigns.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.domain})
              </option>
            ))}
          </select>
        </div>

        <div style={{ background: "#fff", border: "1px solid #d8dee4", borderRadius: 10, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>2) Crawl</h2>
          <label>Seed URL</label>
          <input
            value={seedUrl}
            onChange={(event) => setSeedUrl(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <label>Crawl type</label>
          <select
            value={crawlType}
            onChange={(event) => setCrawlType(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          >
            <option value="deep">deep</option>
            <option value="delta">delta</option>
          </select>
          <button onClick={scheduleCrawl} disabled={busyAction !== ""}>
            {busyAction === "crawl" ? "Scheduling..." : "Run Crawl"}
          </button>
        </div>

        <div style={{ background: "#fff", border: "1px solid #d8dee4", borderRadius: 10, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>3) Rank</h2>
          <label>Cluster</label>
          <input
            value={clusterName}
            onChange={(event) => setClusterName(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <label>Keyword</label>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <label>Location code</label>
          <input
            value={locationCode}
            onChange={(event) => setLocationCode(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <button onClick={addKeywordAndRunRank} disabled={busyAction !== ""}>
            {busyAction === "rank" ? "Scheduling..." : "Add Keyword + Run Rank Snapshot"}
          </button>
        </div>

        <div style={{ background: "#fff", border: "1px solid #d8dee4", borderRadius: 10, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>4) Reports</h2>
          <label>Month number (1-12)</label>
          <input
            type="number"
            min="1"
            max="12"
            value={monthNumber}
            onChange={(event) => setMonthNumber(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <button onClick={generateReport} disabled={busyAction !== ""}>
            {busyAction === "report" ? "Generating..." : "Generate Report"}
          </button>
          <hr style={{ margin: "16px 0" }} />
          <label>Recipient email</label>
          <input
            value={recipientEmail}
            onChange={(event) => setRecipientEmail(event.target.value)}
            style={{ display: "block", width: "100%", margin: "6px 0 12px", padding: 8 }}
          />
          <button onClick={deliverLatestReport} disabled={busyAction !== ""}>
            {busyAction === "deliver" ? "Delivering..." : "Deliver Latest Report"}
          </button>
        </div>
      </section>

      <section style={{ marginTop: 20, background: "#fff", border: "1px solid #d8dee4", borderRadius: 10, padding: 16 }}>
        <h2 style={{ marginTop: 0 }}>5) Latest Results</h2>
        <button
          onClick={() =>
            runAction("refresh", async () => {
              await loadLatest(selectedCampaignId);
              setNotice("Latest results refreshed.");
            })
          }
          disabled={busyAction !== "" || !selectedCampaignId}
          style={{ marginBottom: 12 }}
        >
          {busyAction === "refresh" ? "Refreshing..." : "Refresh Latest Results"}
        </button>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 12
          }}
        >
          <div style={{ border: "1px solid #e5e9ef", borderRadius: 8, padding: 12 }}>
            <strong>Crawl Runs</strong>
            <p style={{ margin: "8px 0" }}>Total: {latestRuns.length}</p>
            <p style={{ margin: "8px 0" }}>
              Latest: {latestRuns[0] ? `${latestRuns[0].status} (${latestRuns[0].crawl_type})` : "none"}
            </p>
          </div>
          <div style={{ border: "1px solid #e5e9ef", borderRadius: 8, padding: 12 }}>
            <strong>Rank Trends</strong>
            <p style={{ margin: "8px 0" }}>Keywords tracked: {latestTrends.length}</p>
            <p style={{ margin: "8px 0" }}>
              Top keyword: {latestTrends[0] ? `${latestTrends[0].keyword} (pos ${latestTrends[0].position})` : "none"}
            </p>
          </div>
          <div style={{ border: "1px solid #e5e9ef", borderRadius: 8, padding: 12 }}>
            <strong>Reports</strong>
            <p style={{ margin: "8px 0" }}>Total: {latestReports.length}</p>
            <p style={{ margin: "8px 0" }}>
              Latest: {latestReports[0] ? `Month ${latestReports[0].month_number} (${latestReports[0].report_status})` : "none"}
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
