"""
ModelDrift collector - v0 skeleton (read this to understand the shape)

The whole design in one sentence:
    Ask ONE frozen question to ONE engine, save the raw answer untouched, and
    record whether the collection worked. Nothing here decides "what the answer
    was" while the browser is open - that happens LATER, offline, against the
    saved files. The agent is allowed to be flaky at *getting* the answer; it is
    never allowed to interpret it.

Where this runs:
    This needs a real browser on a real machine (browser-use + Chromium) with
    network access to the engines. It will NOT run in a sandbox. Take it to
    Claude Code in your repo and have it fill in the one browser-driving function.

Adding a new engine:
    Everything that differs between engines lives in ENGINE_CONFIGS. The
    shared helpers below (_find_composer, _type_and_queue_submit, _click_send,
    _wait_for_response, _detect_retrieval, collect_one, the preflight check)
    all take a config dict and never hardcode a single engine's selectors -
    that's what let Claude get added without forking ChatGPT's logic. A new
    engine needs: an explore pass to find its real selectors (never guess),
    a paired retrieval probe (search-triggering query vs one that won't) to
    find a stable citation/search DOM marker, then one entry in this dict.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import re
import shutil
import time
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

from browser_use import BrowserSession

from browser_common import safe_call, safe_query
import questions as q

# --- 1. THE FROZEN INPUTS -------------------------------------------------
# Loaded from data/question-set.v1.json (see questions.py) - never hardcode
# a query string here. Byte-identical across the Aug/Oct/Dec runs, or the
# longitudinal comparison is void.
MAIN_QUESTIONS = q.MAIN_QUESTIONS              # the 21 frozen questions
BRAND_DIRECT_QUESTIONS = q.BRAND_DIRECT_QUESTIONS  # 2 templates x 10 companies

# No formatting wrapper. The bare query is what a real buyer types - a
# "single comma-separated line" instruction suppresses the model's natural
# reasoning/hedging/citations, which is exactly what accuracy + sourcing
# scoring needs. Extraction works off natural prose (see section 4).

# ENGINE_CONFIGS below is keyed by these same 5 names - "gemini" is recorded
# and reached logged-out (see that config's comment: Google's bot detection
# blocks a persisted login session from surviving, so logged-out is the only
# mode that exists for this engine right now, not a methodology choice).
ENGINES = list(q.ENGINES)                      # ["chatgpt","claude","gemini","perplexity","ai_overview"]
IMPLEMENTED_ENGINES = ENGINES                  # all five now have a working config

RUN_CONFIG_PATH = Path(__file__).resolve().parent / "run_config.json"


def load_run_config():
    """run_config.json is gitignored (may hold a real location string once
    you set one) - run_config.template.json is the committed, shareable
    shape. Copy the template to run_config.json before your first run."""
    if not RUN_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{RUN_CONFIG_PATH} not found. Copy run_config.template.json to "
            "run_config.json (and fill in location_setting) before running."
        )
    with RUN_CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


RUN_DATE = date.today().isoformat()          # one date per session, not per row
RAW_DIR = Path("raw") / RUN_DATE
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Headless by default: chatgpt/gemini/perplexity/ai_overview never need a
# human (no login exists for any of them), and claude only needed one for
# its one-time login - once browser_profile/claude has real cookies on disk,
# a visible window buys nothing. main() flips this to False when --headed is
# passed, for a fresh claude login or debugging a UI change by eye.
HEADLESS = True

# Claude is the ONE engine that persists login cookies in its profile_dir so
# you don't have to sign in every run (claude.ai has no anonymous/guest mode
# at all - confirmed 2026-08-11, it's a hard sign-in wall). Every other
# engine wipes its profile_dir before every single call (fresh_profile:
# True) and is reached fully logged out. For Claude specifically, isolation
# between repetitions comes from a fresh conversation each time, not from
# wiping the profile - so memory and personalization must be turned off and
# cleared by hand in the account before a real run (see collector/README.md).
ENGINE_CONFIGS = {
    "chatgpt": {
        "name": "ChatGPT",
        "profile_dir": Path("browser_profile") / "chatgpt",
        # Confirmed 2026-08-11 (see the screenshot from _probe_anon.py, since
        # deleted): chatgpt.com's Temporary Chat mode gives a fully anonymous
        # session a real, usable composer - no login wall, no account. Logged
        # out here matches gemini/perplexity/ai_overview: no memory, no
        # personalization, nothing to toggle off or clear, by construction
        # rather than by remembering to configure it correctly.
        "fresh_profile": True,
        "url": "https://chatgpt.com/?model=auto&temporary-chat=true",
        "composer_selectors": ["#prompt-textarea", 'div[contenteditable="true"]'],
        "send_button_selector": 'button[data-testid="send-button"]',
        "send_button_aria_contains": None,
        "stop_button_selector": 'button[data-testid="stop-button"]',
        "assistant_message_selector": '[data-message-author-role="assistant"]',
        # Validated via a paired probe: a citation-triggering query left
        # exactly one 'webpage-citation-pill' node; a plain listicle query
        # left zero. A leaked-text marker ("Tools: web") was also seen once
        # but is model-output, not a stable UI component - not used.
        "retrieval_markers": ['data-testid="webpage-citation-pill"'],
        "preflight_query": "What is today's top news headline in the US?",
    },
    "claude": {
        "name": "Claude",
        "profile_dir": Path("browser_profile") / "claude",
        "url": "https://claude.ai/new",
        "composer_selectors": ['div[data-testid="chat-input"]'],  # contenteditable/ProseMirror, not a textarea
        # No stable send-button testid exists - only an aria-label. Query
        # all buttons and filter by aria-label substring instead.
        "send_button_selector": "button",
        "send_button_aria_contains": "send",
        # data-is-streaming flips true->false exactly like ChatGPT's stop
        # button appearing/disappearing - same stable_checks logic reuses.
        "stop_button_selector": 'div[data-is-streaming="true"]',
        "assistant_message_selector": "div[data-is-streaming]",
        # Validated via a paired probe: a news query left an <a class="group/tag">
        # citation pill with a real source href and a "Searched the web" label;
        # a haiku query (guaranteed no search) had neither. Note: Claude
        # searches more readily than ChatGPT - it searched even for the plain
        # "best cold email tools" listicle query. That's real engine behavior,
        # not a detection bug.
        "retrieval_markers": ["group/tag"],
        "preflight_query": "What is today's top news headline in the US?",
    },
    "gemini": {
        "name": "Gemini (logged-out)",
        "profile_dir": Path("browser_profile") / "gemini",
        "url": "https://gemini.google.com/app",
        # Logged-OUT by design, not a workaround. Google's automated-Chrome
        # detection blocks the login session from persisting (confirmed: a
        # sign-in flow that looked complete left zero real auth cookies in
        # the profile - only analytics ones). Logged-out is actually cleaner
        # for this project's purposes: no account, no memory, nothing to
        # clean between runs. fresh_profile=True wipes profile_dir before
        # every single collect_one/preflight call for maximum isolation.
        "fresh_profile": True,
        "composer_selectors": ['div[contenteditable="true"][aria-label="Enter a prompt for Gemini"]'],
        "send_button_selector": "button",
        "send_button_aria_contains": "send",
        "stop_button_selector": 'button[aria-label="Stop response"]',
        "assistant_message_selector": '[class*="response-container-content"]',
        # Validated via a paired probe: a news query left an aria-label
        # reading "View source details for citation from <publisher>..."; a
        # haiku query (guaranteed no search) had none.
        "retrieval_markers": ['aria-label="View source details for citation'],
        "preflight_query": "What is today's top news headline in the US?",
        # The mode picker button exposes the active model, e.g. "Flash-Lite".
        "model_version_regex": r'aria-label="Open mode picker, currently ([^"]+)"',
    },
    "perplexity": {
        "name": "Perplexity",
        "profile_dir": Path("browser_profile") / "perplexity",
        "url": "https://www.perplexity.ai/",
        # Fully usable logged-out (has its own native "Use incognito" toggle
        # for anonymous sessions, but a fresh throwaway profile per call is
        # simpler and consistent with gemini - no login to persist or
        # protect, so nothing gained by keeping the profile around).
        "fresh_profile": True,
        "composer_selectors": ['div[contenteditable="true"]'],
        "send_button_selector": "button",
        "send_button_aria_contains": "submit",
        "stop_button_selector": 'button[aria-label*="Stop response" i]',
        "assistant_message_selector": '[class*="prose"]',
        # Validated via a paired probe: a news query left data-testid=
        # "trusted-citation-check" nodes; a haiku query (guaranteed no
        # search) had none.
        "retrieval_markers": ['data-testid="trusted-citation-check"'],
        "preflight_query": "What is today's top news headline in the US?",
    },
    "ai_overview": {
        "name": "Google AI Overview",
        "profile_dir": Path("browser_profile") / "ai_overview",
        # No chat, no composer - a single search URL per query. See
        # direct_url_mode handling in collect_one().
        "direct_url_mode": True,
        "fresh_profile": True,
        "url_template": "https://www.google.com/search?q={query}",
        "settle_seconds": 4,
        # Google ships an explicit, always-present (hidden when unused)
        # fallback string when no overview fires - a real "no_answer" signal
        # straight from the DOM, not an absence-based guess like the other
        # engines. "Show more AI Overview" only exists when there's real
        # expandable overview content. Both are user-facing copy, not hashed
        # CSS classes (Google's generated classnames are far less stable).
        "no_answer_markers": ["An AI Overview is not available for this search"],
        "answer_present_markers": ['aria-label="Show more AI Overview"'],
        # best-effort: the overview usually renders below sponsored ads, off
        # the initial viewport - scroll it into frame before screenshotting.
        "scroll_into_view_selector": 'div[aria-label="Show more AI Overview"]',
        # An AI Overview IS Google's retrieval-augmented synthesis by
        # definition - no "answered without search" case exists here, unlike
        # a chat engine. retrieval == whether the overview appeared at all.
        "retrieval_markers": ['aria-label="Show more AI Overview"'],
        # Different preflight_query than the other four engines, deliberately.
        # The shared "top news headline" query is real-time/breaking-news
        # content, and Google evidently doesn't wrap that in an AI Overview
        # panel AT ALL - re-probed 2026-08-11 (see _explore_aio.py) and found
        # neither marker present, not even the "not available" fallback,
        # because the panel never mounts for that query type. A paired probe
        # against "what is the capital of France" (evergreen, always
        # overview-eligible historically) confirmed both markers still fire
        # exactly as designed; a nonsense control query correctly showed
        # neither. The markers were never broken - the preflight query choice
        # was wrong for this one engine.
        "preflight_query": "what is the capital of France",
    },
}

CDP_TIMEOUT = 20.0


def slug(query, engine, run_id=None):
    """Deterministic filename so re-runs land in predictable places.

    run_id is opt-in only, for stability checks that deliberately fire the
    same query N times and need to keep each capture (e.g. collect_one(...,
    run_id=i)). Omitted, this is unchanged - production re-runs of the same
    query+engine still overwrite the same file, as designed."""
    h = hashlib.sha1(query.encode()).hexdigest()[:8]
    base = f"{engine}__{h}"
    if run_id is not None:
        base += f"__r{run_id}"
    return base


def slug_for_question(question_id, engine, repetition):
    """Readable filename keyed on the frozen question_id, used by the
    production run_session/extract pipeline. Independent of query text, so
    resumability checks never depend on re-hashing a string."""
    return f"{engine}__{question_id}__r{repetition}"


def _save_raw(query, engine, html, screenshot_b64, run_id=None, capture_id=None):
    base = RAW_DIR / (capture_id if capture_id is not None else slug(query, engine, run_id=run_id))
    base.with_suffix(".html").write_text(html, encoding="utf-8")
    base.with_suffix(".png").write_bytes(base64.b64decode(screenshot_b64))


def _detect_retrieval(html, config):
    """Whether the engine visibly searched the web - a UI marker, not
    content interpretation. Each engine's marker is validated with a paired
    probe (see ENGINE_CONFIGS comments); absence is treated as 'did not
    search'."""
    return any(marker in html for marker in config["retrieval_markers"])


