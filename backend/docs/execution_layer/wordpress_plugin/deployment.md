# Deployment

## Customer installation

WordPress execution is available only to authenticated tenant administrators on
Growth and Enterprise plans. InsightOS builds the release ZIP from the reviewed
plugin source at request time; it never injects credentials, pairing codes, or
customer data into the archive. Each download is recorded in the audit log.

1. In InsightOS, open Next Steps and choose **Download WordPress plugin**.
2. Keep the downloaded ZIP intact.
3. In WordPress, open **Plugins**, choose **Add Plugin**, then **Upload Plugin**.
4. Upload the ZIP, install it, and activate it.
5. In InsightOS, choose **Create pairing code**.
6. In WordPress, open **Settings**, choose **InsightOS**, enter the code, and connect.
7. In InsightOS, use **Test connection**.

Live execution remains blocked until the signed health response comes from the
same website on plugin version 1.4.0 or later with content-inventory,
exact-change preview, mutation, rollback, and health-check permissions.

The setup screen shows the downloadable version and the first portion of its
SHA-256 checksum. The authenticated download response also carries the full
checksum in `X-InsightOS-Package-SHA256`. The archive always expands to the
`lsos-execution-plugin` directory WordPress expects.

The current downloadable release is 1.5.0. It adds public rendering fallbacks
for approved titles and descriptions so the platform can verify those values
on the live page even when a supported SEO plugin is not active.

Before approving the first live change, choose **Check website changes** in
InsightOS. Confirm the current and proposed values, affected pages, safety
checks, and rollback explanation. Approval is tied to that exact preview and
expires operationally as soon as WordPress reports a different page version.

## Manual and managed installation

For a controlled deployment, copy
`wordpress_execution_plugin/lsos-execution-plugin` into `wp-content/plugins/`
and activate it. The customer pairing flow remains the supported way to create
site credentials.

For managed deployments, `LSOS_PAIRING_ENDPOINT` may override the default
InsightOS pairing URL. Static tokens in `wp-config.php` remain readable for a
legacy transition but are not the customer onboarding path.

The Vercel backend bundle must include `wordpress_execution_plugin/**`. Do not
add that path to `excludeFiles`; the production download endpoint packages
those reviewed source files at runtime.
