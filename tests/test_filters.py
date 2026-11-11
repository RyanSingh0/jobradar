"""Regression tests for the title gate and tiers (10 Nov 2026: two Salesforce roles were missed).
Run: python tests/test_filters.py  (exit 1 on failure). Uses saved posting text, no network."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jobradar as jr

FX = json.loads((Path(__file__).parent / "fixtures_10nov.json").read_text())
SPONS = {jr.norm("Salesforce"): 141, jr.norm("Acme Analytics"): 20}


def run(company, title, desc, location="Seattle, WA, United States"):
    if not jr.TITLE_OK.search(title) or jr.TITLE_BAD.search(title):
        return "DROPPED", ""
    j = jr.J(company=company, title=title, location=location, url="x", desc=desc, lca_col="")
    j["soft_senior"] = bool(jr.TITLE_SOFT.search(title))
    return jr.classify(j, SPONS)


GENERIC = ("We need SQL, Python and Tableau for dashboards, data quality checks, validation and reporting. "
           "Statistics, regression and forecasting. ") * 4
CASES = [
    ("Seller Analytics (Senior title, no years) reaches MAYBE", lambda: run(**{k: FX["seller"][k] for k in ("company", "title", "desc")}), {"MAYBE", "HOT"}),
    ("AI Labs Rotational Fellowship reaches HOT or MAYBE", lambda: run(**{k: FX["fellow"][k] for k in ("company", "title", "desc")}), {"MAYBE", "HOT"}),
    ("Referral company 4+ years stretch reaches MAYBE", lambda: run(**{k: FX["gtm"][k] for k in ("company", "title", "desc")}), {"MAYBE"}),
    ("Non-referral Senior Data Analyst, no years -> MAYBE not HOT", lambda: run("Acme Analytics", "Senior Data Analyst", GENERIC), {"MAYBE"}),
    ("Non-referral Senior Data Analyst asking 5+ years -> SKIP", lambda: run("Acme Analytics", "Senior Data Analyst", GENERIC + " 5+ years of experience."), {"SKIP"}),
    ("Non-referral asking 4 years -> SKIP", lambda: run("Acme Analytics", "Data Analyst", GENERIC + " 4+ years of experience."), {"SKIP"}),
    ("Data Analyst II with 2 years -> MAYBE", lambda: run("Acme Analytics", "Data Analyst II", GENERIC + " 2+ years of experience."), {"MAYBE"}),
    ("Plain Data Analyst 1-2 years -> HOT", lambda: run("Acme Analytics", "Data Analyst", GENERIC + " 1-2 years of experience."), {"HOT"}),
    ("Staff ML Engineer still dropped on title", lambda: run("Salesforce", "Staff Machine Learning Engineer", GENERIC), {"DROPPED"}),
    ("Lead Data Scientist still dropped on title", lambda: run("Salesforce", "Lead Data Scientist", GENERIC), {"DROPPED"}),
    ("Data Analyst III still dropped on title", lambda: run("Acme Analytics", "Data Analyst III", GENERIC), {"DROPPED"}),
    ("Postdoc fellow still dropped", lambda: run("Acme Analytics", "Postdoctoral Research Fellow", GENERIC), {"DROPPED"}),
    ("Fellowship that is not data/AI stays out of core", lambda: run("Acme Analytics", "Communications Fellowship",
        "Write press releases and plan events for the communications office. " * 6), {"LOW", "DROPPED"}),
]

if __name__ == "__main__":
    bad = 0
    for name, fn, ok in CASES:
        tier, why = fn()
        flag = "PASS" if tier in ok else "FAIL"
        bad += flag == "FAIL"
        print(f"{flag} {name}: {tier} {why[:90]}")
    print(f"{len(CASES) - bad}/{len(CASES)} passed")
    sys.exit(1 if bad else 0)
