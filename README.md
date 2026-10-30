# JobRadar v3: every relevant US posting, as early as possible, without using Claude

## How it covers the market (four layers)
| Layer | What it reads | Speed | Cost |
|---|---|---|---|
| 1. Company boards | ~4,800 boards read directly from their hiring systems (Workday, Oracle, Greenhouse, Ashby, Lever, iCIMS, SmartRecruiters, Workable, Rippling, BambooHR), plus Amazon, Google, Netflix, TikTok and Bloomberg | ≤30 min after posting | free |
| 2. Your alert emails | LinkedIn, Indeed, Glassdoor, HiringCafe and Jobright alerts forwarded to a jobs-only inbox. This catches everything else: Microsoft, Meta, Apple, Taleo/SuccessFactors/Phenom companies, LinkedIn-only and recruiter posts | as fast as each site's alerts | free |
| 3. Coverage audit | Every relevant alert posting is checked against what layer 1 already had: % caught and how many minutes earlier. Companies it missed go to `out/missing_companies.csv`, so you can add their boards | daily number in `out/latest.md` | free |
| 4. Paid gap-filler (optional) | fantastic.jobs feed via Apify: 275k+ career sites on 58 hiring systems, including Taleo, SuccessFactors, Phenom, Eightfold, Apple, Meta, Google and Amazon, filtered to US, 0–2 years and your titles | jobs land within ~3 h, run every 6 h | ~$0.004–0.012 per job; capped |

**Turn on layer 4 only if layer 3 shows coverage below 95% after a week.** The number tells you whether the money is needed.

---

## Deploy (about 40 minutes)

### 1. Phone alerts (3 min)
Install **ntfy** (free). Tap **+ → Subscribe to topic** and choose a long random name, e.g. `aryan-radar-8k2m4q7x`. Keep it private.

### 2. GitHub repo (10 min)
1. github.com → **+ → New repository** → name it `jobradar` → **Public** (Actions minutes are unlimited on public repos; private repos get 2,000 a month, which is not enough here). The repo holds only code and public job postings. Every password stays in Secrets.
2. Click **uploading an existing file** and drag in `jobradar.py`, `alerts.py`, `companies.csv`, `sponsors.csv`, `fantastic_orgs.txt`, `sponsor_targets.csv`, `discover.py`, `build_sponsors.py`, `voice_check.py` and `README.md`. Click **Commit changes**. (Do not upload the `Sample` folders.)
3. **Add file → Create new file**, name it `.github/workflows/jobradar.yml`, paste in the contents of `jobradar-workflow.yml`, then **Commit**.
4. **Settings → Actions → General → Workflow permissions → Read and write** → Save.
5. **Settings → Secrets and variables → Actions → New repository secret**: `NTFY_TOPIC` = your topic.

### 3. Alert inbox (15 min, free, strongly recommended)
1. Create a new Gmail account just for alerts, e.g. `aryan.jobalerts@gmail.com`. That way JobRadar never touches your main inbox.
2. In the new account: **Google Account → Security → 2-Step Verification** (turn on), then search **App passwords** and create one called `jobradar`. Copy the 16-character password.
3. In your **main** Gmail: **Settings → Forwarding and POP/IMAP → Add a forwarding address** → the new address (confirm it from the new inbox). Then **Settings → Filters → Create filter**:
   - From: `jobalerts-noreply@linkedin.com OR alert@indeed.com OR noreply@glassdoor.com OR ali@hiring.cafe OR jobright.ai`
   - → **Forward it to** the new address (keep a copy in your inbox if you like).
4. Add two more secrets to the repo: `ALERTS_IMAP_USER` = the new address, `ALERTS_IMAP_PASSWORD` = the app password.
5. **Fix your alerts so they feed the audit well:**
   - **LinkedIn:** delete the alert that includes "Internship". Create one alert per title group (Data Analyst; Data Scientist; Business Intelligence Analyst; Quantitative/Risk Analyst; Research Analyst/Associate). For each: United States, Entry level + Associate, the most frequent email option, notifications on.
   - **Glassdoor:** your current alert is for **Remote, India**. Change it to **United States** or delete it.
   - **HiringCafe:** delete the **Software engineer** saved search, which mostly sends senior engineering jobs. Keep Data analyst and Data scientist.
   - **Indeed / Jobright** (optional): create the same title alerts with email on.

### 4. First run (5 min)
**Actions → jobradar → Run workflow**. Wait about 4 minutes for a green tick. You should get HOT pushes. `out/` then holds today's `jobs-…-hot.md`, `jobs-…-maybe.md` and, once alerts arrive, `jobs-…-alerts.md` and `coverage.csv`. If it is red, copy the error to Claude.

### 5. Paid gap-filler (optional, only after a week of coverage numbers)
1. Sign in at apify.com (you already have an account). Go to **Settings → API & Integrations** and copy your API token.
2. Add the repo secret `APIFY_TOKEN`. Optional: **Settings → Variables → New variable** `FANTASTIC_LIMIT` (jobs per run, default 60).
3. **What you pay for:** only jobs at the 602 proven entry-level H-1B sponsors JobRadar does not read directly (`fantastic_orgs.txt`: Citadel, Millennium, Meta, CVS/Aetna, Mass General, Johns Hopkins and others). Between them they file about 38% of the entry-level H-1Bs in your fields. Set the variable `FANTASTIC_ALL=1` to search every company instead (much more expensive).
4. **Cost cap:** it runs 4 times a day and bills at most 4 × limit jobs a day. With the default 60, that is at most 240 jobs a day, about $2.90 at the free/Starter price ($0.012 per job). The expected volume with the sponsor filter is roughly 20–60 jobs a day, about $8–23 a month. Check **Apify → Billing** after the first day.

---

## Daily routine
1. **Push arrives** → tap → read the posting on the employer's site.
2. **Once or twice a day**: download `out/jobs-<today>-hot.md` (plus `-alerts.md` if it has rows) and give it to the Job Tailoring chat with the batch prompt in `claude/job-pipeline-v3.md`.
3. **Monday**: open `out/latest.md` and look at the coverage line. For any company that keeps appearing in `out/missing_companies.csv`, ask Claude to add its board.

## Upkeep and tuning
- New companies: `python discover.py names.txt >> companies.csv`. For Workday, add `Company,workday,TENANT.wdN,SITE,,manual` from the careers URL `https://TENANT.wdN.myworkdayjobs.com/SITE`.
- New H-1B data each quarter (DOL LCA file): `python build_sponsors.py <files>.xlsx`, then upload `sponsors.csv`.
- Filters are plain word lists at the top of `jobradar.py`. Tell Claude a title that was wrongly kept or dropped and it will give you the one-line change.
- Microsoft and Qualcomm block automated reads of their career sites, so they reach you through layer 2 (LinkedIn alerts) or layer 4.
