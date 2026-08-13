# UX13 Service-Business Voice Contract

Status: coded route audit implemented locally; owner comprehension testing remains
Version: `service-business-natural-voice-v3`

## The reader

Write for a capable, busy owner or manager of a local service business. They
know their customers, crews, jobs, service areas, and reputation. They should
not need search-industry or software terminology to understand the product.

Never describe the reader as non-technical, less tech-savvy, confused, or in
need of simplified treatment.

## What every screen must answer

After five seconds, the owner should be able to answer:

1. What is this page for?
2. What should I do next?

If either answer is unclear, fix the headline, supporting sentence, or first
action. Do not add another explanatory card to compensate.

## Voice rules

- Lead with the business outcome or action.
- Use concrete verbs and familiar words.
- Keep one idea in each sentence.
- Explain missing information honestly; never display missing data as zero.
- Keep source, methodology, and specialist terms behind optional detail.
- Keep internal paid-data supplier names out of every customer page, report,
  generated message, and error. Describe the result or use `search data service`.
- Sound like a knowledgeable advisor when read aloud.
- Do not announce that copy is simple, easy, plain English, or AI-written.
- Do not promise rankings, customers, calls, leads, or revenue.

## Avoid

The shared browser and generated-copy contracts reject language such as:

- `unlock`, `leverage`, `seamless`, and `actionable insights`;
- `AI-powered`, `explained in plain English`, and `without digging through SEO tooling`;
- `non-technical owner` and `less tech-savvy`;
- internal system labels and unexplained search-industry terms.

## Reviewed examples

| Avoid | Use |
| --- | --- |
| Local search visibility explained in plain English. | Know how your business is showing up on Google. |
| Unlock actionable insights for each location. | See which locations need attention and why. |
| Leverage AI-powered recommendations. | Start with the action most likely to help. |
| Our seamless workflow simplifies SEO. | See what changed and what to work on next. |
| Sign in to review visibility changes and report delivery status. | Sign in to see what changed on Google, what needs attention, and what to work on next. |
| Review local demand and supporting data. | Compare estimated monthly searches and open why a search is listed when you need more detail. |

## Shared enforcement

- Browser copy uses `customerLanguage.mjs` and the
  `service-business-natural-voice-v3` version.
- Generated guidance uses the same versioned guide through
  `plain_language.py`.
- Contract tests cover prohibited wording and the public home/sign-in promise.
- API error messages and customer-facing source identifiers are sanitized before
  they can reach a page.
- Every product introduction is checked for a visible purpose, supporting
  outcome, title and summary length, and prohibited self-conscious wording.
- Reports apply the same contract to saved headlines, summaries, readiness
  messages, source labels, portfolio notes, next actions, steps, browser
  previews, and downloaded files. Older saved wording is sanitized when shown;
  the frozen measurements do not change.
- Next Steps keeps the issue, reason, and first action visible. Supporting
  information, source, status, and timing sit under optional detail so they do
  not compete with the checklist.
- There is no shipped customer notification center yet. ALT1 owns alerts and
  digests and must use this contract when that surface is built.
- The coded route audit is complete. Representative service-business owners
  must still pass the five-second and read-aloud checks before UX13 is complete.
- Keyword Research now uses customer-purpose labels such as `estimated monthly
  searches`, `where you appear`, and `why this search is listed`. Local Search
  identifies the map as a location reference and says when a ranking check has
  not been run instead of showing a misleading zero.
