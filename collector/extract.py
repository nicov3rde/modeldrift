"""Offline extraction: turn saved raw HTML into the schema'd JSONL row per
response that the measurement spec (Part 3) actually wants.

Runs AFTER collection, never during it - collect_v0.py's whole design is
"save raw, do not interpret while the browser is open." This is the
"interpret" step, and it's re-runnable: because the full page HTML is on
disk under raw/<date>/, a bug found in October's extraction logic can be
fixed and re-applied to August's captures without re-collecting anything.

What this produces, one JSON object per line, written to
data/runs/<run_id>.jsonl:

    run_id, engine, model_version, question_id, question_text,
    repetition, timestamp_iso, location_setting,
    raw_response (visible answer text, unmodified), cited_urls (array, in
    order), error (null or message)

Citation extraction is best-effort per engine (see _CITATION_STRATEGIES
below) - each engine's citation markup was confirmed to *exist* via the
paired retrieval probes in collect_v0.py, but pulling the real href out
of it was not separately re-validated per URL. Spot-check a sample against
the saved screenshots before trusting cited_urls counts in an essay; the
saved raw HTML means this function can be corrected later without
re-collecting.

Usage:
    python extract.py aug2026
    python extract.py aug2026_dry
"""
import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

import collect_v0 as c
import questions as q

RAW_ROOT = Path("raw")
RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"

QUESTION_TEXT_BY_ID = {item["id"]: item["text"] for item in q.ALL_QUESTIONS}


def _answer_text(soup, engine):
    config = c.ENGINE_CONFIGS[engine]
    nodes = soup.select(config["assistant_message_selector"])
    return nodes[-1].get_text(" ", strip=True) if nodes else ""


def _hrefs_near(nodes):
    """Collect http(s) hrefs on each node, or its closest <a> ancestor/
    descendant if the marker itself isn't the link - in document order,
    deduped, first occurrence kept."""
    seen = []
    for node in nodes:
        candidates = []
        if node.name == "a" and node.get("href"):
            candidates.append(node)
        candidates += node.find_all("a", href=True)
        anc = node.find_parent("a", href=True)
        if anc:
            candidates.append(anc)
        for a in candidates:
            href = a.get("href", "")
            if href.startswith("http") and href not in seen:
                seen.append(href)
    return seen


# Engine -> function(soup) -> list[str] of cited URLs, in document order.
# Each keys off the same marker validated for retrieval detection in
# collect_v0.ENGINE_CONFIGS (see that file's per-engine comments for how
# each marker was confirmed with a paired search/no-search probe).
_CITATION_STRATEGIES = {
    "chatgpt": lambda soup: _hrefs_near(soup.select('[data-testid="webpage-citation-pill"]')),
    "claude": lambda soup: _hrefs_near(soup.select('a[class*="group/tag"]')),
    "gemini": lambda soup: _hrefs_near(soup.select('[aria-label*="View source details for citation"]')),
    "perplexity": lambda soup: _hrefs_near(soup.select('[data-testid="trusted-citation-check"]')),
    "ai_overview": lambda soup: _hrefs_near(soup.select('div[aria-label="Show more AI Overview"]')),  # see note below
}
# ai_overview note: the overview's own container isn't keyed off a stable
# testid (see collect_v0.py's comment on Google's non-hashed classnames), so
# this pulls links from the whole page and the caller should sanity-check
# against the saved screenshot - Google SERP chrome (ads, "People also ask")
# can leak in here. Tightening this selector is a good first improvement to
# make against a handful of real August captures before trusting the count.


def cited_urls_for(engine, soup):
    strategy = _CITATION_STRATEGIES.get(engine)
    if strategy is None:
        return []
    try:
        return strategy(soup)
    except Exception:
        return []


def extract_run(run_id):
    rows = []
    status_files = sorted(RAW_ROOT.glob("*/status.jsonl"))
    if not status_files:
        print(f"No raw/<date>/status.jsonl files found under {RAW_ROOT.resolve()}")
        return rows

    for status_file in status_files:
        raw_dir = status_file.parent
        with status_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("run_id") != run_id:
                    continue
                if rec.get("engine", "").startswith("_preflight_"):
                    continue  # preflight rows aren't responses

                question_id = rec.get("question_id")
                out = {
                    "run_id": run_id,
                    "engine": rec.get("engine"),
                    "model_version": rec.get("model"),
                    "question_id": question_id,
                    "question_text": QUESTION_TEXT_BY_ID.get(question_id, rec.get("query")),
                    "repetition": rec.get("repetition"),
                    "timestamp_iso": rec.get("timestamp_iso"),
                    "location_setting": rec.get("location_setting"),
                    "raw_response": "",
                    "cited_urls": [],
                    "error": rec.get("error"),
                }

                if rec.get("status") == "failed":
                    rows.append(out)
                    continue

                html_path = raw_dir / f"{rec['raw']}.html"
                if not html_path.exists():
                    out["error"] = f"status said {rec.get('status')!r} but {html_path.name} is missing"
                    rows.append(out)
                    continue

                soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
                out["raw_response"] = _answer_text(soup, rec["engine"])
                out["cited_urls"] = cited_urls_for(rec["engine"], soup)
                rows.append(out)

    return rows


def main():
    if len(sys.argv) < 2:
        print("usage: python extract.py <run_id>   (e.g. aug2026 or aug2026_dry)")
        sys.exit(1)
    run_id = sys.argv[1]
    rows = extract_run(run_id)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"{run_id}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} rows to {out_path}")
    empty_citations = sum(1 for r in rows if not r["cited_urls"] and not r.get("error"))
    print(f"Rows with zero cited_urls: {empty_citations}/{len(rows)} "
          f"(expected to be high for engines that don't cite consistently - see methodology)")


if __name__ == "__main__":
    main()
