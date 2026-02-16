import Link from "next/link";

export default function HomePage() {
  return (
    <main style={{ maxWidth: 820, margin: "80px auto", padding: 24 }}>
      <h1>LSOS Sprint 1 Scaffold</h1>
      <p>Backend auth and campaign APIs are available under <code>/api/v1</code>.</p>
      <p>
        <Link href="/login">Go to Login</Link>
      </p>
    </main>
  );
}
