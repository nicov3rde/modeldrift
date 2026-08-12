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

## First run: log in by hand (Claude only)

Four of the five engines run fully logged out with a fresh throwaway profile
every single call: ChatGPT (confirmed 2026-08-11: chatgpt.com's Temporary
Chat mode gives a real, usable composer with no account at all), Gemini
(Google's bot detection blocks a persisted automated login from surviving,
confirmed empirically), Perplexity, and Google AI Overviews. Nothing to log
into, nothing to clear, by construction.

Claude has no anonymous or guest mode at all, so it's the one exception: a
persistent profile (`browser_profile/claude`) holds a real account login so
you don't have to sign in every session, and each *repetition* still gets a
fresh conversation via Claude's own temporary-chat mode, not a full logout.
Before your first real run, log in, then in Settings turn off memory and
personalization and clear any existing memories, since Claude retains those
server-side on the account regardless of which browser profile connects to
it.

**Runs headed (a visible browser window) by default, on purpose.** Tried
headless on 2026-08-11: chatgpt.com served a real Cloudflare "Verifying..."
bot-check page in headless mode that never appeared headed (screenshot
confirmed: composer present headed, absent headless). That's a genuine
anti-automation checkpoint, and this project isn't going to try to defeat it
with stealth/fingerprint-spoofing patches - so a visible window is the
accepted cost, not a bug. A `--headless` flag exists if you want to try it
for a specific engine anyway, but treat it as experimental per-engine, not a
default worth relying on.

For the claude login, just run normally - a real browser window opens and
waits (up to 5 minutes) for you to log in by hand:

```
python collect_v0.py --dry-run --max-calls 1   # opens a window, gets claude logged in
```

That's enough: it'll also open (and do nothing useful with) windows for
chatgpt/gemini/etc, since they don't need login, but the claude login step
is what matters, and cookies persist in `browser_profile/claude` after.
From then on claude reuses the saved cookies with no re-login prompt.

## Getting the windows out of your way (Windows only)

Since headed is mandatory, `_desktop_watcher.ps1` keeps the collector's
windows off your actual desktop without hiding them from the OS (hiding
would mean headless, which is the thing that gets blocked). It uses the
community `VirtualDesktop` PowerShell module to create a "ModelDrift"
virtual desktop, then polls for Chrome processes carrying
`--remote-debugging-port=` (a flag only Playwright/browser_use sets - never
present on a normal user-launched Chrome) and relocates each one there the
instant its window exists, before it's even navigated anywhere. Confirmed
2026-08-11 that composers still mount fine on a window relocated before
page load - it's not a page-visibility/throttling problem.

```powershell
Install-Module VirtualDesktop -Scope CurrentUser -Force   # one-time; needs NuGet
                                                            # provider bootstrapped first if this errors:
                                                            # Install-PackageProvider NuGet -Force -Scope CurrentUser
Import-Module VirtualDesktop
$d = New-Desktop
Set-DesktopName -Desktop $d -Name "ModelDrift"
powershell -NoProfile -ExecutionPolicy Bypass -File .\_desktop_watcher.ps1   # run in the background, leave it running
```

Then run the collector normally in another terminal. Your own desktop stays
clear the whole time; switch to "ModelDrift" (Task View, or Win+Ctrl+Right/
Left) whenever you want to check on it.

## Or: run it in Docker instead

`Dockerfile` runs Chrome headed (no `--headless` flag) against a virtual X
display (Xvfb) inside the container, same trick as the virtual-desktop
approach above, just fully out of sight rather than parked on another
desktop. Confirmed working 2026-08-12.

**Important: build and run this from a path that is NOT inside a
OneDrive/Dropbox/cloud-synced folder.** Confirmed 2026-08-12 that OneDrive's
Files-On-Demand reparse points break Docker Desktop's WSL2 build-context
reader outright (`invalid file request <file>`), and are suspected of
contributing to a folder-wipe incident under heavy Chrome-profile file
churn. This repo now lives at `C:\Users\nverde\dev\modeldrift` for exactly
this reason - clone here, not back into OneDrive.

```
docker compose build
docker compose run --rm collector python collect_v0.py --dry-run --max-calls 1
```

Volumes keep `browser_profile/`, `raw/`, and `data/runs` + `data/exports`
on the host at the same paths the non-Docker instructions already use, so
nothing else changes.

**Claude still needs its own login inside the container specifically** -
Windows Chrome's cookies are DPAPI-encrypted and won't decrypt on Linux, so
the `browser_profile/claude` you logged into on the host doesn't carry over.
Until that's set up (would need VNC or similar to see the container's
virtual display for a one-time login), the practical split is: run
chatgpt/gemini/perplexity/ai_overview in Docker (all logged-out, zero setup),
keep claude on the host with the virtual-desktop trick above.

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
- Headless mode is blocked by Cloudflare on at least chatgpt.com (confirmed
  2026-08-11). A real run currently means a visible browser window for its
  full duration; there's no headless fix planned that doesn't involve
  stealth/fingerprint patches this project isn't going to add.
