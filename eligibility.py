"""eligibility.py: sentence-level work-authorization gate (10 Nov 2026).

Why: the old BLOCK_RE only caught "will not / cannot sponsor" verb patterns. Wellmark's posting said
"not considering applicants for this position that require any type of immigration sponsorship ... now or in the
future" and slipped through, and a card went to the tracker as "no sponsorship wording". This module reads EVERY
sentence that touches work authorization and classifies it, so new phrasings land in CHECK instead of passing.

verdict(text) -> ("BLOCK" | "CHECK" | "OK" | "NONE", [quoted sentences])
  BLOCK: the posting excludes candidates who need sponsorship now or later, OPT/CPT/STEM OPT, non-citizens,
         or needs a clearance.
  OK:    the posting says it will sponsor or consider sponsoring (and nothing blocks).
  CHECK: a sentence mentions sponsorship/authorization but the meaning is not certain: a human reads the quote.
  NONE:  no sentence mentions it (still read the full employer page before building).
Run `python3 eligibility.py` to run the regression tests.
"""
import re

TOPIC = re.compile(
    r"sponsor|immigra|\bvisa|h-?1b|\bopt\b|\bcpt\b|stem opt|work authori[sz]|employment authori[sz]|authori[sz]ed to work|"
    r"legally (authori[sz]ed|permitted|eligible) to work|eligib\w* to work|right to work|citizen|permanent resident|green card|"
    r"lawful permanent|security clearance|\bclearance\b|ts/sci|\bitar\b|export control|e-verify|i-983|moratorium|"
    r"u\.?s\.? person", re.I)

BLOCK = [
    # any negation near sponsorship / immigration support
    r"(not|no|never|unable|cannot|can't|won't|will not|does not|do not|is not|are not|isn't|aren't|without|nor)\b[^.;]{0,90}"
    r"(sponsor|immigration|visa|work authori[sz]ation (support|sponsorship))",
    r"(sponsor\w*|immigration support|visa support)[^.;]{0,60}\b(not|unavailable|no longer)\b[^.;]{0,20}"
    r"(available|provided|offered|possible|be considered|considered|supported)",
    r"not (be )?considering[^.;]{0,120}(sponsor|immigration|visa|authori[sz]ation)",
    r"(require|requiring|need|needing)[^.;]{0,40}(sponsor|immigration)[^.;]{0,120}(not|will not|cannot|ineligible|not eligible)",
    r"(not|in)eligible for[^.;]{0,40}(sponsor|visa|opt|cpt|stem opt|i-983)",
    r"(will not|won't|cannot|does not|do not|unable to)[^.;]{0,40}(support|sign|endorse)[^.;]{0,40}(opt|cpt|i-983|training plan)",
    r"(opt|cpt|stem opt|f-1|h-1b)[^.;]{0,40}(not|ineligible)[^.;]{0,20}(eligible|accepted|considered|supported)",
    r"moratorium[^.;]{0,80}(sponsor|visa|immigra)",
    r"(only|exclusively)[^.;]{0,40}(u\.?s\.? citizens?|united states citizens?|citizens? of the united states|permanent residents?|green card)",
    r"(u\.?s\.? citizens?|united states citizens?|citizens? of the united states)[^.;]{0,40}(only|required|is required|are required)",
    r"(must|required to|need to)[^.;]{0,20}be (a )?(u\.?s\.?|united states) citizen",
    r"(u\.?s\.?|united states) citizenship[^.;]{0,20}(is |are )?(required|needed|mandatory)",
    r"citizenship[^.;]{0,20}(is |are )?required",
    r"(must|required to|need to)[^.;]{0,30}(possess|hold|have|obtain|maintain)[^.;]{0,30}(security |secret |top secret |ts/sci )?clearance",
    r"(active|current|secret|top secret|ts/sci)[^.;]{0,15}clearance[^.;]{0,30}(required|needed|must)",
    r"clearance[^.;]{0,20}(is |are )?required",
    r"\bitar\b|u\.?s\.? person",
    r"authori[sz]ed to work in the (u\.?s\.?|united states)[^.;]{0,80}without[^.;]{0,40}(sponsor|visa)",
    r"(now|currently)[^.;]{0,20}(or|and)[^.;]{0,20}in the future[^.;]{0,60}(not|will not|cannot)",
]
OK = [
    r"(will|may|can|is able to|are able to|is willing to)[^.;]{0,20}(consider )?(sponsor|provide (visa |immigration )?sponsorship)",
    r"(sponsorship|visa support|immigration support)[^.;]{0,30}(is |may be |will be )?(available|offered|provided|supported)",
    r"we (do )?sponsor", r"open to (visa )?sponsorship", r"consider sponsoring",
    r"support[^.;]{0,40}(international (student )?(applicants|candidates)|opt|cpt|visa)",
]
# phrases that look like the topic but are not about the candidate's status
NOISE = re.compile(r"regardless of[^.;]{0,120}citizenship|without regard to[^.;]{0,160}citizenship|"
                   r"(race|religion|national origin|sex|gender|age|disability|veteran)[^.;]{0,120}citizenship|"
                   r"citizenship (status|or immigration status)[^.;]{0,60}(protected|discriminat)|"
                   r"equal (employment )?opportunity|e-verify (participat|employer)|participates in e-verify|"
                   r"good (corporate )?citizen|citizenship behavio", re.I)
