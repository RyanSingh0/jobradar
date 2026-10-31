"""Reads job-alert emails (LinkedIn, HiringCafe, Glassdoor, Indeed, Jobright) from a Gmail inbox over IMAP and turns
them into job records. JobRadar uses them two ways:
  1. postings that only exist on LinkedIn or job boards are added to out/jobs-DATE-alerts.md
  2. coverage audit: for every relevant alert posting, did JobRadar already have it, and how much earlier?

Env: ALERTS_IMAP_USER (e.g. aryan.jobalerts@gmail.com), ALERTS_IMAP_PASSWORD (a Google *app password*), optional
     ALERTS_IMAP_HOST (default imap.gmail.com). Read-only: messages are fetched with BODY.PEEK (nothing marked read).
"""
import email, imaplib, os, re, html
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

SENDERS = {"jobalerts-noreply@linkedin.com": "linkedin", "jobs-noreply@linkedin.com": "linkedin",
           "ali@hiring.cafe": "hiringcafe", "noreply@glassdoor.com": "glassdoor",
           "alert@indeed.com": "indeed", "donotreply@jobalert.indeed.com": "indeed", "jobright.ai": "jobright"}


def _text(msg):
    plain, htm = "", ""
    for part in msg.walk():
        ct = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        try:
            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if ct == "text/plain" and not plain:
            plain = body
        elif ct == "text/html" and not htm:
            htm = body
    return plain, htm


def parse_linkedin(plain, htm=""):
    out = []
    for block in re.split(r"\n-{10,}\n", plain):
        m = re.search(r"View job: (https://www\.linkedin\.com/comm/jobs/view/(\d+))", block)
        if not m:
            continue
        lines = [l.strip() for l in block[:m.start()].strip().splitlines() if l.strip()]
        lines = [l for l in lines if not l.lower().startswith("your job alert for")]
        if len(lines) >= 3:
            out.append(dict(title=lines[0], company=lines[1], location=lines[2],
                            url=f"https://www.linkedin.com/jobs/view/{m.group(2)}/"))
    return out


def parse_hiringcafe(plain, htm=""):
    out = []
    for m in re.finditer(r"\n\s*\d+\.\s+(.+?)\n\s*→\s*(\S+)\n\s*Company:\s*(.+?)\n\s*Location:\s*(.+?)\n", plain):
        out.append(dict(title=m.group(1).strip(), url=m.group(2).strip(), company=m.group(3).strip(), location=m.group(4).strip()))
    return out


def parse_glassdoor(plain, htm=""):
    out = []
    for m in re.finditer(r"\[\|(.+?)\]\((https://www\.glassdoor\.[^)]+jobListingId=(\d+)[^)]*)\)", plain, re.S):
        cells = [c.strip() for c in re.split(r"\|+", m.group(1)) if c.strip()]
        cells = [c for c in cells if c not in ("Easy Apply",) and not re.fullmatch(r"\d+d|Just posted|\d+h|30d\+", c)]
        if len(cells) >= 3:
            company = re.sub(r"\s+\d\.\d\s*★$", "", cells[0]).strip()
            out.append(dict(company=company, title=cells[1], location=cells[2], url=m.group(2)))
    return out


def parse_generic(plain, htm=""):
    """Indeed / Jobright fallback: pair each job link with the two text lines above it (title, company)."""
    out, src = [], plain or re.sub(r"<[^>]+>", "\n", html.unescape(htm))
    lines = [l.strip() for l in src.splitlines()]
    for i, l in enumerate(lines):
        m = re.search(r"(https?://\S*(indeed\.com/(rc/clk|viewjob|pagead)|jobright\.ai/jobs/info)\S*)", l)
        if m:
            prev = [x for x in lines[max(0, i - 6):i] if x and not x.startswith("http")]
            if len(prev) >= 2:
                out.append(dict(title=prev[-2], company=prev[-1], location="", url=m.group(1)))
    return out


PARSERS = {"linkedin": parse_linkedin, "hiringcafe": parse_hiringcafe, "glassdoor": parse_glassdoor,
           "indeed": parse_generic, "jobright": parse_generic}


def fetch(hours=26):
    user, pw = os.environ.get("ALERTS_IMAP_USER"), os.environ.get("ALERTS_IMAP_PASSWORD")
    if not (user and pw):
        return []
    box = imaplib.IMAP4_SSL(os.environ.get("ALERTS_IMAP_HOST", "imap.gmail.com"))
    box.login(user, pw)
    box.select("INBOX", readonly=True)
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%d-%b-%Y")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jobs = []
    for sender, src in SENDERS.items():
        typ, data = box.search(None, f'(SINCE {since} FROM "{sender}")')
        for num in (data[0].split() if typ == "OK" and data and data[0] else []):
            typ, msg_data = box.fetch(num, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            try:
                received = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc)
            except Exception:
                received = datetime.now(timezone.utc)
            if received < cutoff:
                continue
            plain, htm = _text(msg)
            for j in PARSERS[src](plain, htm):
                j.update(source=src, received=received)
                jobs.append(j)
    box.logout()
    return jobs
