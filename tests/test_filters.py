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
    ("Tool-free quant/risk posting still surfaces", lambda: run("Acme Analytics", "Credit Risk Analyst",
        ("Front office credit risk for derivatives and FX portfolios, model risk review, reporting and quantitative research. "
         "1-2 years of experience. ") * 3), {"MAYBE", "HOT"}),
    ("Staff ML Engineer still dropped on title", lambda: run("Salesforce", "Staff Machine Learning Engineer", GENERIC), {"DROPPED"}),
    ("Lead Data Scientist still dropped on title", lambda: run("Salesforce", "Lead Data Scientist", GENERIC), {"DROPPED"}),
    ("Data Analyst III still dropped on title", lambda: run("Acme Analytics", "Data Analyst III", GENERIC), {"DROPPED"}),
    ("Postdoc fellow still dropped", lambda: run("Acme Analytics", "Postdoctoral Research Fellow", GENERIC), {"DROPPED"}),
    ("Fellowship that is not data/AI stays out of core", lambda: run("Acme Analytics", "Communications Fellowship",
        "Write press releases and plan events for the communications office. " * 6), {"LOW", "DROPPED"}),
]

# 27 Nov 2026: entry-level finance and risk analyst titles (Wayflyer "Graduate Credit Analyst" was LOW)
WAYFLYER = ("Analyse financial and non-financial data on new and existing customers. Assess and quantify risk. You don't need "
            "years of experience. A strong academic record in Business, Finance, Engineering or Computer Science. "
            "An instinct for data (Excel or SQL is a plus). Based in our Charlotte HQ. ") * 3
UNDERWRITE = ("Underwrite commercial loans, spread financial statements, prepare credit memos for the loan committee. "
              "3 years of commercial lending experience. ") * 3
CASES += [
    ("Graduate Credit Analyst, no data-occupation LCA -> MAYBE (was LOW)", lambda: run("Wayflyer", "Graduate Credit Analyst",
        WAYFLYER, "Charlotte, North Carolina, United States"), {"MAYBE"}),
    ("Graduate Credit Analyst at a sponsor, Python and SQL -> HOT", lambda: run("Acme Analytics", "Graduate Credit Analyst",
        GENERIC + WAYFLYER), {"HOT"}),
    ("Junior Investment Analyst with Excel -> at least MAYBE", lambda: run("Acme Analytics", "Junior Investment Analyst",
        ("Build portfolio reports in Excel, research public companies, statistics on fund performance. ") * 4), {"MAYBE", "HOT"}),
    ("Plain bank Credit Analyst (underwriting) is not lifted", lambda: run("Acme Analytics", "Credit Analyst", UNDERWRITE),
        {"LOW", "MAYBE", "SKIP"}),
    ("Graduate Credit Analyst with no data skill stays below core", lambda: run("Acme Analytics", "Graduate Credit Analyst",
        UNDERWRITE.replace("3 years of commercial lending experience. ", "")), {"LOW", "MAYBE"}),
]

# 23 Nov 2026: builder family (entry Forward Deployed, AI solutions, automation/transformation associate, LLM evaluation)
BUILD = ("You will write Python and SQL against our warehouse, ship LLM tools and APIs with customers, dashboards, "
         "data pipelines, machine learning and statistics. 0-2 years of experience. ") * 4
CASES += [
    ("Forward Deployed Engineer with Python + SQL, 0-2 years -> HOT", lambda: run("Acme Analytics", "Forward Deployed Engineer", BUILD), {"HOT"}),
    ("AI Solutions Analyst with Python + SQL -> HOT", lambda: run("Acme Analytics", "AI Solutions Analyst", BUILD), {"HOT"}),
    ("Transformation Associate with Python + SQL -> HOT", lambda: run("Acme Analytics", "Transformation Associate", BUILD), {"HOT"}),
    ("AI Agent Evaluation Engineer -> HOT", lambda: run("Acme Analytics", "AI Agent Evaluation Engineer", BUILD), {"HOT"}),
    ("Forward Deployed Engineer without SQL stays below HOT", lambda: run("Acme Analytics", "Forward Deployed Engineer",
        BUILD.replace("Python and SQL", "Java and TypeScript")), {"LOW", "MAYBE"}),
    ("Forward Deployed Engineer asking '5 years ... including 2' stays below HOT", lambda: run("Acme Analytics",
        "Forward Deployed Engineer", BUILD.replace("0-2 years of experience", "5 years of experience, including 2 in AI")), {"LOW", "SKIP"}),
    ("Distinguished AI Engineer dropped on title", lambda: run("Acme Analytics", "Distinguished AI Engineer", BUILD), {"DROPPED"}),
    ("Test Automation Engineer dropped on title", lambda: run("Acme Analytics", "Test Automation Engineer", BUILD), {"DROPPED"}),
]