SOFT = re.compile(r"\b(may|might) not\b|business needs?|case[- ]by[- ]case", re.I)
BLOCK_RX = [re.compile(p, re.I) for p in BLOCK]
OK_RX = [re.compile(p, re.I) for p in OK]
SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+|•|•|\s{3,}")


def sentences(text):
    return [s.strip() for s in SPLIT.split(text or "") if s and TOPIC.search(s)]


def verdict(text):
    hits = sentences(text)
    blocks, oks, unclear = [], [], []
    for s in hits:
        if NOISE.search(s) and not re.search(r"sponsor|clearance|must be|required|only", s, re.I):
            continue
        hard = any(r.search(s) for r in BLOCK_RX)
        if hard and SOFT.search(s) and not re.search(r"will not|cannot|won't|does not|do not|is not|are not|only|must", s, re.I):
            unclear.append(s)
        elif hard:
            blocks.append(s)
        elif any(r.search(s) for r in OK_RX):
            oks.append(s)
        elif re.search(r"sponsor|immigra|visa|h-?1b|opt\b|cpt\b|clearance|citizen|permanent resident|green card|"
                       r"moratorium|authori[sz]", s, re.I) and not NOISE.search(s):
            unclear.append(s)
    if blocks:
        return "BLOCK", blocks
    if unclear:
        return "CHECK", unclear + oks
    if oks:
        return "OK", oks
    return "NONE", []


# Real lines from postings and emails seen 26 Oct - 10 Nov 2026 (expected verdict, text)
TESTS = [
    ("BLOCK", "At this time, Wellmark is not considering applicants for this position that require any type of immigration sponsorship (additional work authorization or permanent work authorization) now or in the future to work in the United States."),
    ("BLOCK", "Candidate must be authorized to work in the US without company sponsorship. The company will not support the STEM OPT I-983 Training Plan endorsement for this position."),
    ("BLOCK", "This role is not eligible for work visa sponsorship."),
    ("BLOCK", "Due to a hiring moratorium on sponsorship for employment visa status this moratorium may affect our ability to employ you should you be selected as the final candidate."),
    ("BLOCK", "Applicants must be authorized to work in the U.S. and will not require sponsorship for themselves or their spouses now and in the future."),
    ("BLOCK", "Toyota does not offer sponsorship of job applicants for employment-based visas or any other work authorization for this role now or in the future."),
    ("BLOCK", "At this time, Capital One will not sponsor a new applicant for employment authorization, or offer any immigration related support for this position."),
    ("BLOCK", "Additionally, this position is only open to United States citizens or lawful permanent residents."),
    ("BLOCK", "US Citizenship is required."),
    ("BLOCK", "Applicants must possess an active Secret clearance."),
    ("BLOCK", "Visa sponsorship is not available for this position."),
    ("BLOCK", "We do not anticipate providing visa sponsorship for this position."),
    ("BLOCK", "This position is not eligible for employment visa sponsorship."),
    ("BLOCK", "We are unable to sponsor or take over sponsorship of an employment visa at this time."),
    ("BLOCK", "No H-1B sponsorship is available for this role."),
    ("BLOCK", "OPT and CPT candidates are not eligible for this position."),
    ("CHECK", "Visa sponsorship/support is based on business needs and may not be available for this position."),
    ("CHECK", "Applicants must be legally authorized to work in the United States."),
    ("OK", "Capital One will consider sponsoring a new qualified applicant for employment authorization for this position."),
    ("OK", "We support international student applicants (CPT/OPT)."),
    ("NONE", "All qualified applicants will receive consideration for employment without regard to race, color, religion, sex, national origin, citizenship status, disability or veteran status."),
    ("NONE", "We are an E-Verify employer. Equal opportunity employer including disability and veterans."),
    ("NONE", "Build dashboards in Power BI and Tableau for the spares supply chain team."),
]

if __name__ == "__main__":
    bad = 0
    for want, t in TESTS:
        got, q = verdict(t)
        ok = got == want
        bad += not ok
        print(("PASS" if ok else "FAIL"), want, "->", got, "|", t[:90])
    print(f"{len(TESTS) - bad}/{len(TESTS)} passed")
    raise SystemExit(1 if bad else 0)
