"""Finds which ATS a company uses by probing the public board APIs with slug guesses.
Usage: python discover.py names.txt >> companies.csv      (one company name per line)
       python discover.py --missing >> companies.csv      (companies from out/missing_companies.csv, the alert audit)
Workday is not guessable reliably: add those rows by hand as  Company,workday,tenant.wdN,SiteName
(copy tenant/wdN/site from the company's myworkdayjobs.com URL).

27 Nov 2026 upgrade (Wayflyer was missed because it was never in companies.csv):
- a hit is kept only when the board belongs to the company: the Greenhouse board name, the Ashby page title, the
  SmartRecruiters company name or (Lever, Workable) the posting text must contain the company's first two distinctive words.
  The old version kept the first slug that answered, so a one-word guess could land on another firm's board
  ("general", "national", "capital" all answer on Greenhouse or Lever).
- companies already in companies.csv (same ATS and slug, or same name) are skipped, so the output can be appended as-is.
- rows carry a source tag (discover-YYYY-MM-DD) so a later audit can find and drop them.
Rows a probe could not confirm are printed as comments for a person to check, never as live rows."""
import csv, html, re, sys, json, urllib.request, concurrent.futures as cf
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0"}
DROP = r"\b(inc|llc|l l c|corp|corporation|co|company|group|holdings?|the|lp|llp|ltd|limited|na|n a|usa|us|u s|of america|america|services?|technolog(?:y|ies)|international|global|financial|partners)\b"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return None


def words(name):
    s = re.sub(r"[.,'\"()/]", " ", name.lower().replace("&", " "))
    return [w for w in re.findall(r"[a-z0-9]+", re.sub(DROP, " ", s)) if len(w) >= 3]


def norm(name):
    return "".join(words(name))


def guesses(name):
    s = re.sub(r"[.,'\"()]", " ", name.lower().replace("&", " and "))
    s = re.sub(r"\b(inc|llc|l l c|corp|corporation|co|company|holdings|the|lp|llp|ltd|limited|usa|us)\b", " ", s)
    a = re.sub(r"[^a-z0-9]", "", s); b = re.sub(r"[^a-z0-9]+", "-", s.strip()).strip("-")
    w = words(name)
    return [g for g in dict.fromkeys([a, b, a + "careers", a + "jobs", w[0] if w else a]) if len(g) >= 3]


def belongs(name, text):
    """The company's first two distinctive words (or its only one) must all appear in the board's own name or text.
    One word was not enough: "General Hospital Corporation" matched a board called "General Interest"."""
    w = words(name)[:2]
    flat = re.sub(r"[^a-z0-9]", "", (text or "").lower())
    return bool(w and flat) and all(x in flat for x in w)


def probe(name):
    for s in guesses(name):
        r = get(f"https://boards-api.greenhouse.io/v1/boards/{s}")
        if r:
            board = json.loads(r).get("name", "")
            jobs = json.loads(get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs") or "{}").get("jobs", [])
            if jobs and belongs(name, board):
                return ("greenhouse", s, len(jobs))
        r = get(f"https://api.ashbyhq.com/posting-api/job-board/{s}")
        if r:
            jobs = json.loads(r).get("jobs", [])
            m = re.search(r"<title>(.*?)</title>", get(f"https://jobs.ashbyhq.com/{s}") or "", re.S)
            if jobs and belongs(name, html.unescape(m.group(1)) if m else ""):
                return ("ashby", s, len(jobs))
        r = get(f"https://api.lever.co/v0/postings/{s}?mode=json")
        if r and r.lstrip().startswith("[") and r.strip() != "[]":
            js = json.loads(r)
            if belongs(name, " ".join((p.get("descriptionPlain") or "")[:3000] + (p.get("additionalPlain") or "")[:2000] for p in js[:3])):
                return ("lever", s, len(js))
        r = get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=5")
        if r:
            c = json.loads(r).get("content", [])
            if c and belongs(name, (c[0].get("company") or {}).get("name", "")):
                return ("smartrecruiters", s, json.loads(r).get("totalFound", len(c)))
        r = get(f"https://apply.workable.com/api/v1/widget/accounts/{s}")
        if r:
            d = json.loads(r)
            if d.get("jobs") and belongs(name, d.get("name", "") + " " + d.get("description", "")):
                return ("workable", s, len(d["jobs"]))
    return None


def listed():
    rows = list(csv.DictReader(open(ROOT / "companies.csv", encoding="utf-8")))
    return {norm(r["company"]) for r in rows}, {(r["ats"], (r["slug"] or "").lower()) for r in rows}


if __name__ == "__main__":
    if sys.argv[1:] == ["--missing"]:
        names = [r["company"] for r in csv.DictReader(open(ROOT / "out" / "missing_companies.csv", encoding="utf-8"))]
    else:
        names = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    have_names, have_slugs = listed()
    for n in dict.fromkeys(names):
        if norm(n) in have_names:
            print(f"# {n},already in companies.csv", flush=True)
    names = [n for n in dict.fromkeys(names) if norm(n) and norm(n) not in have_names]
    tag = f"discover-{date.today().isoformat()}"
    with cf.ThreadPoolExecutor(12) as ex:
        for name, hit in zip(names, ex.map(probe, names)):
            if not hit:
                print(f"# {name},NOT FOUND or not confirmed (likely Workday/iCIMS/Taleo: add by hand),,", flush=True)
            elif (hit[0], hit[1]) in have_slugs:
                print(f"# {name},already listed as {hit[0]}/{hit[1]}", flush=True)
            else:
                have_slugs.add((hit[0], hit[1]))
                print(f"{name},{hit[0]},{hit[1]},,,{tag}", flush=True)