# 23 Nov 2026: location gate. (location, country field) -> True if outside the US. Leaks of 17 Nov (Zug, Sabana, Lucknow,
# Haifa, Chengdu) plus US towns the old gate dropped (Indiana, New Mexico, Dublin OH, Melbourne FL, Vancouver WA).
LOC = [
    ("CRI-Sabana", "", True), ("Corp - Zug Corporate Office", "", True), ("1401-GIPL-Experio-Vibhuti-Khand-Lucknow-UP", "", True),
    ("Haifa HEALTHCARE HA IL 2", "", True), ("Chengdu, Sichuan", "", True), ("London United Kingdom remote", "", True),
    ("Toronto Canada remote", "", True), ("Mississauga Mississauga CA", "CA", True), ("Laval, QC", "", True),
    ("GBR MLTN 120", "", True), ("Manchester---GBR", "", True), ("Sofia, BGR", "", True), ("Remote, Mexico", "", True),
    ("Tbilisi, Georgia", "", True), ("Cork", "", True), ("Cork ; Cork (Ireland)", "Ireland", True),
    ("Maconomy site ; Greater Noida (India)", "India", True),
    ("Dublin, OH", "", False), ("Melbourne, FL", "", False), ("Vancouver, WA", "", False), ("Albuquerque, New Mexico", "", False),
    ("Fort Wayne, Indiana", "", False), ("Indianapolis, IN", "", False), ("IND07", "", False), ("NY06-01-Niskayuna-GRC", "", False),
    ("GEORGIA - VIRTUAL - GA01", "", False), ("Atlanta, Georgia", "", False), ("Cambridge, MA", "", False), ("Lebanon, NH", "", False),
    ("New Brunswick, NJ", "", False), ("Remote-TX", "", False), ("2 Locations", "", False), ("Remote", "", False),
    ("Cork ; New York, New York (Ireland)", "Ireland", False), ("UT MAIN CAMPUS (United States of America)", "United States of America", False),
    ("Paris France Palo Alto Amsterdam London Berlin remote", "", False), ("Seattle, WA, United States", "US", False),
]
CASES += [(f"location {l!r} foreign={want}", lambda l=l, c=c: (str(jr.looks_foreign(l, c)), ""), {str(want)}) for l, c, want in LOC]
CASES += [
    ("Unplaceable non-Workday location with no US evidence -> SKIP", lambda: run("Acme Analytics", "Data Analyst",
        GENERIC + " 1-2 years of experience.", location="RMZ Titanium"), {"SKIP"}),
    ("Unplaceable location with a dollar pay range stays in", lambda: run("Acme Analytics", "Data Analyst",
        GENERIC + " 1-2 years of experience. Pay range $85,000 - $95,000.", location="Main Campus"), {"HOT"}),
]

# 24 Nov 2026 (Aryan): internships open to graduates, contracts and temporary roles are in scope; current-student-only
# internships and future-graduation programs are not.
CASES += [
    ("Data Science Intern open to recent graduates reaches MAYBE or HOT", lambda: run("Acme Analytics", "Data Science Intern",
        GENERIC + " Open to students and recent graduates. Paid, 40 hours per week."), {"MAYBE", "HOT"}),
    ("Data Analyst Internship for graduates with a degree reaches MAYBE or HOT", lambda: run("Acme Analytics", "Data Analyst Internship",
        GENERIC + " Bachelor's or Master's degree completed. Paid, full time for 6 months."), {"MAYBE", "HOT"}),
    ("Intern who must be currently enrolled -> SKIP", lambda: run("Acme Analytics", "Data Science Intern",
        GENERIC + " Candidates must be currently enrolled in a degree program."), {"SKIP"}),
    ("Intern with an expected graduation in 2027 -> SKIP", lambda: run("Acme Analytics", "Data Analyst Intern",
        GENERIC + " Expected graduation between December 2026 and June 2027."), {"SKIP"}),
    ("Intern returning to school -> SKIP", lambda: run("Acme Analytics", "Machine Learning Intern",
        GENERIC + " You must be returning to school after the internship."), {"SKIP"}),
    ("Full-time role 'pursuing or have completed' stays in", lambda: run("Acme Analytics", "Data Analyst",
        GENERIC + " 1-2 years of experience. Currently pursuing or have completed a Master's degree in a quantitative field."), {"HOT", "MAYBE"}),
    ("Contract Data Analyst reaches HOT or MAYBE", lambda: run("Acme Analytics", "Contract Data Analyst",
        GENERIC + " 1-2 years of experience. 6-month W2 contract."), {"HOT", "MAYBE"}),
    ("Staffing W2 contract reaches HOT or MAYBE", lambda: run("Insight Global", "Data Analyst (Contract)",
        GENERIC + " 1-2 years of experience. This is a 6 month W2 contract with our client, a healthcare company."), {"HOT", "MAYBE"}),
    ("Corp-to-corp only contract -> SKIP", lambda: run("Acme Staffing", "Data Analyst", GENERIC + " C2C only. 1 year of experience."), {"SKIP"}),
    ("'No C2C' W2 contract stays in", lambda: run("Acme Staffing", "Data Analyst", GENERIC + " W2 only, no C2C. 1 year of experience."), {"HOT", "MAYBE"}),
    ("Training fee posting -> SKIP", lambda: run("Acme Staffing", "Junior Data Analyst", GENERIC + " A one-time training fee applies before placement."), {"SKIP"}),
    ("Co-op still dropped on title", lambda: run("Acme Analytics", "Data Science Co-op", GENERIC), {"DROPPED"}),
    ("Summer 2027 internship still dropped on title", lambda: run("Acme Analytics", "Summer 2027 Data Science Intern", GENERIC), {"DROPPED"}),
]

