"""JobRadar v2: polls ~5,000 company job boards directly (no Claude, no browser) and catches new entry-level
postings in Aryan's target roles within one sweep (30 min) of publication.

Run:   python jobradar.py               one sweep, 24-hour window (schedule every 30 min)
       python jobradar.py --dry-run     no push, no state update
       python jobradar.py --only greenhouse,ashby   limit to some ATS types (testing)
Env:   NTFY_TOPIC=<secret topic>        phone push via the free ntfy app (optional)
Files: companies.csv (company,ats,slug,site,lca)  state.json  sponsors.csv (optional)
Out:   out/jobs-YYYY-MM-DD.md  full JDs of every kept posting today (the file you hand to Claude)
       out/latest.md  last sweep summary     out/history.csv  posting-time log
"""
import csv, json, os, re, time, html, argparse, urllib.request, urllib.error, urllib.parse, concurrent.futures as cf
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 JobRadar/2",
      "Accept": "application/json, text/html;q=0.9"}
ET = timezone(timedelta(hours=-4))
WINDOW_H = 24

# ---------------- targeting ----------------
TITLE_OK = re.compile(
    r"\banalyst\b|analytics|business intelligence|\bbi\b|decision scien|data scien|machine learning|\bml\b|\bai\b|"
    r"applied scien|research (associate|assistant|professional|specialist|scientist|fellow)|predoc|pre-doc|statistic|"
    r"biostatistic|econometric|economist|quantitative|\bquant\b|model (risk|validation|evaluation|developer)|"
    r"risk (model|scientist)|data engineer|analytics engineer|data (quality|validation|governance|specialist|associate)|"
    r"insights|reporting|forecast|actuarial analyst|strategy (associate|analytics)|evaluation|\bllms?\b|\bnlp\b|"
    r"new grad|early career|graduate program|rotational|development program|associate,? data|junior data", re.I)
CORE = re.compile(  # his target families: these can be HOT; any other TITLE_OK match is "broad" (max MAYBE)
    r"data (analyst|scien|engineer|analytics|quality|validation)|business intelligence|\bbi (analyst|developer|engineer)|"
    r"analytics (analyst|engineer|associate|specialist|consultant)|(decision|product|marketing|growth|insights|reporting|pricing|"
    r"investment|portfolio|performance|research|statistical|quantitative|risk|credit risk|market risk|fraud|model risk|"
    r"healthcare data|financial data|strategy) analy|decision scien|quantitative|\bquant\b|model (risk|validation|development)|"
    r"risk (model|analytics|scien)|machine learning|\bml\b|applied scien|\bai (engineer|scientist|evaluation)|\bllms?\b|\bnlp\b|"
    r"statistician|biostatistic|econometric|economist|research (associate|assistant|professional|data|scientist)|predoc|pre-doc|"
    r"analytics|data science|\bai/ml\b", re.I)
TITLE_BAD = re.compile(
    r"senior|\bsr\.?\b|\blead\b|leader|expert|\bavp\b|manager|director|principal|staff|\bhead\b|\bvp\b|vice president|"
    r"\bchief\b|partner\b|intern\b|interns\b|internship|co-op|\bcoop\b|summer 20|\bii\b|\biii\b|\biv\b|level [2-5]|"
    r"\b[2-5]\b(?!\d)|architect|sales|recruit|counsel|attorney|paralegal|account exec|nurse|\brn\b|physician|pharmac|"
    r"security analyst|cyber|soc analyst|threat|penetration|help ?desk|service desk|desktop|network|technician|"
    r"mechanic|warehouse|driver|cashier|clinical (research )?coordinator|post-?doc|student|apprentice|"
    r"\((d/f/m|m/w/d|f/m/d|w/m/d|h/f)\)|professor|faculty|lecturer|teacher|"
    r"software engineer(?!.*(data|ml|machine|ai\b))|firmware|hardware|embedded|electrical|mechanical|chemist|circuit|analog|"
    r"semiconductor|silicon|asic|fpga|\brf\b|antenna|verification engineer|loan (officer|processor|closer|servicing)|fulfillment|"
    r"real estate|payroll|accounts payable|tax\b|audit(or)?\b|underwrit|claims|loan officer|collector|customer service|"
    r"molecular|biolog|clinical research|wet lab|assay|\bcell\b|chemistry|genomic|histolog|field research|"
    r"temporary|temp\b|part[- ]time|seasonal|volunteer|visiting|trade finance|transportation|logistics|supply chain|"
    r"procurement|hr analyst|human resources|benefits analyst|compensation analyst|\bit analyst|application analyst|"
    r"\berp\b|oracle (technical|functional)|salesforce|servicenow|sap\b|business systems analyst|product owner|scrum", re.I)
US_HINT = re.compile(r"united states|\bus\b|\busa\b|u\.s\.|remote|new york|boston|"
    r"chicago|san francisco|seattle|austin|dallas|houston|atlanta|denver|philadelphia|charlotte|miami|los angeles|"
    r"washington|pittsburgh|minneapolis|phoenix|detroit|columbus|nashville|raleigh|salt lake|san diego|san jose|"
    r"jersey|princeton|stamford|greenwich|cambridge|baltimore|richmond|tampa|orlando|st\.? louis|kansas city|"
    r"cleveland|cincinnati|indianapolis|milwaukee|omaha|portland|sacramento|las vegas|irvine|plano|wilmington|"
    r"hartford|providence|ann arbor|madison|durham|new haven|rochester|buffalo|albany|ohio|texas|california|"
    r"florida|illinois|massachusetts|virginia|carolina|georgia|pennsylvania|michigan|minnesota|colorado|arizona", re.I)
