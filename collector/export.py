"""Two flat CSV exports from data/runs/<run_id>.jsonl, for eyeballing in
Sheets - not analysis. Presence counting here is deliberately literal (exact
company-name substring match, case-insensitive): no alias table, no fuzzy
matching. Building the alias table ("Housecall"/"Housecall Pro"/"HousecallPro"
are one company) is Part 4 of the measurement spec's real presence analysis,
done later against the full picture, not bolted on here as a guess.

Usage:
    python export.py aug2026
Writes:
    data/exports/<run_id>_flat.csv       one row per response
    data/exports/<run_id>_presence.csv   one row per (question_id, engine, company)
"""
import csv
import json
import re
import sys
from pathlib import Path

import questions as q

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
EXPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"

COMPANIES = [c["name"] for c in q.COMPANIES]


def _load_rows(run_id):
    path = RUNS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        print(f"{path} not found - run extract.py {run_id} first.")
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def export_flat(run_id, rows):
    out_path = EXPORTS_DIR / f"{run_id}_flat.csv"
    fields = [
        "run_id", "engine", "model_version", "question_id", "question_text",
        "repetition", "timestamp_iso", "location_setting",
        "response_preview", "citation_count", "error",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            preview = (row.get("raw_response") or "")[:300]
            writer.writerow({
                "run_id": row.get("run_id"),
                "engine": row.get("engine"),
                "model_version": row.get("model_version"),
                "question_id": row.get("question_id"),
                "question_text": row.get("question_text"),
                "repetition": row.get("repetition"),
                "timestamp_iso": row.get("timestamp_iso"),
                "location_setting": row.get("location_setting"),
                "response_preview": preview,
                "citation_count": len(row.get("cited_urls") or []),
                "error": row.get("error"),
            })
    print(f"Wrote {len(rows)} rows to {out_path}")


def _named_companies(text):
    if not text:
        return []
    return [name for name in COMPANIES if re.search(re.escape(name), text, re.IGNORECASE)]


def export_presence(run_id, rows):
    """One row per (question_id, engine, company): appearance count out of
    the reps actually run for that question, and mean position among
    responses where the company was named. question_id here is the frozen
    A1-D21 set only - the brand-direct loop isn't a presence measure (the
    company's own name is baked into the question)."""
    out_path = EXPORTS_DIR / f"{run_id}_presence.csv"
    main_ids = {item["id"] for item in q.MAIN_QUESTIONS}

    # (question_id, engine, company) -> {"named": int, "reps_seen": int, "positions": [int]}
    tally = {}
    for row in rows:
        qid = row.get("question_id")
        if qid not in main_ids:
            continue
        engine = row.get("engine")
        text = row.get("raw_response") or ""
        named_here = _named_companies(text)
        for company in COMPANIES:
            key = (qid, engine, company)
            slot = tally.setdefault(key, {"named": 0, "reps_seen": 0, "positions": []})
            slot["reps_seen"] += 1
            if company in named_here:
                slot["named"] += 1
                slot["positions"].append(text.lower().find(company.lower()))

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question_id", "engine", "company", "named_count", "reps_seen", "mean_char_position_when_named"])
        for (qid, engine, company), slot in sorted(tally.items()):
            mean_pos = (sum(slot["positions"]) / len(slot["positions"])) if slot["positions"] else ""
            writer.writerow([qid, engine, company, slot["named"], slot["reps_seen"], mean_pos])
    print(f"Wrote {len(tally)} rows to {out_path}")
    print("Note: mean_char_position_when_named is a character offset, not a rank/list "
          "position - a rough proximity signal for a quick look, not the real position "
          "metric from the analysis plan (which needs ordered list extraction per response).")


def main():
    if len(sys.argv) < 2:
        print("usage: python export.py <run_id>")
        sys.exit(1)
    run_id = sys.argv[1]
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = _load_rows(run_id)
    export_flat(run_id, rows)
    export_presence(run_id, rows)


if __name__ == "__main__":
    main()
