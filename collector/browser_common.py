"""Shared helpers for every engine's collector - import this first.

Two problems showed up repeatedly while wiring ChatGPT and Claude, neither
specific to either engine, so both live here instead of being rediscovered
per file:

1. Windows' console defaults to cp1252, which can't encode the em-dashes,
   arrows, and icon-font private-use characters that show up routinely in
   natural-prose answers and in some UI text. Reconfiguring stdout on import
   means every script gets this for free.

2. The CDP/DevTools WebSocket connection drops mid-session unpredictably -
   observed reconnect stalls ranged from instant up to 943 seconds during
   this project's exploration. A plain try/except around a CDP call doesn't
   help when the call just hangs; it needs a hard timeout too, or one dead
   connection silently stalls (or poisons) an entire collection run.
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

CDP_CALL_TIMEOUT = 15.0
CDP_CALL_RETRIES = 3
CDP_RETRY_DELAY = 1.0


async def safe_call(factory, *, timeout=CDP_CALL_TIMEOUT, retries=CDP_CALL_RETRIES,
                     default=None, retry_delay=CDP_RETRY_DELAY):
    """Run an async CDP-backed call with a hard timeout and retries.

    `factory` is a zero-arg callable returning a fresh awaitable each call
    (e.g. `lambda: page.screenshot()`) - a coroutine object can't be awaited
    twice, so a retry needs a new one each attempt. Treats both raised
    exceptions AND a timed-out/hung call as transient; returns `default`
    if every attempt fails rather than raising or hanging the caller.
    """
    for attempt in range(retries):
        try:
            return await asyncio.wait_for(factory(), timeout=timeout)
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(retry_delay)
    return default


async def safe_query(page, selector, timeout=CDP_CALL_TIMEOUT, retries=CDP_CALL_RETRIES):
    """CDP node lookups race with streaming re-renders and can hang on a
    dropped WebSocket - treat 'nothing matched yet' and 'the connection
    hiccuped' identically, since both just mean 'try again next poll'."""
    result = await safe_call(
        lambda: page.get_elements_by_css_selector(selector),
        timeout=timeout, retries=retries, default=[],
    )
    return result if result is not None else []
