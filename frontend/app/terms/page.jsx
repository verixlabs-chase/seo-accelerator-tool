import Link from "next/link";

export const metadata = {
  title: "Terms of Service | InsightOS",
  description: "Terms governing access to and use of InsightOS."
};

const UPDATED_ON = "August 10, 2026";

export default function TermsOfServicePage() {
  return (
    <main className="min-h-screen bg-[#0b0b0c] px-6 py-14 text-zinc-100">
      <article className="mx-auto max-w-3xl">
        <Link className="text-sm text-orange-400 hover:text-orange-300" href="/">
          ← InsightOS
        </Link>
        <p className="mt-10 text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">
          Legal
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white">
          Terms of Service
        </h1>
        <p className="mt-3 text-sm text-zinc-400">Last updated {UPDATED_ON}</p>

        <div className="mt-10 space-y-10 text-[15px] leading-7 text-zinc-300">
          <section>
            <h2 className="text-xl font-semibold text-white">Agreement</h2>
            <p className="mt-3">
              These terms govern access to InsightOS, a local-search performance platform
              operated by VerixLabs. By creating an account or using the service, you agree to
              these terms on behalf of yourself and the organization you represent.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Accounts and authorization</h2>
            <p className="mt-3">
              You must provide accurate account information and protect access to your account.
              You may connect only websites, business profiles, and third-party accounts that you
              own or are authorized to manage. You remain responsible for the people you invite
              and the actions they take within your organization.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Connected services</h2>
            <p className="mt-3">
              InsightOS may connect to Google and other third-party services at your direction.
              Those services remain governed by their own terms and availability. You control
              whether an integration stays connected and may revoke access at any time. InsightOS
              will not make an external profile or website change unless the product clearly
              presents that action and an authorized user approves it.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Acceptable use</h2>
            <p className="mt-3">You may not use InsightOS to:</p>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Access data or accounts without permission.</li>
              <li>Mislead customers, manipulate reviews, send spam, or violate platform policies.</li>
              <li>Probe, disrupt, reverse engineer, or bypass security and usage limits.</li>
              <li>Upload unlawful content or infringe another person&apos;s rights.</li>
              <li>Resell or sublicense the service unless a written plan or agreement allows it.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Recommendations and results</h2>
            <p className="mt-3">
              InsightOS provides measurements, forecasts, and recommendations to support business
              decisions. Search engines and customer behavior are outside our control, so we do
              not guarantee rankings, traffic, leads, revenue, or any specific result. Forecasts
              are estimates, not promises.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Fees and suspension</h2>
            <p className="mt-3">
              Paid plans, usage allowances, renewal terms, and taxes are shown when you subscribe
              or in a separate order. We may suspend access for overdue payment, security risk,
              unlawful use, or a material violation of these terms. We will use reasonable efforts
              to provide notice when the circumstances allow.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Ownership and customer data</h2>
            <p className="mt-3">
              You retain ownership of the information and content you provide. You grant us the
              limited right to process that information only as needed to operate, secure, and
              support InsightOS. InsightOS, its software, design, and documentation remain the
              property of VerixLabs and its licensors.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Service availability and liability</h2>
            <p className="mt-3">
              The service is provided on an “as available” basis to the extent permitted by law.
              We are not responsible for outages or changes caused by third-party platforms. To
              the extent permitted by law, VerixLabs will not be liable for
              indirect, incidental, special, consequential, or lost-profit damages arising from
              use of the service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Changes and contact</h2>
            <p className="mt-3">
              We may update these terms as InsightOS changes. Material changes will be posted here
              with a revised date. Questions may be sent to{" "}
              <a
                className="text-orange-400 hover:text-orange-300"
                href="mailto:support@verixlabs.com"
              >
                support@verixlabs.com
              </a>
              .
            </p>
          </section>
        </div>
      </article>
    </main>
  );
}
