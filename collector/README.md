# ModelDrift collector

Drives a real browser against ChatGPT, Claude, Gemini, Perplexity, and Google
AI Overviews, fires the frozen question set, and saves raw HTML + a
screenshot per response. Interpretation (which brands got named, which URLs
got cited) happens later, offline, in `extract.py`, never while the browser
is open. See `collect_v0.py`'s module docstring for the full design rationale.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Copy `run_config.template.json` to `run_config.json` and fill in
`location_setting`. The runner doesn't refuse to run if it's left `null`, but
every row will record `location_setting: null`, and the spec is explicit
that this can't stay implicit, or it'll bite you in the December re-run.

`run_config.json` is gitignored (so is `browser_profile/`, `raw/`, `.gcp/`):
it's the local, possibly-machine-specific file the runner actually reads.
`run_config.template.json` is the committed, shareable shape.

## First run: log in by hand

ChatGPT and Claude use a persistent profile (`browser_profile/chatgpt`,
`browser_profile/claude`) so you don't have to sign in every session; each
*repetition* still gets a fresh conversation via each platform's own
temporary/incognito-chat mode, not a full logout. Gemini, Perplexity, and
Google AI Overviews use a fresh throwaway profile every single call (fully
logged out), Gemini specifically because Google's bot detection blocks a
persisted automated login from surviving at all, confirmed empirically.

The first time you run against `chatgpt` or `claude`, a real browser window
opens and waits (up to 5 minutes) for you to log in by hand. After that,
cookies persist in `browser_profile/` and you won't be prompted again unless
the session expires.

## Running it

```
python collect_v0.py --dry-run          # 105 calls: 21 questions x 5 engines x 1 rep
python extract.py aug2026_dry            # turns raw captures into data/runs/aug2026_dry.jsonl
python export.py aug2026_dry             # data/exports/aug2026_dry_flat.csv + _presence.csv
```

Review the dry run before touching the real one: read a few raw responses,
check how many rows came back with zero `cited_urls` per engine (expected to
be high for engines that don't cite consistently; the methodology says so),
and check nothing looks truncated or malformed.

Then the real run:

```
python collect_v0.py                     # 825 calls: the full frozen set
python extract.py aug2026
python export.py aug2026
```

**Resumable.** Every capture writes `raw/<date>/<engine>__<question_id>__r<n>.html`
+ `.png`. Killing the process and re-running the same command skips anything
already on disk (`status: success` or `no_answer`, both are real data) and
only retries what's missing or previously `failed`. `--max-calls N` caps how
many *new* calls a single invocation will make (default: `run_config.json`'s
`max_calls_per_invocation`). It stops cleanly and tells you to re-run to
pick up where it left off, rather than trying to do all 825 in one sitting.

**Failure isolation.** One engine being down, or one capture crashing, never
aborts the run. It's logged as `status: failed` with the error, and the
loop moves on.

## Files

| File | Purpose |
|---|---|
| `collect_v0.py` | The runner. `ENGINE_CONFIGS` holds every engine-specific selector, validated against real DOM via paired retrieval probes; see its comments before touching one. |
| `browser_common.py` | Shared CDP-call timeout/retry helpers (Windows console encoding fix, hung-connection handling). |
| `questions.py` | Loads `../data/question-set.v1.json`, the single frozen source, also read by the Astro site's methodology/companies pages. |
| `stability.py` | Fires one query N times against one engine to measure run-to-run noise, a permanent instrument, not a one-off; see its docstring. |
| `extract.py` | Offline: raw HTML to schema'd JSONL (`data/runs/<run_id>.jsonl`) per the measurement spec's Part 3 fields. Citation extraction is best-effort per engine; spot-check before trusting counts, see the file's docstring. |
| `export.py` | JSONL to `data/exports/<run_id>_flat.csv` and `_presence.csv`. Presence counting is a literal company-name substring match, no alias table; that's later, real analysis. |

## Known gaps

- `extract.py`'s per-engine citation-URL extraction hasn't been validated
  URL-by-URL yet, only marker-presence has (via the retrieval probes). Spot
  check a sample against saved screenshots before publishing citation counts.
- No spend cap exists because there's no per-call API cost (this drives real
  browser sessions against free-tier consumer accounts, not paid APIs). The
  safety limit instead is `max_calls_per_invocation`.
