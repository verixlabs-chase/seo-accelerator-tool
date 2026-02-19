import Link from "next/link";

export default function PlatformHomePage() {
  return (
    <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
      <h1>Platform Owner Control Center</h1>
      <p>Governance-only surface. No SEO execution controls on this namespace.</p>
      <ul>
        <li>
          <Link href="/platform/orgs">Organizations</Link>
        </li>
        <li>
          <Link href="/platform/providers">Provider Health</Link>
        </li>
        <li>
          <Link href="/platform/audit">Audit Log</Link>
        </li>
      </ul>
    </main>
  );
}
