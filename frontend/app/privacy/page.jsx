import Link from "next/link";

export const metadata = {
  title: "Privacy Policy | InsightOS",
  description: "How InsightOS collects, uses, protects, and deletes customer data."
};

const UPDATED_ON = "August 5, 2026";

export default function PrivacyPolicyPage() {
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
          Privacy Policy
        </h1>
        <p className="mt-3 text-sm text-zinc-400">Last updated {UPDATED_ON}</p>

        <div className="mt-10 space-y-10 text-[15px] leading-7 text-zinc-300">
          <section>
            <h2 className="text-xl font-semibold text-white">What this policy covers</h2>
            <p className="mt-3">
              InsightOS is a local-search performance platform operated by Top Dog Digital
              Solutions. This policy explains the information we collect when a business uses
              InsightOS, why we use it, and the choices available to the business.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Information we collect</h2>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Account details, such as name, email address, organization, and login activity.</li>
              <li>Business and location information supplied by a customer or found on its public website.</li>
              <li>
                Google Search Console data a customer authorizes, including search appearances,
                website visits from search, average position, pages, and search queries.
              </li>
              <li>
                Google Business Profile data a customer authorizes, including listing details,
                reviews, and profile performance information.
              </li>
              <li>Product usage, diagnostic, security, and billing records needed to operate the service.</li>
            </ul>
            <p className="mt-3">
              InsightOS does not receive or store a customer&apos;s Google password.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">How we use information</h2>
            <ul className="mt-3 list-disc space-y-2 pl-6">
              <li>Connect authorized data sources and keep each business location separate.</li>
              <li>Display performance, trends, reviews, and other customer-requested reports.</li>
              <li>Create prioritized recommendations and measure whether completed work helped.</li>
              <li>Protect accounts, troubleshoot failures, prevent abuse, and improve reliability.</li>
              <li>Provide support and important service notices.</li>
            </ul>
            <p className="mt-3">
              We do not sell Google user data, use it for advertising, or use it to train a
              general-purpose artificial intelligence model.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Google API data</h2>
            <p className="mt-3">
              InsightOS&apos;s use and transfer of information received from Google APIs adheres to
              the Google API Services User Data Policy, including its Limited Use requirements.
              Customers choose which Google account to connect and may revoke access at any time
              from their Google Account permissions or from InsightOS.
            </p>
            <a
              className="mt-3 inline-block text-orange-400 hover:text-orange-300"
              href="https://developers.google.com/terms/api-services-user-data-policy"
              rel="noreferrer"
              target="_blank"
            >
              Google API Services User Data Policy ↗
            </a>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Sharing and service providers</h2>
            <p className="mt-3">
              We share information only with providers needed to run InsightOS, such as hosting,
              database, authentication, monitoring, payment, and approved data-integration
              services. They may process information only to provide those services. We may also
              disclose information when legally required or to protect customers and the service.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Retention, deletion, and security</h2>
            <p className="mt-3">
              We keep information only while it is needed to provide the service, meet legal
              obligations, resolve disputes, or protect the platform. Customers may disconnect a
              Google integration without deleting their Google data at the source. To request
              deletion of an InsightOS account and its stored customer data, contact us at the
              address below. We use access controls, tenant separation, encryption in transit,
              and operational safeguards designed to protect stored information.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white">Contact us</h2>
            <p className="mt-3">
              Questions, access requests, or deletion requests can be sent to{" "}
              <a
                className="text-orange-400 hover:text-orange-300"
                href="mailto:chase@topdogdigitalsolutions.com"
              >
                chase@topdogdigitalsolutions.com
              </a>
              .
            </p>
          </section>
        </div>
      </article>
    </main>
  );
}