# 25 Nov 2026 (Aryan): 54 of the 57 internships that reached HOT or MAYBE on 24-25 Nov were for current students. Real lines.
CASES += [
    ("TikTok 'Currently pursuing an Undergraduate/Master's' -> SKIP", lambda: run("TikTok", "Data Scientist Intern (TikTok LIVE)",
        GENERIC + " Minimum Qualifications: Currently pursuing an Undergraduate/Master's in Computer Science or a related field."), {"SKIP"}),
    ("TikTok '2027 Start (PhD)' title -> SKIP", lambda: run("TikTok", "Research Scientist Intern (Trust and Safety - CV/NLP/Multimodal LLM) - 2027 Start (PhD)",
        GENERIC + " PhD internships at Our Company provide students with the opportunity to contribute to our products."), {"SKIP", "DROPPED"}),
    ("State Street '2027 Summer Internship' -> dropped", lambda: run("State Street", "Quantitative Risk Internship - 2027 Summer Internship",
        GENERIC + " Undergraduate student in a quantitative field such as statistics or economics."), {"SKIP", "DROPPED"}),
    ("Barclays 'Summer Internship Program 2028' -> SKIP", lambda: run("Barclays", "Markets Quantitative Analyst Summer Internship Program 2028 New York", GENERIC), {"SKIP", "DROPPED"}),
    ("ASML 'must be currently pursuing a bachelor's' -> SKIP", lambda: run("ASML", "Internship - Data Analyst",
        GENERIC + " Candidate must be currently pursuing a bachelor's or master's degree and maintaining a 3.0 GPA."), {"SKIP"}),
    ("Expedia 'Must be graduating with a PhD' -> SKIP", lambda: run("Expedia", "Applied Science Intern - PhD",
        GENERIC + " Must be graduating with a PhD degree in a technical subject in 2027 or later."), {"SKIP", "DROPPED"}),
    ("KLA 'Pursuing a Bachelor's or Master's' -> SKIP", lambda: run("KLA Corporation", "PLM BI & Analytics Intern",
        GENERIC + " Pursuing a Bachelor's or Master's degree in Business Analytics, Information Systems or related."), {"SKIP"}),
    ("Jabil 'Senior or recent graduate' internship can reach HOT", lambda: run("Acme Analytics", "Data Scientist Intern",
        GENERIC + " 1-2 years of experience. Senior or recent graduate with a Bachelor or above in Data Science."), {"HOT", "MAYBE"}),
    ("Internship that says nothing on enrollment stays below HOT", lambda: run("Acme Analytics", "Data Science Intern",
        GENERIC + " 1-2 years of experience. Paid, 40 hours per week."), {"MAYBE", "LOW"}),
    ("Graduate Assistant (student employment) dropped on title", lambda: run("University of St. Thomas", "Graduate Assistant for Data Analytics, Center for Well-Being", GENERIC), {"DROPPED"}),
    ("Full-time 'Graduate - 2027 Start' for those who have recently completed stays in", lambda: run("Acme Analytics",
        "Machine Learning Engineer Graduate - 2027 Start", GENERIC + " Individuals who are completing or have recently completed a Bachelor's degree."), {"HOT", "MAYBE", "LOW"}),
]

# 23 Nov 2026 (evening): board readers
LD = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Data Scientist 1","description":"<p>Python and SQL</p>",'
      '"jobLocation":[{"@type":"Place","address":{"addressLocality":"St. Louis","addressRegion":"MO","addressCountry":"US"}}]}</script>')
CASES += [
    ("JSON-LD JobPosting gives title, place, country", lambda: (str(jr.jsonld_job(LD)), ""),
     {str({"title": "Data Scientist 1", "desc": "Python and SQL", "loc": "St. Louis, MO, US", "country": "US"})}),
    ("Workday requests share one limit per host", lambda: (str(jr.host_sem("https://mgb.wd1.myworkdayjobs.com/x") is
                                                             jr.host_sem("https://cmu.wd1.myworkdayjobs.com/y")), ""), {"True"}),
    ("non-Workday hosts are not limited", lambda: (str(jr.host_sem("https://boards-api.greenhouse.io/v1")), ""), {"None"}),
    ("iCIMS boards re-seed under the sitemap key", lambda: (jr.board_key({"ats": "icims", "slug": "us-erac.icims.com", "site": ""}), ""),
     {"icims:us-erac.icims.com::sitemap"}),
    ("other boards keep their key", lambda: (jr.board_key({"ats": "workday", "slug": "cmu.wd115", "site": "CMU"}), ""), {"workday:cmu.wd115:CMU"}),
    ("paid lane defaults to hiring systems JobRadar cannot read", lambda: (str("taleo" in jr.FANTASTIC_ATS and "workday" not in jr.FANTASTIC_ATS), ""), {"True"}),
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
