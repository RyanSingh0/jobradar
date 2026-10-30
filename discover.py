"""Finds which ATS a company uses by probing the public board APIs with slug guesses.
Usage: python discover.py names.txt >> companies.csv      (one company name per line)
Workday is not guessable reliably: add those rows by hand as  Company,workday,tenant.wdN,SiteName
(copy tenant/wdN/site from the company's myworkdayjobs.com URL)."""
import re, sys, json, urllib.request, concurrent.futures as cf

def ok(url, key):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=12) as r:
            d = json.load(r)
            n = len(d.get(key, [])) if isinstance(d, dict) else len(d)
            return n
    except Exception:
        return -1

def guesses(name):
    base = re.sub(r"\b(inc|llc|corp|corporation|co|company|group|holdings|the|lp|l\.p\.|ltd)\b\.?", "", name.lower())
    a = re.sub(r"[^a-z0-9]", "", base); b = re.sub(r"[^a-z0-9]+", "-", base.strip()).strip("-")
    return list(dict.fromkeys([a, b, a + "careers", a + "jobs"]))

def probe(name):
    for s in guesses(name):
        for ats, url, key in (("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", "jobs"),
                              ("lever", f"https://api.lever.co/v0/postings/{s}?mode=json", None),
                              ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{s}", "jobs"),
                              ("smartrecruiters", f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1", "content"),
                              ("workable", f"https://apply.workable.com/api/v1/widget/accounts/{s}", "jobs")):
            n = ok(url, key)
            if n > 0:
                return f"{name},{ats},{s},"
    return f"# {name},NOT FOUND (likely Workday/iCIMS/Taleo: add by hand),,"

if __name__ == "__main__":
    names = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    with cf.ThreadPoolExecutor(12) as ex:
        for row in ex.map(probe, names):
            print(row, flush=True)
