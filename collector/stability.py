"""
Stability measurement - permanent part of the instrument, not a one-off.

Different job from extract.py: extract.py will parse ONE capture into a row.
This measures the run-to-run noise floor of ONE query by firing it N times
and comparing answers - because "brand X's presence dropped since August"
is meaningless without knowing how much a query's answer churns on its own,
with nothing about the world having changed.

Run this:
    - once per category, to size the N you need before trusting a single
      collection as signal instead of noise
    - per engine, as you wire up Gemini/Perplexity/AI Overview/Claude - each
      has its own noise profile
    - periodically across the Aug/Oct/Dec longitudinal runs, so a real
      brand-presence change can be told apart from ordinary churn

The brand-frequency table below is a rough proper-noun/domain heuristic for
a quick numeric read, NOT the authoritative extraction rule - that's a
separate methodology decision (see collect_v0.py section 4 / DECISIONS.md)
applied identically across engines and runs. Always read the raw texts too.
"""
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

import collect_v0 as c

# crude proper-noun / product-name heuristic: capitalized word (optionally
# multi-word), or a bare domain-like token (thing.io, thing.ai, thing.com)
_BRAND_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z0-9]*(?:\.(?:io|ai|com))?(?:\s[A-Z][a-zA-Z0-9]+)*\b"
)
_STOPWORDS = {"I", "The", "A", "An", "It", "This", "That", "These", "Those", "For", "If"}


def _extract_answer_text(html_path):
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")
    msgs = soup.select('[data-message-author-role="assistant"]')
    return msgs[-1].get_text(" ", strip=True) if msgs else ""


def _candidate_brands(text):
    found = [m.strip() for m in _BRAND_PATTERN.findall(text)]
    return [b for b in found if b not in _STOPWORDS and len(b) > 1]


async def collect_runs(query, engine, n, start_run_id=1):
    """Fire `query` at `engine` n times, each saved under its own run_id so
    none overwrite each other. Returns a list of (run_id, status_record)."""
    results = []
    for i in range(start_run_id, start_run_id + n):
        print(f"--- run {i - start_run_id + 1}/{n} (run_id={i}) ---")
        try:
            rec = await c.collect_one(query, engine, run_id=i)
        except Exception as e:
            rec = {"status": "failed", "error": str(e), "raw": None}
        print(json.dumps(rec))
        results.append((i, rec))
    return results


def report(query, engine, run_ids):
    """Print each run's raw answer text plus a rough brand-frequency table."""
    counts = Counter()
    lengths = []
    texts = {}
    for run_id in run_ids:
        slug = c.slug(query, engine, run_id=run_id)
        html_path = c.RAW_DIR / f"{slug}.html"
        if not html_path.exists():
            print(f"{slug}: MISSING (run failed?)")
            continue
        text = _extract_answer_text(html_path)
        texts[run_id] = text
        brands = _candidate_brands(text)
        counts.update(set(brands))  # once per run, not per mention
        lengths.append(len(text))

    print(f"\n=== raw answers ({len(texts)} runs) ===")
    for run_id, text in texts.items():
        print(f"\n--- run_id={run_id} ---")
        print(text)

    print(f"\n=== rough candidate-brand frequency (heuristic, not the extraction rule) ===")
    for brand, n in counts.most_common(30):
        print(f"  {n:2d}/{len(texts)}  {brand}")

    print(f"\nanswer length in chars: min={min(lengths)} max={max(lengths)} "
          f"(spread={max(lengths) - min(lengths)})")


if __name__ == "__main__":
    # Windows console defaults to cp1252, which can't encode em-dashes/arrows
    # that show up routinely in natural-prose answers - force UTF-8 so a
    # report never crashes on the model's own punctuation.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    engine = sys.argv[1] if len(sys.argv) > 1 else "chatgpt"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    query = c.MAIN_QUESTIONS[0]["text"]

    results = asyncio.run(collect_runs(query, engine, n))
    run_ids = [run_id for run_id, rec in results if rec.get("status") in ("success", "no_answer")]
    report(query, engine, run_ids)