def _extract_model(html, config):
    """Whatever model/version string the UI exposes, e.g. Gemini's mode
    picker showing 'Flash-Lite'. None if the engine has no such marker."""
    pattern = config.get("model_version_regex")
    if not pattern:
        return None
    m = re.search(pattern, html)
    return m.group(1) if m else None


def _prepare_profile_dir(config):
    """Most engines persist login across runs. gemini is deliberately
    logged-out and marks fresh_profile=True - wipe it before every session
    so 'fresh/isolated' is enforced by construction, not by convention."""
    profile_dir = config["profile_dir"]
    if config.get("fresh_profile"):
        shutil.rmtree(profile_dir, ignore_errors=True)
    profile_dir.mkdir(parents=True, exist_ok=True)


async def _find_composer(page, config, timeout=300.0, poll=0.5):
    """Poll for the chat input. Generous timeout because on a cold profile
    this is also the window in which a human logs in by hand."""
    start = time.monotonic()
    last_nudge = start
    while time.monotonic() - start < timeout:
        for selector in config["composer_selectors"]:
            elements = await safe_query(page, selector)
            if elements:
                return elements[0]
        now = time.monotonic()
        if now - last_nudge > 10:
            print(f"  ... waiting for {config['name']} composer (log in manually in the browser window if prompted)")
            last_nudge = now
        await asyncio.sleep(poll)
    return None


