# CX1 Help Center Contract

Status: first customer-help slice implemented locally  
Route: `/help`  
Language version: `service-business-plain-language-v2`

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
payment number, or private access key. The current slice opens the customer's
email application; it does not send automatically or collect a diagnostic
bundle. Consented diagnostic bundles and tracked escalation states remain a
later CX1 slice.

## Acceptance checks

- A customer can find setup, result-reading, action, and recovery guides.
- `heatmap` finds the Local Search map guide and definition.
- `not updating` finds connection recovery guidance.
- One-business customers do not see the multi-location management guide until
  they choose a multi-location or team workspace.
- Search result counts update for assistive technology.
- Every expandable guide can be used with a keyboard.
- Desktop and mobile layouts preserve readable order and direct actions.
