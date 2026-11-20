#!/usr/bin/env python3
"""
Smoke test for the project catalog and project ranking.

Verifies that:
1. okf/project_catalog.yaml loads and every project has the required fields
2. okf/project_catalog_condensed.yaml matches the catalog (same titles, no bullets)
3. A keyword-overlap ranker puts an archetype-appropriate project first for each JD type
4. (optional, --llm) the real Claude Code ranking prompt returns valid JSON

Run (from the project folder):
    .venv\\Scripts\\python.exe tests/test_llm_search.py
    .venv\\Scripts\\python.exe tests/test_llm_search.py --llm      # also calls Claude Code
"""

import json
import re
import sys
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = SKILL_DIR / "okf" / "project_catalog.yaml"
CONDENSED_PATH = SKILL_DIR / "okf" / "project_catalog_condensed.yaml"

REQUIRED_FIELDS = ("title", "description", "technologies", "archetypes", "bullets", "keywords")

# ─── Test JDs (one per archetype) ─────────────────────────────────────────────

TEST_JDS = [
    {
        "archetype": "Plant Research & Experiments",
        "expected_top": ["Working Student, Plant Experiments", "Master's Thesis", "ZALF"],
        "title": "Working Student Plant Science",
        "company": "AgriTech GmbH",
        "jd_text": """
We are looking for a working student to support plant experiments and product development.

Requirements:
- Studies in horticulture, plant science or agriculture
- Experience setting up and monitoring plant experiments in the greenhouse or lab
- Careful documentation of measurements and experiment results
- ImageJ or Excel for data analysis
- Cross-functional collaboration with the product team
""",
    },
    {
        "archetype": "Quality Control & Food Safety",
        "expected_top": ["Hydroponics Food Safety", "Seminar Research", "ZALF"],
        "title": "Student Assistant Quality Control",
        "company": "FreshFoods AG",
        "jd_text": """
Student assistant in quality control and food safety.

Requirements:
- Knowledge of food safety standards and contamination risks
- Quality assessments of plant health and produce
- Laboratory skills: sample preparation, analytical procedures, pH measurement
- Compliance documentation and attention to detail
""",
    },
    {
        "archetype": "Hydroponics & Controlled-Environment Agriculture",
        "expected_top": ["Hydroponics Food Safety", "Master's Thesis", "Working Student, Plant Experiments"],
        "title": "Hydroponics Technician",
        "company": "VertiFarm",
        "jd_text": """
Hydroponics technician for an indoor farm producing microgreens.

Requirements:
- Hands-on hydroponics and soilless cultivation experience
- Nutrient solution, pH and EC management and water quality monitoring
- Plant health monitoring and fungal contamination control
- Controlled-environment agriculture, light regimes
""",
    },
]


def load_catalog(path=CATALOG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["projects"]


def test_catalog_structure():
    print("Test 1: Catalog structure validation...")
    projects = load_catalog()
    assert len(projects) >= 4, f"Expected at least 4 catalog entries, got {len(projects)}"
    titles = set()
    for p in projects:
        for field in REQUIRED_FIELDS:
            assert field in p, f"Project '{p.get('title', '?')}' missing field: {field}"
        assert 3 <= len(p["bullets"]) <= 10, f"'{p['title']}' has {len(p['bullets'])} bullets (need 3-10)"
        assert p["title"] not in titles, f"Duplicate title: {p['title']}"
        titles.add(p["title"])
        assert not p.get("repo_url"), f"'{p['title']}' has a repo_url but the candidate has no GitHub portfolio"
    print(f"  PASS: {len(projects)} projects, all have required fields")
    return projects


def test_condensed_matches_catalog(projects):
    print("\nTest 2: Condensed catalog is in sync...")
    condensed = load_catalog(CONDENSED_PATH)
    assert [p["title"] for p in condensed] == [p["title"] for p in projects], \
        "project_catalog_condensed.yaml is stale; run: python extract_projects.py --condensed " \
        "--catalog okf/project_catalog.yaml --output okf/project_catalog_condensed.yaml"
    assert all("bullets" not in p for p in condensed), "condensed catalog must not contain bullets"
    print(f"  PASS: {len(condensed)} condensed entries match")


def keyword_overlap_ranker(jd_text, projects, top_n=6):
    """Offline fallback ranker: JD word overlap with each project's keywords/technologies."""
    words = {w.strip(".,;:()[]{}\"'!?/-") for w in jd_text.lower().split() if len(w) > 2}
    scored = []
    for p in projects:
        kw = {k.lower() for k in p.get("keywords", [])}
        # also match multi-word keywords as substrings of the JD
        phrase_hits = sum(1 for k in kw if " " in k and k in jd_text.lower())
        tech = {t.strip().lower() for t in re.split(r"[,;]", p.get("technologies", ""))}
        tech_hits = sum(1 for t in tech if t and t in jd_text.lower())
        scored.append((len(words & kw) + phrase_hits + tech_hits, p["title"]))
    scored.sort(key=lambda x: -x[0])
    return [{"rank": i + 1, "title": t, "reason": f"overlap score {s}"} for i, (s, t) in enumerate(scored[:top_n])]


def test_ranking_for_jds(projects):
    print("\nTest 3: Keyword ranking for representative JDs...")
    ok = True
    for jd in TEST_JDS:
        ranked = keyword_overlap_ranker(jd["jd_text"], projects)
        top3 = [r["title"] for r in ranked[:3]]
        hit = any(any(exp.lower() in t.lower() for exp in jd["expected_top"]) for t in top3)
        status = "PASS" if hit else "WARN"
        ok = ok and hit
        print(f"  {status}: {jd['company']} — {jd['title']} ({jd['archetype']}) -> top3: {top3}")
    assert ok, "Keyword ranker did not surface an expected project for at least one archetype"


def test_llm_ranking(projects):
    """Optional: real model call through api_pipeline.call_harness (needs `claude auth login`)."""
    print("\nTest 4: Claude Code ranking (--llm)...")
    sys.path.insert(0, str(SKILL_DIR))
    import api_pipeline

    catalog_yaml = yaml.dump({"projects": projects}, allow_unicode=True, default_flow_style=False)
    n = min(6, len(projects))
    jd = TEST_JDS[0]
    prompt = f"""Rank the {n} most relevant projects for this job. Return ONLY a JSON array of
objects with keys "rank" (int), "title" (exact catalog title), "reason" (one sentence).

## Project Catalog
{catalog_yaml}

## Job Description
{jd['jd_text']}"""
    text = api_pipeline.call_harness(prompt, system="You are a project ranking system. Output JSON only.")
    match = re.search(r"\[.*\]", text, re.DOTALL)
    assert match, f"No JSON array in response: {text[:200]}"
    ranked = json.loads(match.group(0))
    titles = {p["title"] for p in projects}
    assert all(r["title"] in titles for r in ranked), "Model returned a title that is not in the catalog"
    print(f"  PASS: {len(ranked)} ranked, top = {ranked[0]['title']}")


if __name__ == "__main__":
    projects = test_catalog_structure()
    test_condensed_matches_catalog(projects)
    test_ranking_for_jds(projects)
    if "--llm" in sys.argv:
        test_llm_ranking(projects)
    print("\nAll tests passed.")