async def _type_and_queue_submit(page, config, query, attempts=5):
    """Type into the composer, re-fetching a fresh element handle right
    before every single action - the node keeps going stale mid-sequence
    (React re-render), so even a handle reused across two calls can die.
    fill() dispatches real per-character keyboard events (not a JS
    `.value=`), which is what a contenteditable/ProseMirror editor like
    ChatGPT's or Claude's needs - click to focus first, then type."""
    last_error = None
    for attempt in range(attempts):
        try:
            composer = await _find_composer(page, config, timeout=15)
            if composer is None:
                raise RuntimeError("composer never appeared (login timed out or page layout changed)")
            await composer.click()
            await asyncio.sleep(0.3)

            composer = await _find_composer(page, config, timeout=15)
            await composer.fill(query, clear=True)
            return
        except Exception as e:
            last_error = e
            print(f"  ... composer interaction failed (attempt {attempt + 1}/{attempts}): {e}")
            await asyncio.sleep(1.5)  # let the page finish re-rendering before retrying
    raise last_error


async def _click_send(page, config, timeout=10.0, poll=0.3):
    start = time.monotonic()
    aria_substr = config.get("send_button_aria_contains")
    while time.monotonic() - start < timeout:
        buttons = await safe_query(page, config["send_button_selector"])
        for b in buttons:
            try:
                if aria_substr:
                    aria = await safe_call(lambda b=b: b.get_attribute("aria-label"), default=None)
                    if not aria or aria_substr.lower() not in aria.lower():
                        continue
                if await safe_call(lambda b=b: b.get_attribute("disabled"), default=None) is None:
                    await b.click()
                    return True
            except Exception:
                pass
        await asyncio.sleep(poll)
    return False