STATE = re.compile(r"(?:^|,\s*|\s)(AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|"
                   r"NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)(?:\b|$)")  # case-sensitive on purpose


def us_loc(t):
    if FOREIGN.search(t):  # "Bengaluru, IN": a state code alone can't outvote a foreign city
        return bool(US_HINT.search(t))
    return bool(US_HINT.search(t) or STATE.search(t))


FOREIGN = re.compile(r"london|india|bengaluru|bangalore|hyderabad|pune|mumbai|chennai|gurgaon|gurugram|noida|delhi|"
    r"singapore|hong kong|sydney|melbourne|shanghai|beijing|shenzhen|tokyo|seoul|taipei|amsterdam|dublin|toronto|"
    r"vancouver|montreal|ottawa|calgary|paris|berlin|munich|frankfurt|zurich|geneva|warsaw|krakow|prague|budapest|"
    r"bucharest|madrid|barcelona|lisbon|milan|rome|stockholm|copenhagen|oslo|helsinki|brussels|luxembourg|vienna|"
    r"mexico|brazil|são paulo|sao paulo|buenos aires|bogota|santiago|lima|manila|kuala lumpur|jakarta|bangkok|"
    r"ho chi minh|hanoi|tel aviv|dubai|riyadh|cairo|johannesburg|lagos|nairobi|canada|united kingdom|\buk\b|"
    r"england|scotland|ireland|germany|france|spain|italy|netherlands|poland|israel|philippines|australia|"
    r"new zealand|japan|china|korea|taiwan|vietnam|malaysia|indonesia|costa rica|argentina|colombia|chile|"
    r"portugal|greece|romania|hungary|czech|slovakia|ukraine|turkey|egypt|pakistan|sri lanka|bangladesh|nigeria|kenya|"
    r"south africa|switzerland|austria|belgium|denmark|sweden|norway|finland|\bemea\b|\bapac\b|\blatam\b", re.I)

BLOCK_RE = re.compile("|".join([
    r"u\.?s\.? citizens? only", r"must be a u\.?s\.? citizen", r"u\.?s\.? citizenship (is )?required",
    r"(united states|u\.?s\.?) citizens? or (lawful )?permanent residents?", r"citizenship is required",
    r"(will not|won'?t|cannot|can ?not|unable to|does not|do not|not able to|is not able to|are not able to)( be able to)? "
    r"(provide |offer |support |consider |sponsor )?(any )?(immigration |visa |employment |work )*(visa )?sponsor",
    r"not (be )?(able to )?sponsor", r"no (immigration |visa )?sponsorship", r"sponsorship (is )?not (available|provided|offered)",
    r"without (the need for )?(current or future |now or in the future )?(employer |visa )?sponsorship",
    r"(active |current |obtain a |eligible for a )?(secret|top secret|ts/sci|security) clearance", r"clearance (is )?required",
    r"\bitar\b", r"export control", r"green card holders?", r"not eligible for (opt|cpt|stem opt)",
    r"(opt|cpt) (candidates )?(are )?not (eligible|accepted|considered)"]), re.I)
YOE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(?:\d{1,2})?\s*\+?\s*years?", re.I)

TECH = ["python", "sql", " r ", " r,", "statistic", "machine learning", "tableau", "power bi", "excel", "spark", "aws",
        "pandas", "regression", "forecast", "time series", "bigquery", "gcp", "postgres", "scikit", "pytorch", "tensorflow",
        "econometric", "probability", "a/b test", "hypothesis test", "dashboard", "etl", "data visualization", "llm", "nlp"]
DOMAIN = ["risk", "credit", "fraud", "model validation", "model risk", "backtest", "portfolio", "quantitative", "fx",
          "futures", "trading", "derivatives", "monte carlo", "healthcare", "research", "publication", "data quality",
          "validation", "calibration", "segmentation", "cohort", "kpi", "reporting", "data cleaning", "pipeline",
          "xgboost", "random forest", "classification", "deep learning", "docker", "kubernetes", "git", "lambda", "athena"]
LACK = ["sas", "snowflake", "databricks", "airflow", "dbt", "looker", "java", "c\\+\\+", "scala", "kafka", "hadoop",
        "salesforce", "sap", "alteryx", "qlik", "matlab", "azure", "ssis", "informatica", "cfa", "actuar", "kdb", "golang",
        "phd required", "ph\\.d\\. required"]


def fit_estimate(text):
    t = " " + re.sub(r"\s+", " ", text.lower()) + " "
    tech = sorted({k.strip(" ,") for k in TECH if k in t})
    dom = sorted({k for k in DOMAIN if k in t})
    lack = sorted({k.replace("\\", "") for k in LACK if re.search(r"\b" + k, t)})
    if not tech:
        return 0, dom, lack
    got = 2 * len(tech) + len(dom)
    return min(95, round(100 * got / (got + 3 * len(lack) + 6))), tech + dom, lack


def min_yoe(text):
    nums = [int(m.group(1)) for m in YOE_RE.finditer(text) if int(m.group(1)) <= 15]
    return min(nums) if nums else None


# ---------------- http helpers ----------------
import threading
LIMIT = {"workable": threading.Semaphore(2), "rippling": threading.Semaphore(4), "bamboohr": threading.Semaphore(4)}


