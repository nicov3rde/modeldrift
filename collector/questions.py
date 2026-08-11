"""Loads the frozen question set from data/question-set.v1.json.

Single source of truth, shared conceptually with the site's
src/data/questions.ts (same JSON, two readers). Never hardcode a question
string in a runner script - import from here instead, per the freeze rule:
after data/question-set.v1.json's freeze_date, wording is locked, and a
revision creates a v2 file rather than editing v1 in place.
"""
import json
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "question-set.v1.json"

with _DATA_PATH.open(encoding="utf-8") as f:
    _RAW = json.load(f)

FREEZE_DATE = _RAW["freeze_date"]
ENGINES = _RAW["engines"]
REPETITIONS = _RAW["repetitions"]  # {"main": 5, "brand_direct": 3}

# Flat list of the 21 frozen questions: [{"id": "A1", "bucket": "A", "text": "..."}, ...]
MAIN_QUESTIONS = [
    {"id": q["id"], "bucket": bucket["id"], "text": q["text"]}
    for bucket in _RAW["buckets"]
    for q in bucket["questions"]
]

# Flat list of the 20 brand-direct combos (2 templates x 10 companies):
# [{"id": "BD-elyos-ai-what-is", "text": "What is Elyos AI", "company": "Elyos AI", "company_slug": "elyos-ai"}, ...]
BRAND_DIRECT_QUESTIONS = [
    {
        "id": f"BD-{company['slug']}-{template['id']}",
        "text": template["text"].format(company=company["name"]),
        "company": company["name"],
        "company_slug": company["slug"],
    }
    for company in _RAW["brand_direct"]["companies"]
    for template in _RAW["brand_direct"]["templates"]
]

COMPANIES = _RAW["brand_direct"]["companies"]

ALL_QUESTIONS = MAIN_QUESTIONS + BRAND_DIRECT_QUESTIONS


def reps_for(question_id: str) -> int:
    """5 reps for the 21 frozen questions, 3 for the brand-direct loop."""
    return REPETITIONS["brand_direct"] if question_id.startswith("BD-") else REPETITIONS["main"]


if __name__ == "__main__":
    print(f"freeze_date={FREEZE_DATE}  engines={ENGINES}")
    print(f"main questions: {len(MAIN_QUESTIONS)} (expect 21)")
    print(f"brand-direct combos: {len(BRAND_DIRECT_QUESTIONS)} (expect 20)")
    total_main = len(MAIN_QUESTIONS) * len(ENGINES) * REPETITIONS["main"]
    total_bd = len(BRAND_DIRECT_QUESTIONS) * len(ENGINES) * REPETITIONS["brand_direct"]
    print(f"total main responses per run: {total_main}")
    print(f"total brand-direct responses per run: {total_bd}")
    print(f"grand total per run: {total_main + total_bd}")
