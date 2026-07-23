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

A fixed set of ~150 queries in one SaaS category, run against all five engines
and logged with citations. The query set is frozen and versioned so that later
runs are directly comparable to the first.

Query types:
- Category queries — "best X for Y" (tests presence)
- Brand-direct — "what is Acme" (tests accuracy)
- Comparison — "Acme vs Beta" (tests framing)

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

Setup. Category selection in progress. Findings publish at
[modeldrift.tech](https://modeldrift.tech).

## Stack

Python · static site on Vercel · JSON-LD structured data

---

Built by Nicholas Crowell.