async def _wait_for_response(page, config, timeout=180.0, poll=1.0):
    """Return True once an answer showed up and finished streaming, False if
    nothing ever appeared (a `no_answer`, not a crash)."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if await safe_query(page, config["assistant_message_selector"]):
            break
        await asyncio.sleep(poll)
    else:
        return False

    stable_checks = 0
    while time.monotonic() - start < timeout:
        if not await safe_query(page, config["stop_button_selector"]):
            stable_checks += 1
            if stable_checks >= 2:
                return True
        else:
            stable_checks = 0
        await asyncio.sleep(poll)
    return True  # timed out mid-stream; still save whatever's on the page


async def _submit_query(page, config, query):
    """Type + send. Shared by collect_one and the preflight check."""
    await _type_and_queue_submit(page, config, query)
    if not await _click_send(page, config):
        await page.press("Enter")  # fallback if the send-button heuristic drifted


async def _collect_direct_url(page, config, query):
    """ai_overview's path: no chat, no composer - one search URL per query.
    Returns (html, screenshot_b64, got_answer).

    Google keeps BOTH the "not available" fallback text AND the overview's
    own toggle controls in the DOM at all times, regardless of outcome -
    they differ only by inline CSS visibility. A substring match on the
    saved (static) HTML can't tell which one is actually showing (confirmed
    empirically: a capture with no overview still contained both marker
    strings). Check live computed visibility instead, before serializing."""
    url = config["url_template"].format(query=urllib.parse.quote_plus(query))
    await safe_call(lambda: page.goto(url), timeout=30, retries=2)
    await asyncio.sleep(config.get("settle_seconds", 3))

    # Page.evaluate always returns a stringified result ("True"/"False" for
    # a JS boolean, per its own str(value) fallback) - both strings are
    # truthy in Python, so the raw call result can't be used as a bool
    # directly. Compare against the string form explicitly.
    no_answer_text = config.get("no_answer_markers", [""])[0]
    got_answer_str = await safe_call(
        lambda: page.evaluate(
            """(needle) => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    if (node.textContent.includes(needle)) {
                        const el = node.parentElement;
                        const visible = !!(el && el.offsetParent !== null);
                        return !visible;  // fallback text hidden => a real overview rendered
                    }
                }
                return false;  // fallback text not found at all - be conservative
            }""",
            no_answer_text,
        ),
        timeout=CDP_TIMEOUT, default="False",
    )
    got_answer = (got_answer_str == "True")

    html = await safe_call(lambda: page.evaluate("() => document.documentElement.outerHTML"), timeout=CDP_TIMEOUT, default="")

    # best-effort: the overview usually renders below sponsored ads, off the
    # initial viewport - scroll it into frame before screenshotting
    scroll_sel = config.get("scroll_into_view_selector")
    if got_answer and scroll_sel:
        els = await safe_query(page, scroll_sel)
        if els:
            await safe_call(lambda: els[0].evaluate("() => this.scrollIntoView({block: 'center'})"), timeout=10, default=None)
            await asyncio.sleep(0.5)

    screenshot_b64 = await safe_call(lambda: page.screenshot(), timeout=CDP_TIMEOUT, default=None)
    return html, screenshot_b64, got_answer


# --- 2. TRANSPORT: get to the answer, grab it raw, do NOT interpret --------
async def collect_one(query, engine, run_id=None, capture_id=None):
    """
    Drive a real browser to `engine`, in a FRESH/isolated session (no history,
    no logged-in memory bleed), and ask exactly `query` - bare, no formatting
    wrapper. A real buyer doesn't say "list as a single comma-separated
    line"; the wrapper suppressed reasoning, hedges, and citations, which is
    exactly the signal accuracy/sourcing scoring needs.

    Then save, UNTOUCHED:
        - the full answer text / page HTML  ->  RAW_DIR / f"{slug}.html"
        - a screenshot                      ->  RAW_DIR / f"{slug}.png"

    Return a status dict. Do NOT parse which brands were named here.

    run_id is opt-in (see slug()) - stability checks use it. capture_id is
    opt-in too - the production run_session passes a readable
    slug_for_question() id instead of a hash; if omitted, falls back to the
    hash-based slug() as before.

    Status values:
        "success"    - got an answer, saved raw
        "no_answer"  - engine gave nothing (e.g. AI Overview didn't fire) = DATA
        "failed"     - collection broke (blocked, timeout) = a GAP, not a finding
                       (raised as an exception; run_session logs it as "failed")
    """
    if engine not in ENGINE_CONFIGS:
        raise NotImplementedError(f"engine={engine!r} not wired up yet")
    config = ENGINE_CONFIGS[engine]
    _prepare_profile_dir(config)

    session = BrowserSession(
        headless=HEADLESS,
        user_data_dir=str(config["profile_dir"]),
        keep_alive=False,
        enable_default_extensions=False,  # their content scripts were mutating the DOM mid-interaction
    )
    await session.start()
    try:
        page = await session.get_current_page()

        if config.get("direct_url_mode"):
            html = screenshot_b64 = got_answer = None
            for capture_attempt in range(3):
                html, screenshot_b64, got_answer = await _collect_direct_url(page, config, query)
                if html and screenshot_b64:
                    break
                await asyncio.sleep(1.0)
        else:
            await safe_call(lambda: page.goto(config["url"]), timeout=30, retries=2)
            await asyncio.sleep(2.0)  # let initial hydration/re-render settle before touching the DOM

            # Explicit, generous wait for a human to log in on a cold profile -
            # _type_and_queue_submit's own composer lookups use a short 15s
            # timeout (that's for React-staleness retries, not a login wait),
            # so without this gate a not-yet-logged-in session fails in ~80s
            # total instead of the ~5 minutes the profile-prep comments promise.
            composer = await _find_composer(page, config, timeout=300.0)
            if composer is None:
                raise RuntimeError(f"login timed out - no composer appeared for {config['name']} after 5 minutes")

            await _submit_query(page, config, query)

            got_answer = await _wait_for_response(page, config)

            html = screenshot_b64 = None
            for capture_attempt in range(3):
                html = await safe_call(lambda: page.evaluate("() => document.documentElement.outerHTML"), timeout=CDP_TIMEOUT, default=None)
                screenshot_b64 = await safe_call(lambda: page.screenshot(), timeout=CDP_TIMEOUT, default=None)
                if html and screenshot_b64:
                    break
                await asyncio.sleep(1.0)  # DOM still settling from the last streamed tokens
        if not html or not screenshot_b64:
            raise RuntimeError("failed to capture html/screenshot after 3 attempts")
        raw_id = capture_id if capture_id is not None else slug(query, engine, run_id=run_id)
        _save_raw(query, engine, html, screenshot_b64, capture_id=raw_id)

        # ai_overview: retrieval IS whether the overview rendered - no
        # "answered without search" case exists for it, unlike a chat
        # engine, and the generic marker-substring check can't distinguish
        # a real render from Google's always-present hidden template (see
        # _collect_direct_url). Use the already-correct live-computed value.
        retrieval = got_answer if config.get("direct_url_mode") else _detect_retrieval(html, config)

        return {
            "query": query, "engine": engine, "date": RUN_DATE,
            "status": "success" if got_answer else "no_answer",
            "retrieval": retrieval,
            "model": _extract_model(html, config),
            "raw": raw_id,
        }
    except Exception:
        try:
            page = await session.get_current_page()
            screenshot_b64 = await safe_call(lambda: page.screenshot(), timeout=15, default=None)
            if screenshot_b64:
                error_id = capture_id if capture_id is not None else slug(query, engine, run_id=run_id)
                (RAW_DIR / f"{error_id}__error.png").write_bytes(base64.b64decode(screenshot_b64))
        except Exception:
            pass
        raise
    finally:
        await session.stop()


async def _preflight_check_retrieval_marker(engine):
    """Each engine's _detect_retrieval() keys on an implementation-specific
    DOM marker that the provider can change on any UI update, silently
    flipping every `retrieval` value in a run to a false "didn't search".
    Fire a query known to force a citable search and confirm the marker
    still fires, BEFORE burning a whole session on a broken detector."""
    config = ENGINE_CONFIGS[engine]
    _prepare_profile_dir(config)
    session = BrowserSession(
        headless=HEADLESS,
        user_data_dir=str(config["profile_dir"]),
        keep_alive=False,
        enable_default_extensions=False,
    )
    await session.start()
    try:
        page = await session.get_current_page()
        if config.get("direct_url_mode"):
            html, _screenshot_b64, got_answer = await _collect_direct_url(page, config, config["preflight_query"])
            marker_ok = got_answer
        else:
            await safe_call(lambda: page.goto(config["url"]), timeout=30, retries=2)
            await asyncio.sleep(2.0)
            composer = await _find_composer(page, config, timeout=300.0)  # see collect_one's login-wait comment
            if composer is None:
                raise RuntimeError(f"login timed out - no composer appeared for {config['name']} after 5 minutes")
            await _submit_query(page, config, config["preflight_query"])
            await _wait_for_response(page, config)
            html = await safe_call(lambda: page.evaluate("() => document.documentElement.outerHTML"), timeout=CDP_TIMEOUT, default="")
            marker_ok = _detect_retrieval(html, config)
        (RAW_DIR / f"_preflight_retrieval_check__{engine}.html").write_text(html, encoding="utf-8")
        return marker_ok
    finally:
        await session.stop()


# --- 3. THE LOOP: every question x every engine x every repetition --------
def _already_done(capture_id):
    """Resumable: a prior 'success' or 'no_answer' capture on disk means
    skip it - both are real data, not gaps. Only 'failed' (or missing
    entirely) gets retried, so killing and re-running the same command picks
    up exactly where it stopped, without duplicates or re-paying for work
    already done."""
    base = RAW_DIR / capture_id
    return base.with_suffix(".html").exists() and base.with_suffix(".png").exists()


def _default_calls(engines):
    """Every (question, engine, repetition) triple in the full frozen set:
    21 main questions x engines x 5 reps, then 20 brand-direct combos x
    engines x 3 reps. Main questions first, in a stable order, so progress
    output and resumability behave predictably run to run."""
    calls = []
    for question in MAIN_QUESTIONS:
        for engine in engines:
            for rep in range(1, q.REPETITIONS["main"] + 1):
                calls.append((question, engine, rep))
    for question in BRAND_DIRECT_QUESTIONS:
        for engine in engines:
            for rep in range(1, q.REPETITIONS["brand_direct"] + 1):
                calls.append((question, engine, rep))
    return calls


async def run_session(run_config, questions_only=None, max_calls=None):
    """Drives the full frozen set against every engine in run_config, or a
    subset if questions_only is given as (questions, engines, reps_per_question)
    - the dry run passes (MAIN_QUESTIONS, ENGINES, 1).

    Every row gets run_id and location_setting from run_config, stamped
    directly - not left implicit, so October/December are comparable and a
    reader auditing the JSONL never has to guess what was pinned this run.
    """
    run_id = run_config["run_id"]
    location_setting = run_config.get("location_setting")
    if location_setting is None:
        print("WARNING: location_setting is null in run_config.json - every row will "
              "record location_setting=null. Fill it in before a run you intend to keep.")

    status_log = RAW_DIR / "status.jsonl"
    calls_made = 0
    cap = max_calls if max_calls is not None else run_config.get("max_calls_per_invocation")

    with status_log.open("a") as f:
        for engine in IMPLEMENTED_ENGINES:
            try:
                marker_ok = await _preflight_check_retrieval_marker(engine)
            except Exception as e:
                marker_ok = False
                print(f"PREFLIGHT ERROR ({engine}): retrieval-marker check crashed: {e}")
            preflight_rec = {
                "run_id": run_id, "engine": f"_preflight_{engine}", "date": RUN_DATE,
                "status": "ok" if marker_ok else "MARKER_BROKEN",
            }
            f.write(json.dumps(preflight_rec) + "\n")
            f.flush()
            if not marker_ok:
                print("!" * 70)
                print(f"PREFLIGHT FAILED ({engine}): retrieval marker did not fire on a known-search query.")
                print(f"{engine}'s UI likely changed - `retrieval` values for this engine in this run are NOT trustworthy.")
                print("!" * 70)

        if questions_only:
            main_qs, engines_subset, reps_override = questions_only
            calls = [
                (question, engine, rep)
                for question in main_qs
                for engine in engines_subset
                for rep in range(1, reps_override + 1)
            ]
        else:
            calls = _default_calls(ENGINES)
        total = len(calls)
        done_count = 0
        per_engine = {e: 0 for e in ENGINES}

        for question, engine, rep in calls:
            done_count += 1
            capture_id = slug_for_question(question["id"], engine, rep)
            if _already_done(capture_id):
                print(f"[{done_count}/{total}] skip (on disk)  {engine:12s} {question['id']:>4s} r{rep}")
                continue
            if cap is not None and calls_made >= cap:
                print(f"STOPPED: hit max_calls_per_invocation={cap}. Re-run the same command to resume.")
                break
            calls_made += 1
            per_engine[engine] += 1
            try:
                rec = await collect_one(question["text"], engine, capture_id=capture_id)
            except Exception as e:
                # A crash is a GAP, logged as such - never a silent hole.
                rec = {
                    "query": question["text"], "engine": engine, "date": RUN_DATE,
                    "status": "failed", "error": str(e), "raw": capture_id,
                }
            rec.update({
                "run_id": run_id,
                "question_id": question["id"],
                "repetition": rep,
                "timestamp_iso": datetime.now(timezone.utc).isoformat(),
                "location_setting": location_setting,
            })
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"[{done_count}/{total}] {rec['status']:9s} {engine:12s} {question['id']:>4s} r{rep} "
                  f"({calls_made} calls this invocation)")

        print(f"\nDone. {calls_made} calls made this invocation. Per-engine calls: {per_engine}")


# --- 4. (separate step, separate file later) OFFLINE EXTRACTION -----------
# extract.py reads raw/<date>/*.html and produces your real rows:
# which brands were named, any cited sources, retrieval on/off - schema'd,
# re-runnable, auditable. Because it reads SAVED raw, you can re-parse Aug's
# data in December without re-collecting. That's your longitudinal integrity.
#
# LOCKED: what counts as "named" (same tier as the frozen question set -
# apply identically across all 5 engines and every run, or the longitudinal
# comparison breaks).
#
# named_in_text: the brand's name appears anywhere in the assistant's
#   visible prose, regardless of position, sentiment, or hedging. A brand
#   buried in "you might also consider X" or "unlike X, this one..." still
#   counts as named - being named is a visibility event, not an endorsement.
#   Does NOT count if the name only appears in the echoed human turn, or in
#   the engine's own UI chrome/disclaimers.
#
# cited_as_source: the brand's domain appears as a citation/source link tied
#   to the answer (e.g. a citation pill), independent of named_in_text. A
#   brand can be named without being cited, cited without being named (a
#   source domain referenced only via link, never mentioned by name), or
#   both. Track these as two separate booleans - do not collapse into one
#   "mentioned" column, that's exactly the sourcing signal this project is
#   trying to measure.
#
# first_mention_position: word offset (or list position, if the answer
#   happens to enumerate) of the first named_in_text hit. Tracked separately
#   from named_in_text - ordering is a prominence signal, not a presence
#   signal, and conflating them loses information.
#
# Sentiment/stance (was the mention positive or negative) is explicitly OUT
# of scope for v0 extraction - a stretch goal, not required to answer "was
# X named."


def _cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="21 main questions x 5 engines x 1 rep (105 calls). No brand-direct loop. "
             "Writes run_id as '<run_id>_dry' and keeps its captures separate from the real run.",
    )
    parser.add_argument(
        "--max-calls", type=int, default=None,
        help="Override run_config.json's max_calls_per_invocation for this invocation only.",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Override run_config.json's run_id for this invocation only.",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Show the browser window. Only needed for a fresh claude login (its cookies are gone or "
             "were never saved) or to debug a UI change by eye - every other engine and every "
             "already-logged-in claude call runs perfectly well headless, which is the default.",
    )
    return parser.parse_args()


async def main():
    args = _cli()
    if args.headed:
        global HEADLESS
        HEADLESS = False
    run_config = load_run_config()
    if args.run_id:
        run_config["run_id"] = args.run_id
    if args.dry_run:
        run_config = {**run_config, "run_id": f"{run_config['run_id']}_dry"}
        print(f"DRY RUN: run_id={run_config['run_id']!r}, 21 questions x {len(ENGINES)} engines x 1 rep = "
              f"{21 * len(ENGINES)} calls. Brand-direct loop is skipped in a dry run.")
        await run_session(run_config, questions_only=(MAIN_QUESTIONS, ENGINES, 1), max_calls=args.max_calls)
    else:
        await run_session(run_config, max_calls=args.max_calls)


if __name__ == "__main__":
    asyncio.run(main())