def get(url, data=None, timeout=25, raw=False, extra=None):
    for attempt in range(3):
        try:
            return _get(url, data, timeout, raw, extra)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(4 * (attempt + 1)); continue
            raise
        except (TimeoutError, ConnectionResetError, urllib.error.URLError):
            if attempt < 2:
                time.sleep(2); continue
            raise


def _get(url, data=None, timeout=25, raw=False, extra=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={**UA, **({"Content-Type": "application/json"} if data is not None else {}), **(extra or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    return b.decode("utf-8", "replace") if raw else json.loads(b)


def iso(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None


def strip(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(h))).strip()


def J(**k):  # job record; detail = callable or None; dated = True if `posted` is trustworthy
    k.setdefault("desc", ""); k.setdefault("detail", None); k.setdefault("dated", True)
    return k


# ---------------- fetchers (list stage; descriptions fetched later only for matches) ----------------
def greenhouse(c, cut):
    s = c["slug"]
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs").get("jobs", []):
        yield J(title=j["title"], location=(j.get("location") or {}).get("name", ""), url=j["absolute_url"],
                posted=iso(j.get("first_published") or j.get("updated_at")),
                detail=lambda i=j["id"]: strip(get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs/{i}").get("content")))


def lever(c, cut):
    for j in get(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json"):
        cat = j.get("categories") or {}
        yield J(title=j["text"], location=f"{cat.get('location','')} {' '.join(cat.get('allLocations') or [])} {j.get('country','')}",
                url=j["hostedUrl"], posted=datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc),
                desc=(j.get("descriptionPlain") or "") + " " + " ".join(strip(l.get("content")) for l in j.get("lists", [])) +
                " " + (j.get("additionalPlain") or ""))


def ashby(c, cut):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}").get("jobs", []):
        if not j.get("isListed", True):
            continue
        a = (j.get("address") or {}).get("postalAddress") or {}
        loc = " ".join([j.get("location", ""), a.get("addressCountry", "")] + [x.get("location", "") for x in j.get("secondaryLocations") or []])
        yield J(title=j["title"], location=loc + (" remote" if j.get("isRemote") else ""), url=j["jobUrl"],
                posted=iso(j.get("publishedAt")), desc=j.get("descriptionPlain") or strip(j.get("descriptionHtml")))


def smartrecruiters(c, cut):
    s = c["slug"]
    for j in get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100&country=us").get("content", []):
        loc = j.get("location") or {}
        def d(i=j["id"]):
            x = (get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings/{i}").get("jobAd") or {}).get("sections") or {}
            return " ".join(strip((x.get(k) or {}).get("text")) for k in ("jobDescription", "qualifications", "additionalInformation"))
        yield J(title=j["name"], location=f"{loc.get('city','')} {loc.get('region','')} {loc.get('country','')} {'remote' if loc.get('remote') else ''}",
                url=f"https://jobs.smartrecruiters.com/{s}/{j['id']}", posted=iso(j.get("releasedDate")), detail=d)


def workday(c, cut):
    tenant, wd = c["slug"].split(".")
    base, site = f"https://{tenant}.{wd}.myworkdayjobs.com", c["site"]
    for off in range(0, 400, 20):  # empty search is sorted newest first: stop at the first older posting
        d = get(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": off, "searchText": ""})
        posts = d.get("jobPostings", [])
        for j in posts:
            p = (j.get("postedOn") or "").lower()
            if "today" in p:
                age = 0
            elif "yesterday" in p:
                age = 1
            else:
                return
            yield J(day_only=True, title=j.get("title", ""), location=j.get("locationsText", ""), url=f"{base}/{site}{j['externalPath']}",
                    posted=datetime.now(timezone.utc) - timedelta(hours=12 if age == 0 else 23),
                    detail=lambda p=j["externalPath"]: strip(get(f"{base}/wday/cxs/{tenant}/{site}{p}")["jobPostingInfo"].get("jobDescription")))
        if len(posts) < 20:
            return


def oracle(c, cut):
    host, site = c["slug"], c["site"]
    api = f"https://{host}/hcmRestApi/resources/latest"
    for off in range(0, 300, 25):
        q = f"{api}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={site},facetsList=NONE,limit=25,offset={off},sortBy=POSTING_DATES_DESC"
        items = get(q).get("items") or [{}]
        reqs = items[0].get("requisitionList") or []
        for j in reqs:
            posted = iso(j.get("PostedDate"))
            if posted and posted < cut - timedelta(hours=24):  # date-only field: allow one extra day, gate later
                return
            def d(i=j["Id"]):
                x = (get(f'{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22{i}%22,siteNumber={site}').get("items") or [{}])[0]
                return " ".join(strip(x.get(k)) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr", "CorporateDescriptionStr"))
            yield J(day_only=True, title=j.get("Title", ""), location=f"{j.get('PrimaryLocation','')} {j.get('PrimaryLocationCountry','')} " +
                    " ".join(x.get("Name", "") for x in j.get("secondaryLocations") or []),
                    url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{j['Id']}",
                    posted=(posted + timedelta(hours=16)) if posted else None, detail=d)  # date-only: assume midday ET
        if len(reqs) < 25:
            return


def workable(c, cut):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{c['slug']}?details=true")
    for j in d.get("jobs", []):
        yield J(day_only=True, title=j.get("title", ""), location=f"{j.get('city','')} {j.get('state','')} {j.get('country','')} {'remote' if j.get('telecommuting') else ''}",
                url=j.get("url") or j.get("shortlink", ""), posted=iso(j.get("published_on")) and iso(j.get("published_on")) + timedelta(hours=16),
                desc=strip((j.get("description") or "") + " " + (j.get("requirements") or "")))


def rippling(c, cut):  # no dates: new = not seen before (board seeded on first sweep)
    s = c["slug"]
    for page in range(0, 10):
        d = get(f"https://ats.rippling.com/api/v2/board/{s}/jobs?page={page}")
        for j in d.get("items", []):
            yield J(title=j.get("name", ""), location=" ".join(f"{x.get('name','')} {x.get('country','')}" for x in j.get("locations") or []),
                    url=j["url"], posted=None, dated=False,
                    detail=lambda u=j["url"]: strip(get(u, raw=True))[:15000])
        if page + 1 >= (d.get("totalPages") or 1):
            return


def bamboohr(c, cut):
    s = c["slug"]
    for j in get(f"https://{s}.bamboohr.com/careers/list").get("result", []):
        loc = j.get("location") or {}
        yield J(title=j.get("jobOpeningName", ""), location=f"{loc.get('city','')} {loc.get('state','')} {loc.get('addressCountry','')}",
                url=f"https://{s}.bamboohr.com/careers/{j['id']}", posted=None, dated=False,
                detail=lambda i=j["id"]: strip(((get(f"https://{s}.bamboohr.com/careers/{i}/detail").get("result") or {}).get("jobOpening") or {}).get("description")))


KEYWORDS = ("data", "analyst", "scientist", "quantitative", "research", "machine learning", "analytics", "risk")


def amazon(c, cut):  # amazon.jobs public search, newest first
    seen_ids = set()
    for kw in KEYWORDS:
        for off in range(0, 300, 100):
            d = get(f"https://www.amazon.jobs/en/search.json?base_query={urllib.parse.quote(kw)}&country%5B%5D=USA"
                    f"&sort=recent&result_limit=100&offset={off}")
            jobs = d.get("jobs", [])
            stop = False
            for j in jobs:
                p = iso_date(j.get("posted_date"))
                if p and p < cut - timedelta(hours=24):
                    stop = True; break
                if j.get("id_icims") in seen_ids:
                    continue
                seen_ids.add(j.get("id_icims"))
                yield J(day_only=True, title=j.get("title", ""), location=j.get("normalized_location") or j.get("location", ""),
                        url="https://www.amazon.jobs" + j.get("job_path", ""), posted=(p + timedelta(hours=16)) if p else None,
                        desc=strip(" ".join(str(j.get(k) or "") for k in ("description", "basic_qualifications", "preferred_qualifications"))))
            if stop or len(jobs) < 100:
                break


def google(c, cut):  # careers.google.com results page carries the job data as JSON (ds:1)
    seen_ids = set()
    for kw in ("data", "analyst", "scientist", "quantitative", "research"):
        for page in range(1, 6):
            h = get(f"https://www.google.com/about/careers/applications/jobs/results/?q={urllib.parse.quote(kw)}"
                    f"&location=United%20States&sort_by=date&page={page}", raw=True)
            i = h.find("AF_initDataCallback({key: 'ds:1'")
            if i < 0:
                break
            s = h.find("data:", i) + 5
            jobs = (json.loads(h[s:h.find(", sideChannel", s)]) or [[]])[0] or []
            stop = False
            for j in jobs:
                ts = (j[12] or [None])[0] if len(j) > 12 else None
                p = datetime.fromtimestamp(ts, timezone.utc) if ts else None
                if p and p < cut:
                    stop = True; break
                if j[0] in seen_ids:
                    continue
                seen_ids.add(j[0])
                locs = " ; ".join(x[0] for x in (j[9] or []) if x)
                desc = " ".join(strip((x or [None, ""])[1]) for x in (j[10], j[3], j[4], j[19]) if isinstance(x, list))
                yield J(title=j[1], location=locs, url=f"https://www.google.com/about/careers/applications/jobs/results/{j[0]}",
                        posted=p, desc=desc)
            if stop or len(jobs) < 20:
                break


def eightfold(c, cut):  # Eightfold public API (Netflix, Microsoft, Qualcomm, ...); slug = host, site = domain
    host, dom = c["slug"], c["site"]
    for start in range(0, 1000, 100):
        d = get(f"https://{host}/api/apply/v2/jobs?domain={dom}&sort_by=timestamp&start={start}&num=100")
        pos = d.get("positions", [])
        for j in pos:
            p = datetime.fromtimestamp(int(j.get("t_create") or 0), timezone.utc) if j.get("t_create") else None
            if p and p < cut:
                continue
            yield J(title=j.get("name", ""), location=" ; ".join(j.get("locations") or [j.get("location", "")]),
                    url=j.get("canonicalPositionUrl") or f"https://{host}/careers/job/{j['id']}", posted=p,
                    detail=lambda i=j["id"]: strip(get(f"https://{host}/api/apply/v2/jobs/{i}?domain={dom}").get("job_description")))
        if len(pos) < 100:
            return


def tiktok(c, cut):  # TikTok / ByteDance public job API; no posting date: new = not seen before
    site = c.get("site") or "tiktok"
    host = {"tiktok": "lifeattiktok.com", "bytedance": "jobs.bytedance.com"}.get(site, "lifeattiktok.com")
    seen_ids = set()
    for kw in KEYWORDS:
        d = get("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts",
                {"recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [], "location_code_list": [],
                 "keyword": kw, "limit": 100, "offset": 0},
                extra={"website-path": site, "Origin": f"https://{host}", "Referer": f"https://{host}/"})
        for j in (d.get("data") or {}).get("job_post_list", []):
            if j["id"] in seen_ids:
                continue
            seen_ids.add(j["id"])
            ci, chain = j.get("city_info") or {}, []
            while ci:
                chain.append(ci.get("en_name") or ""); ci = ci.get("parent") or {}
            yield J(title=j.get("title", ""), location=", ".join(chain), url=f"https://{host}/search/{j['id']}",
                    posted=None, dated=False, desc=(j.get("description") or "") + " " + (j.get("requirement") or ""))


def avature(c, cut):  # Avature career sites (Bloomberg, ...): HTML list, no dates: new = not seen before
    host = c["slug"]
    for kw in ("data", "analyst", "quantitative", "research"):
        page = get(f"https://{host}/careers/SearchJobs/?keyword={urllib.parse.quote(kw)}&jobRecordsPerPage=50", raw=True)
        for href, t in re.findall(r'<a[^>]+href="(https://[^"]+/careers/JobDetail/[^"]+)"[^>]*>\s*([^<]{3,160})', page):
            t = " ".join(t.split())
            if t.lower() in ("apply", "apply now", "view job"):
                continue
            yield J(title=t, location="", url=href, posted=None, dated=False, detail=lambda u=href: strip(get(u, raw=True))[:15000])


FANTASTIC_TITLES = ["data analyst", "data scientist", "data science", "business intelligence", "analytics", "decision scien:*",
                    "quantitative", "quant", "risk analyst", "credit risk", "market risk", "model risk", "model validation",
                    "fraud analyst", "research analyst", "research associate", "research assistant", "statistician",
                    "biostatistician", "machine learning", "applied scientist", "data engineer", "analytics engineer",
                    "economist", "predoctoral", "insights analyst", "reporting analyst", "pricing analyst", "investment analyst"]


def fantastic(c, cut):
    """fantastic.jobs career-site feed via Apify (paid, optional): 275k+ career sites incl. Taleo, SuccessFactors,
    Phenom, Eightfold, iCIMS, Oracle and Apple/Meta/Google/Amazon. Needs APIFY_TOKEN. Runs every 6 h for postings of the
    last ~7 h; FANTASTIC_LIMIT caps jobs per run, so the most it can bill per day is 4 x limit jobs."""
    tok = os.environ.get("APIFY_TOKEN")
    if not tok:
        return
    since = (datetime.now(timezone.utc) - timedelta(hours=float(os.environ.get("FANTASTIC_SINCE_H", "7")))).strftime("%Y-%m-%dT%H:%M:%S")
    inp = {"timeRange": "24h", "datePostedAfter": since, "limit": int(os.environ.get("FANTASTIC_LIMIT", "60")),
           "titleSearch": FANTASTIC_TITLES, "titleExclusionSearch": ["senior", "sr", "lead", "manager", "director", "principal",
           "staff", "intern", "internship", "head"], "locationSearch": ["United States"], "aiExperienceLevelFilter": ["0-2"],
           "removeAgency": True, "descriptionType": "text"}
    orgs = ROOT / "fantastic_orgs.txt"  # optional: pay only for jobs at proven entry-level H-1B sponsors
    if orgs.exists() and os.environ.get("FANTASTIC_ALL") != "1":
        inp["organizationSearch"] = [l.strip() for l in orgs.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = get("https://api.apify.com/v2/acts/fantastic-jobs~career-site-job-listing-api/run-sync-get-dataset-items"
                f"?token={tok}&timeout=280", inp, timeout=300)
    for x in items if isinstance(items, list) else []:
        yield J(company=x.get("organization") or "", title=x.get("title") or "",
                location=" ; ".join(x.get("locations_derived") or []) or str(x.get("locations_raw") or "")[:200],
                url=x.get("url") or "", posted=iso(x.get("date_posted")), desc=x.get("description_text") or "",
                via=f"fantastic.jobs/{x.get('source', '')}")


def iso_date(s):
    try:
        return datetime.strptime(str(s).strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def icims(c, cut):  # HTML search pages; no dates: new = not seen before
    host = c["slug"]
    for kw in ("analyst", "data", "research", "quantitative"):
        page = get(f"https://{host}/jobs/search?ss=1&searchKeyword={kw}&searchRelation=keyword_all&in_iframe=1", raw=True)
        for href, inner in re.findall(r'href="(https://[^"]+/jobs/\d+/[^"]+/job)\?in_iframe=1"[^>]*>(.*?)</a>', page, re.S):
            t = strip(inner) or urllib.parse.unquote(href.split("/")[-2]).replace("-", " ")
            yield J(title=t, location="", url=href, posted=None, dated=False,
                    detail=lambda u=href: strip(get(u + "?in_iframe=1", raw=True))[:15000])


FETCH = dict(greenhouse=greenhouse, lever=lever, ashby=ashby, smartrecruiters=smartrecruiters, workday=workday,
             oracle=oracle, workable=workable, rippling=rippling, bamboohr=bamboohr, icims=icims,
             amazon=amazon, google=google, eightfold=eightfold, tiktok=tiktok, avature=avature, fantastic=fantastic)


# ---------------- pipeline ----------------
def board_key(c):
    return f"{c['ats']}:{c['slug']}:{c.get('site','')}"


def scan(c, cut, seeded):
    out, err = [], None
    sem = LIMIT.get(c["ats"])
    if sem:
        sem.acquire()
    try:
        for j in FETCH[c["ats"]](c, cut):
            if not j["title"] or not TITLE_OK.search(j["title"]) or TITLE_BAD.search(j["title"]):
                continue
            loc = j["location"]
            if loc.strip() and FOREIGN.search(loc) and not us_loc(loc):
                continue
            if j["dated"] and j["posted"] and j["posted"] < cut:
                continue
            if not j["dated"] and not seeded:  # first look at an undated board: remember, don't alert
                j["seed_only"] = True
            j["company"], j["lca_col"] = j.get("company") or c["company"], c.get("lca", "")
            out.append(j)
    except Exception as e:
        err = f"{c['company']} ({board_key(c)}): {type(e).__name__} {str(e)[:70]}"
    finally:
        if sem:
            sem.release()
    return c, out, err


BOILER = re.compile(r"(is an equal (employment )?opportunity|equal opportunity employer|we are an equal|\beeo\b|"
                    r"reasonable accommodation|e-verify|know your rights|pay transparency nondiscrimination)", re.I)


def trim(t, cap=7000):
    m = BOILER.search(t, int(len(t) * 0.5))
    t = t[:m.start()] if m else t
    return t if len(t) <= cap else t[:cap] + " [...]"


def load_detail(j):
    if not j["desc"] and j["detail"]:
        try:
            j["desc"] = j["detail"]() or ""
        except Exception:
            pass
    j.pop("detail", None)
    return j


def sponsors():
    p = ROOT / "sponsors.csv"
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        d = {}
        for r in csv.DictReader(f):  # value = filings in his occupations, or 1 if the employer sponsors 5+ in any role
            n, anyn = int(r["lca_count"]), int(r.get("lca_any") or 0)
            k = norm(r["employer"])
            if n or anyn >= 5:
                d[k] = max(d.get(k, 0), n if n else -anyn)
        return d


def norm(s):
    s = re.sub(r"\b(inc|llc|l\.?l\.?c|corp|corporation|co|company|n\.?a|na|lp|l\.?p|ltd|plc|group|holdings?|the|usa|us|america)\b\.?", " ", s.lower())
    return re.sub(r"[^a-z0-9]", "", s)


def tkey(title):
    t = re.split(r"\s+[-–|]\s+|\s*\(", title.lower())[0]
    return re.sub(r"[^a-z0-9]", "", t)[:40]


def jkey(company, title):
    return norm(company)[:12] + "|" + tkey(title)


def classify(j, spons):
    text = j["title"] + " " + j["desc"]
    m = BLOCK_RE.search(text)
    if m:
        a = max(0, m.start() - 50)
        return "SKIP", f'eligibility: "...{text[a:m.end() + 30]}..."'
    y = min_yoe(j["desc"])
    j["yoe"] = y
    if y is not None and y >= 4:
        return "SKIP", f"asks {y}+ years"
    loc = j["location"] or ""
    if (FOREIGN.search(loc) and not us_loc(loc)) or (not us_loc(loc) and FOREIGN.search(j["title"] + " " + j["url"] + " " + j["desc"][:400])):
        return "SKIP", "outside US"
    fit, have, lack = fit_estimate(text)
    if y == 3:
        fit = min(fit, 55)
    j.update(fit=fit, have=have, lack=lack)
    k = norm(j["company"])
    col = str(j.get("lca_col") or "").strip().lower()
    lca = "cap-exempt" if col == "cap-exempt" else (int(col) if col.isdigit() else None)
    if lca is None and k:
        lca = spons.get(k) or next((v for kk, v in spons.items() if len(k) > 4 and kk.startswith(k)), None)
    j["lca"] = lca
    if len(j["desc"]) < 200:
        return "CHECK", "description not readable by the scanner; open the link"
    sponsor_ok = bool(lca) or not spons
    core = bool(CORE.search(j["title"]))
    tech = any(k in " " + j["desc"].lower() for k in ("python", "sql", " r ", "statistic", "machine learning", "tableau", "power bi"))
    j["scope"] = "core" if core else "broad"
    if core and tech and fit >= 55 and sponsor_ok:
        return "HOT", ""
    if (core and fit >= 40) or (not core and tech and fit >= 62 and sponsor_ok):
        return "MAYBE", ("" if sponsor_ok else "no H-1B filings found for this employer") + ("" if core else " broad title")
    return "LOW", ""


def ntfy(topic, title, msg, url=None, prio="default"):
    h = {"Title": title.encode("ascii", "ignore").decode(), "Priority": prio, "Tags": "briefcase"}
    if url:
        h["Click"] = url
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(), headers=h), timeout=15)
    except Exception as e:
        print("push failed:", e)


def et(d):
    return d.astimezone(ET).strftime("%b %d %H:%M ET") if d else "?"


def lca_text(v):
    if v == "cap-exempt":
        return "cap-exempt employer"
    if not v:
        return "none found (check myvisajobs)"
    return f"{v} in data/analytics/finance occupations" if v > 0 else f"0 in his occupations, {-v} in other roles"


def posted_text(j):
    if not j.get("dated") or not j.get("posted"):
        return "new since the previous sweep (board shows no date)"
    if j.get("day_only"):
        return j["posted"].astimezone(ET).strftime("%b %d (board gives the date only)")
    return et(j["posted"])


def entry(j, n):
    return (f"---\n\n## {n}. [{j['tier']}] {j['company']} | {j['title']}\n"
            f"- Link: {j['url']}\n- Location: {' '.join(j['location'].split()) or 'see posting'}\n- Posted: {posted_text(j)}\n"
            f"- Scanner fit: ~{j.get('fit')} | Min YOE: {j.get('yoe')} | H-1B (certified LCAs, Oct 2024-Dec 2025): {lca_text(j.get('lca'))}\n"
            f"- Title scope: {j.get('scope','-')} | Has: {', '.join(j.get('have', [])[:14]) or '-'} | Lacks: {', '.join(j.get('lack', [])) or '-'}"
            f"{'  | Note: ' + j['why'].strip() if j.get('why', '').strip() else ''}\n\n### Job description\n\n{trim(j['desc']).strip() or '(not readable; open the link)'}\n")


def render(day, rows, tier_set, label):
    rows = [r for r in rows if r["tier"] in tier_set]
    rows.sort(key=lambda r: (-(r.get("fit") or 0)))
    head = [f"# {label} postings for Aryan, {day} (JobRadar, posted in the last 24 h)\n",
            "Scanner fit is a keyword prefilter, not the Step 1 assessment. Eligibility wording was screened automatically; "
            "re-check it in Step 1.\n", "| # | Company | Title | Fit | H-1B | Posted |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        head.append(f"| {i} | {r['company']} | {r['title']} | {r.get('fit')} | {lca_text(r.get('lca'))} | {posted_text(r)} |")
    return "\n".join(head) + "\n\n" + "".join(entry(r, i) + "\n" for i, r in enumerate(rows, 1))


def audit_alerts(a, now, day, out, index, alerts_seen):
    """Pull LinkedIn/HiringCafe/Glassdoor/Indeed/Jobright alert emails. Relevant postings JobRadar never saw go to
    out/jobs-DAY-alerts.md (and missing_companies.csv); every relevant one is logged to coverage.csv."""
    if a.dry_run or not os.environ.get("ALERTS_IMAP_USER"):
        return ""
    try:
        import alerts
        items = alerts.fetch()
    except Exception as e:
        return f"Alert inbox: error {type(e).__name__}: {str(e)[:80]}"
    rel = []
    for x in items:
        if x["url"] in alerts_seen or not CORE.search(x["title"]) or TITLE_BAD.search(x["title"]):
            continue
        if x["location"] and FOREIGN.search(x["location"]) and not us_loc(x["location"]):
            continue
        alerts_seen[x["url"]] = now.isoformat()
        k = jkey(x["company"], x["title"])
        ck, tk = k.split("|")
        hit = index.get(k) or next((v for kk, v in index.items() if kk.split("|")[1] == tk and len(ck) >= 8
                                    and (kk.startswith(ck[:8]) or ck.startswith(kk.split("|")[0]))), None)
        x["caught"] = bool(hit)
        x["lead_min"] = round((x["received"] - iso(hit)).total_seconds() / 60) if hit else ""
        rel.append(x)
    if not rel:
        return "Alert inbox: no new relevant alert postings"
    cov = out / "coverage.csv"
    first = not cov.exists()
    with open(cov, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if first:
            w.writerow(["received_utc", "source", "company", "title", "caught_by_jobradar", "jobradar_lead_minutes", "url"])
        for x in rel:
            w.writerow([x["received"].isoformat(), x["source"], x["company"], x["title"], x["caught"], x["lead_min"], x["url"]])
    missed = [x for x in rel if not x["caught"]]
    if missed:
        mp = out / "missing_companies.csv"
        first = not mp.exists()
        with open(mp, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if first:
                w.writerow(["date", "company", "title", "source", "url"])
            for x in missed:
                w.writerow([day, x["company"], x["title"], x["source"], x["url"]])
        ap_ = out / f"jobs-{day}-alerts.md"
        new_file = not ap_.exists()
        with open(ap_, "a", encoding="utf-8") as f:
            if new_file:
                f.write(f"# Alert-only postings, {day}\n\nFound in your LinkedIn/HiringCafe/Glassdoor/Indeed/Jobright alert emails "
                        "but not on any JobRadar board. The description is not fetched: open the link, and paste the JD to "
                        "Claude if it looks right.\n\n| Source | Company | Title | Location | Link |\n|---|---|---|---|---|\n")
            for x in missed:
                f.write(f"| {x['source']} | {x['company']} | {x['title']} | {x['location']} | {x['url']} |\n")
    # rolling 7-day coverage
    rows = list(csv.DictReader(open(cov, encoding="utf-8")))
    wk = [r for r in rows if r["received_utc"] >= (now - timedelta(days=7)).isoformat()]
    hits = [r for r in wk if r["caught_by_jobradar"] == "True"]
    leads = sorted(int(r["jobradar_lead_minutes"]) for r in hits if str(r["jobradar_lead_minutes"]).lstrip("-").isdigit())
    med = leads[len(leads) // 2] if leads else None
    return (f"Coverage audit (7 days): JobRadar had {len(hits)}/{len(wk)} = {100 * len(hits) // max(1, len(wk))}% of relevant alert "
            f"postings; median {'lead' if (med or 0) >= 0 else 'lag'} {abs(med) if med is not None else '-'} min vs the alert email. "
            f"This sweep: {len(rel)} relevant alert postings, {len(missed)} not on JobRadar boards.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=WINDOW_H)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="", help="ATS types to leave out, e.g. workable")
    ap.add_argument("--delay", type=float, default=0, help="seconds between boards (slow lane for rate-limited ATS)")
    ap.add_argument("--workers", type=int, default=48)
    a = ap.parse_args()
    t0, now = time.time(), datetime.now(timezone.utc)
    cut = now - timedelta(hours=a.hours)
    only, skip = set(a.only.split(",")) - {""}, set(a.skip.split(",")) - {""}
    with open(ROOT / "companies.csv", newline="", encoding="utf-8") as f:
        companies = [r for r in csv.DictReader(f) if r.get("ats") in FETCH and not r["company"].startswith("#")
                     and (not only or r["ats"] in only) and r["ats"] not in skip
                     and (r["ats"] != "fantastic" or "fantastic" in only)]
    if a.delay:
        a.workers = 1
    sp = ROOT / "state.json"
    state = json.loads(sp.read_text()) if sp.exists() else {}
    seen, boards = state.get("seen", {}), state.get("boards", {})
    index, alerts_seen = state.get("index", {}), state.get("alerts_seen", {})
    spons = sponsors()

    found, errs = [], []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        def run(c):
            if a.delay:
                time.sleep(a.delay)
            return scan(c, cut, board_key(c) in boards)
        for c, out, err in ex.map(run, companies):
            found += out
            if err:
                errs.append(err)
            else:
                boards[board_key(c)] = now.isoformat()
    uniq, pair = {}, set()
    for j in found:
        p = (norm(j["company"]), j["title"].lower().strip())
        if j["url"] in uniq or p in pair:
            continue
        uniq[j["url"]] = j; pair.add(p)
    for j in uniq.values():  # every title-matched posting JobRadar has ever seen, for the coverage audit
        index.setdefault(jkey(j["company"], j["title"]), now.isoformat())
    new = [j for j in uniq.values() if j["url"] not in seen]
    alert = [j for j in new if not j.get("seed_only")]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        alert = list(ex.map(load_detail, alert))
    for j in alert:
        j["tier"], j["why"] = classify(j, spons)
    rank = {"HOT": 0, "CHECK": 1, "MAYBE": 2, "LOW": 3, "SKIP": 4}
    alert.sort(key=lambda j: (rank[j["tier"]], -(j.get("fit") or 0)))
    keep = [j for j in alert if j["tier"] in ("HOT", "CHECK", "MAYBE")]

    out = ROOT / "out"; out.mkdir(exist_ok=True)
    day = now.astimezone(ET).strftime("%Y-%m-%d")
    store = out / f"day-{day}.json"
    rows = json.loads(store.read_text()) if store.exists() and not a.dry_run else []
    for j in keep:
        r = {k: v for k, v in j.items() if k not in ("detail", "seed_only", "lca_col")}
        r["posted"] = j["posted"].isoformat() if j.get("posted") else None
        r["desc"] = trim(j["desc"])
        rows.append(r)
    for r in rows:
        r["posted"] = iso(r["posted"]) if isinstance(r["posted"], str) else r["posted"]
    suffix = "-dryrun" if a.dry_run else ""
    (out / f"jobs-{day}-hot{suffix}.md").write_text(render(day, rows, {"HOT", "CHECK"}, "HOT"), encoding="utf-8")
    (out / f"jobs-{day}-maybe{suffix}.md").write_text(render(day, rows, {"MAYBE"}, "MAYBE"), encoding="utf-8")
    if not a.dry_run:
        store.write_text(json.dumps([{**r, "posted": r["posted"].isoformat() if r["posted"] else None} for r in rows]), encoding="utf-8")
    daily = out / f"jobs-{day}-maybe.md"
    cov_line = audit_alerts(a, now, day, out, index, alerts_seen)
    took = time.time() - t0
    summ = [f"# Sweep {now.astimezone(ET):%Y-%m-%d %H:%M ET}: {len(companies)} boards, {len(alert)} new matches, "
            f"{len(keep)} kept, {len(errs)} board errors, {took:.0f}s\n", cov_line]
    for j in alert:
        summ.append(f"- [{j['tier']}] {j['company']} | {j['title']} | fit~{j.get('fit','-')} | {j['url']}" +
                    (f" | {j['why']}" if j.get("why") else ""))
    if errs:
        summ.append("\n## Board errors\n" + "\n".join("- " + e for e in sorted(errs)[:300]))
    (out / "latest.md").write_text("\n".join(summ), encoding="utf-8")
    print("\n".join(summ[:80]))
    if a.dry_run:
        return

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        for j in [j for j in keep if j["tier"] == "HOT"][:15]:
            ntfy(topic, f"HOT: {j['company']}", f"{j['title']}\nfit~{j['fit']}  H-1B: {lca_text(j.get('lca'))}  {j['location'][:50]}", j["url"], "high")
        rest = [j for j in keep if j["tier"] != "HOT"]
        if rest:
            ntfy(topic, f"+{len(rest)} more to review", "\n".join(f"{j['company']}: {j['title']}" for j in rest[:12]),
                 f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}/blob/main/out/{daily.name}" if os.environ.get("GITHUB_REPOSITORY") else None)
    for j in new:
        seen[j["url"]] = now.isoformat()
    old = (now - timedelta(days=90)).isoformat()
    old30 = (now - timedelta(days=30)).isoformat()
    sp.write_text(json.dumps({"seen": {k: v for k, v in seen.items() if v > old}, "boards": boards,
                              "index": {k: v for k, v in index.items() if v > old30},
                              "alerts_seen": {k: v for k, v in alerts_seen.items() if v > old30}}, indent=0))
    hist = out / "history.csv"
    first = not hist.exists()
    with open(hist, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if first:
            w.writerow(["found_utc", "posted_utc", "dated", "company", "title", "tier", "fit", "url"])
        for j in alert:
            w.writerow([now.isoformat(), j["posted"].isoformat() if j.get("posted") else "", j.get("dated"),
                        j["company"], j["title"], j["tier"], j.get("fit", ""), j["url"]])


if __name__ == "__main__":
    main()
