# CX1 Help Center Contract

Status: CX1 customer education and support implemented locally
Route: `/help`  
Language version: `service-business-natural-voice-v3`

## Purpose

The Help Center lets a service-business owner find the next useful step without
leaving InsightOS, understanding specialist search terminology, or contacting
an operator for routine questions.

It is task help, not a chatbot. Search results come from reviewed product guides
and definitions. The page does not invent advice, inspect customer data, run a
paid check, or change a website or Google listing.

## Customer workflow

1. Search for the task, problem, or number shown on the current screen.
2. Choose whether the workspace covers one business, several locations, or
   team/agency work.
3. Open a matching guide and follow its numbered steps.
4. Use the guide's direct link to return to the correct product page.
5. If no guide resolves the issue, send the safe support details listed on the
   page.

## Content requirements

- Use the same customer wording as the product interface.
- Lead with actions and observable results.
- Keep source mechanics and internal system terms out of primary help copy.
- Never promise rankings, calls, leads, revenue, savings, or a guaranteed
  support resolution.
- Explain missing information instead of treating it as zero.
- Give every guide one product destination and an ordered checklist.
- Keep multi-location numbers separate and explicitly state when a portfolio
  view compares rather than combines locations.

## Search behavior

- Search is local to the reviewed guide and glossary catalog.
- It matches the visible title, summary, numbered steps, and familiar alternate
  terms such as `heatmap`, `keyword`, `impressions`, and `not updating`.
- Workspace type filters guides, not definitions.
- An empty result gives a clear reset action and the safe support fallback.

## Support safety

The customer is asked for only:

1. business and location name;
2. the page where the problem happened;
3. the task they were trying to finish; and
4. the exact on-screen message.

The page explicitly tells the customer never to send a password, sign-in code,
payment number, API key, or private access key. It saves a durable,
tenant-scoped request and keeps email as a fallback. Customers explicitly
choose whether to attach a safe
system summary and whether support may inspect the selected location for 72
hours. The summary is restricted to identifiers, setup state, connection
status/timestamps/error codes, and latest scan/report status. Passwords,
tokens, credentials, page content, review text, prompts, payment information,
and provider payloads are prohibited. Customers receive a reference number,
response expectation, visible status, and an explicit priority-review path.
Platform support receives a filterable queue so requests can be found by
organization or status and handled against their response target.

## Quick product tours

- The Help Center can start a four-step tour for a one-business owner,
  multi-location manager, or team/agency operator.
- A successful first setup starts the same tour once. Customers can close it,
  resume it across pages, or restart it from the Help Center.
- The tour is a small non-modal guide. It does not block the page or leave a
  permanent message behind after the customer finishes or closes it.
- Tour state contains only the persona, step number, completion state, and
  timestamps. It is tenant-scoped in browser storage and expires after 90 days.
- Governed events measure started, viewed-step, and completed states using only
  the persona and step number. No search terms, page content, or contact data
  are recorded.

## Acceptance checks

- A customer can find setup, result-reading, action, and recovery guides.
- `heatmap` finds the Local Search map guide and definition.
- `not updating` finds connection recovery guidance.
- One-business customers do not see the multi-location management guide until
  they choose a multi-location or team workspace.
- Search result counts update for assistive technology.
- Every expandable guide can be used with a keyboard.
- Desktop and mobile layouts preserve readable order and direct actions.
