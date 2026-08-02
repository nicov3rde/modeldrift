# Model Drift

Tracking how AI answer engines describe SaaS brands across buying-intent queries.

## What this is

When someone asks an AI assistant "what's the best tool for X," the answer names a
handful of brands and describes them. That answer isn't a ranking — a brand is
either named or it isn't, and what gets said about it is either accurate or it
isn't. This project measures both, systematically, across five engines.

**Engines:** ChatGPT, Claude, Gemini, Perplexity, Google AI Overviews

**What gets measured:**
- **Presence** — which brands get named, how often, and which never appear
- **Accuracy** — whether descriptions, pricing, and positioning are correct
- **Sourcing** — which pages the engines cite, and where errors originate

## Method

20 buyer-intent questions about electrical contractor software (the first
category), asked against all five engines, 5 repetitions per question in a
fresh session each time. The question set is frozen and versioned so that
later runs are directly comparable to the first. Full detail, including every
question, lives at [modeldrift.tech/methodology](https://modeldrift.tech/methodology).

Question groups:
- Problem-aware — the buyer hasn't named the category yet
- Category-aware — actively evaluating
- Capability-specific — questions matching a real product's exact strengths
- Comparison and decision — e.g. "ServiceTitan alternatives"

Plus a brand-direct loop ("what is Acme," "is Acme good for electrical
contractors") run separately against every tracked company.

Every result row records the engine, model version, date, and retrieval setting,
so that changes over time can be attributed rather than guessed at.

## Runs

| Run | Date | Status |
|-----|------|--------|
| 1 | August 2026 | planned |
| 2 | October 2026 | planned |
| 3 | December 2026 | planned |

Three runs across five months produce longitudinal data on how AI
recommendations shift within a single category.

## Status

Site skeleton live at [modeldrift.tech](https://modeldrift.tech). First run:
August 12, 2026. First essay: September 6, 2026.

## Stack

Astro (static output) on Vercel · JSON-LD structured data. Data collection
tooling is separate from this site.

## Site development

```
npm install
npm run dev       # http://localhost:4321
npm run build     # outputs to dist/
```

`node scripts/generate-images.mjs` regenerates `public/favicon.ico` and
`public/og-default.png` from the SVG templates in that script.

---

Built by Nicholas Crowell.
