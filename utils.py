"""Utility helpers for normalization, deduplication, and text parsing."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

TRACKING_PARAMS = {"ref", "src", "source", "gclid", "fbclid", "trk", "trackingid", "refid", "mc_cid", "mc_eid"}

def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication: drop scheme, www/m, fragment, trailing slash, tracking params."""
    if not url:
        return ""
    url = url.strip()
    p = urlparse(url if "://" in url else f"https://{url}")
    host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = re.sub(r"/+$", "", p.path.lower())
    query = sorted(
        (k.lower(), v) for k, v in parse_qsl(p.query)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    )
    return host + path + (f"?{urlencode(query)}" if query else "")

def domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url if "://" in url else f"https://{url}").netloc
    except Exception:
        return ""
    netloc = netloc.lower().removeprefix("www.")
    return netloc

def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).strip()

def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    sa = set(normalize_title(a).split())
    sb = set(normalize_title(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def base_domain(domain: str) -> str:
    """Collapse subdomains: in.linkedin.com -> linkedin.com, foo.ac.in stays foo.ac.in."""
    parts = (domain or "").lower().removeprefix("www.").split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "ac", "org", "gov", "edu", "com", "nic"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else ".".join(parts)

def find_duplicate(opp, seen: dict):
    """Return the key of the already-seen entry that `opp` duplicates, or None.

    `seen` maps normalized_url -> (base_domain, normalized_title, index).
    """
    key = normalize_url(opp.url)
    if key in seen:
        return key
    base = base_domain(opp.source_domain)
    ntitle = normalize_title(opp.title)
    for s_key, s in seen.items():
        sim = title_similarity(ntitle, s[1])
        if base == s[0]:  # same site: ignore the site's own name in titles ("... | Evenbreak")
            jac, size, contain, _ = _core_sim(ntitle, s[1], {base.split(".")[0]})
            if sim > 0.7 or (size >= 2 and (jac >= 0.6 or contain == 1.0)):
                return s_key
            continue
        jac, size, contain, extra = _core_sim(ntitle, s[1])
        if (sim >= 0.9 and len(ntitle.split()) >= 4) or (size >= 2 and contain == 1.0 and extra <= 2):  # other site, same event
            return s_key
    return None

def is_duplicate(opp, seen: dict) -> bool:
    """Backwards-compatible wrapper: True if duplicate, otherwise registers opp in `seen`."""
    if find_duplicate(opp, seen) is not None:
        return True
    seen[normalize_url(opp.url)] = (base_domain(opp.source_domain), normalize_title(opp.title), len(seen))
    return False

PROFILE_PATH_PATTERNS = {
    "linkedin.com": [r"^/in/", r"^/pub/", r"^/profile/", r"^/company/", r"^/school/", r"^/groups/", r"^/feed/", r"^/showcase/"],
    "github.com": [r"^/[^/]+/?$"],                      # github.com/username
    "twitter.com": [r"^/[^/]+/?$"], "x.com": [r"^/[^/]+/?$"],
    "instagram.com": [r"^/[^/]+/?$"], "facebook.com": [r"^/[^/]+/?$"],
    "medium.com": [r"^/@[^/]+/?$"], "behance.net": [r"^/[^/]+/?$"],
    "naukri.com": [r"^/mnjuser/"], "devpost.com": [r"^/software/"], "unstop.com": [r"^/u/"],
}

# Forums, Q&A and social sites: discussion about opportunities, never the opportunity itself.
BLOCKED_DOMAINS = {
    # forums, Q&A, social
    "quora.com", "reddit.com", "facebook.com", "instagram.com", "pinterest.com", "tiktok.com", "youtube.com",
    "twitter.com", "x.com",
    # personal sites, portfolios and blogs: people who took part, not events you can join
    "github.com", "gitlab.com", "github.io", "vercel.app", "netlify.app", "pages.dev", "web.app",
    "firebaseapp.com", "herokuapp.com", "onrender.com", "wixsite.com", "carrd.co", "notion.site", "about.me",
    "linktr.ee", "behance.net", "dribbble.com", "medium.com", "dev.to", "hashnode.dev", "substack.com",
    "blogspot.com", "wordpress.com",
}
PERSONAL_TITLE = re.compile(r"\b(portfolio|resume|r[eé]sum[eé]|curriculum vitae|my profile|about me)\b", re.I)
PAST_ACHIEVEMENT = re.compile(r"\b(prize winner|1st prize|first prize|winner of|won\b|secured|finalist|runner[- ]?up|"
                              r"participated in|my (hackathon|project|experience))", re.I)
ACTIVE_WORDING = re.compile(r"\b(apply|register|registration|applications? (?:open|are|close)|last date|deadline|"
                            r"prize pool|join us|sign up|enrol+)\b", re.I)

def is_non_opportunity(url: str, title: str = "") -> bool:
    """True for personal profile pages and other results that are not opportunities."""
    p = urlparse(url if "://" in url else f"https://{url}")
    path = p.path.lower() or "/"
    domain = base_domain(p.netloc.lower())
    if domain in BLOCKED_DOMAINS:
        return True
    if PERSONAL_TITLE.search(title or ""):
        return True
    for dom, pats in PROFILE_PATH_PATTERNS.items():
        if domain == dom and any(re.search(pat, path) for pat in pats):
            return True
    # Person-style LinkedIn titles that slipped through, e.g. "Name - Student - College | LinkedIn"
    t = (title or "").lower()
    if (domain == "linkedin.com" and "/jobs" not in path and t.strip().endswith("| linkedin")
            and not re.search(r"hackathon|intern|scholarship|fellowship|competition|challenge", t)):
        return True
    return False

def detect_deadline(text: str) -> tuple[str | None, bool]:
    """Attempt to extract a deadline date from text. Returns (date_str, confident)."""
    if not text:
        return None, False
    text = text.replace("\n", " ")
    patterns = [
        r"(?:deadline|last\s+date|closing\s+date|apply\s+by|registration\s+(?:deadline|closes)|ends|expires|due)\s*[:\-]?\s*"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + "|".join(MONTHS.keys()) + r")\s*,?\s*\d{4})",
        r"(?:deadline|last\s+date|closing\s+date|apply\s+by|registration\s+(?:deadline|closes)|ends|expires|due)\s*[:\-]?\s*"
        r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + "|".join(MONTHS.keys()) + r")\s*,?\s*\d{4})",
        r"((?:"
        + "|".join(MONTHS.keys()) + r")\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            parsed = _parse_date(raw)
            if parsed:
                return parsed, True
    return None, False

def _parse_date(raw: str) -> str | None:
    raw = raw.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.strftime("%B %d, %Y")
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            d = datetime(c, b, a)
            return d.strftime("%B %d, %Y")
        except ValueError:
            try:
                d = datetime(c, a, b)
                return d.strftime("%B %d, %Y")
            except ValueError:
                return None
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(\d{4})", raw)
    if m:
        day, mon_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        mon = MONTHS.get(mon_name)
        if mon:
            try:
                return datetime(year, mon, day).strftime("%B %d, %Y")
            except ValueError:
                return None
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})", raw)
    if m:
        mon_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        mon = MONTHS.get(mon_name)
        if mon:
            try:
                return datetime(year, mon, day).strftime("%B %d, %Y")
            except ValueError:
                return None
    return None

def clean_snippet(text: str, maxlen: int = 350) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > maxlen:
        text = text[:maxlen].rsplit(" ", 1)[0] + "…"
    return text


def parse_posted_date(raw: str, today: date | None = None) -> str | None:
    """Convert SerpApi's `date` text ("3 days ago", "Sep 28, 2026") to ISO yyyy-mm-dd.

    Returns None when the text is missing or not understood. Relative dates are approximate
    (a month is counted as 30 days, a year as 365).
    """
    if not raw:
        return None
    today = today or date.today()
    t = raw.strip().lower()
    if t in {"today", "just now"}:
        return today.isoformat()
    if t == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago", t)
    if m:
        per = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
        return (today - timedelta(days=per * int(m.group(1)))).isoformat()
    parsed = _parse_date(raw)
    if parsed:
        return datetime.strptime(parsed, "%B %d, %Y").date().isoformat()
    return None


def has_term(term: str, text: str) -> bool:
    """Whole-term match, so skill "C" does not match every letter c, and "C" does not match "C++"."""
    term = (term or "").strip().lower()
    if not term:
        return False
    return re.search(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])", (text or "").lower()) is not None

OPPORTUNITY_HINTS = [
    r"apply", r"applications?", r"stipend", r"regist(?:er|ration|rations)", r"deadline",
    r"program(?:me)?", r"bootcamp", r"grants?", r"olympiad", r"codeathon", r"ctf\b",
    r"mentorship", r"trainee", r"summer of code", r"early careers?", r"prize", r"openings?",
    r"jobs?", r"hiring", r"careers?", r"step.*google",
]

def looks_like_opportunity(title: str, snippet: str, opp_type: str) -> bool:
    """A result must name a known opportunity type or use opportunity wording; otherwise it is noise."""
    if opp_type != "Unknown":
        return True
    text = f"{title} {snippet}".lower()
    return any(re.search(p, text) for p in OPPORTUNITY_HINTS)


# ---- request focus: make the typed request actually matter -------------------------------------
REQ_STOP = set("""a an and or the for of in on at to with without my me i we you your our is are be it its this that these those
find show give get list suggest recommend looking look want need please can could would should some any all more most best top good great
latest new current open available suitable suited ideal relevant matching match based eligible eligibility
no not prior previous work experience experienced years year yr yrs fresher freshers beginner beginners entry level
student students undergraduate undergraduates college university engineering btech b.tech be b.e degree branch
skills skill academic profile background
internship internships intern interns hackathon hackathons scholarship scholarships competition competitions
workshop workshops fellowship fellowships opportunity opportunities program programs programme job jobs role roles
remote online onsite hybrid paid free stipend summer winter india indian
cse ece eee mech civil aids it computer science codeathon codeathons contest contests""".split())
SYNONYMS = {"ml": ["machine learning"], "ai": ["artificial intelligence"], "js": ["javascript"],
            "dsa": ["data structures", "algorithms"], "nlp": ["natural language"], "cv": ["computer vision"],
            "web": ["web development", "frontend", "backend", "full stack"], "devops": ["dev ops"]}

def request_keywords(request: str) -> list[str]:
    """Meaningful topic words in the user's request, e.g. 'Python internships ...' -> ['python']."""
    out: list[str] = []
    for tok in re.findall(r"[a-z0-9+#.]+", (request or "").lower()):
        tok = tok.strip(".")
        if not tok or tok in REQ_STOP or tok.isdigit() or re.fullmatch(r"\d+(st|nd|rd|th)(-?year)?", tok):
            continue
        if len(tok) < 2 and tok not in {"c", "r"}:
            continue
        if tok not in out:
            out.append(tok)
    return out

def matches_request(title: str, snippet: str, keywords: list[str]) -> bool:
    """True when no keywords were given, or the result text mentions at least one of them."""
    if not keywords:
        return True
    text = f"{title} {snippet}"
    for k in keywords:
        if any(has_term(alt, text) for alt in [k, *SYNONYMS.get(k, [])]):
            return True
    return False

# ---- graduation year / outdated postings -------------------------------------------------------
GRAD_CONTEXT = [r"(?:graduat\w*|batch|pass(?:ing)?[\s-]?outs?|class)\s*(?:of|in|by|at|:|-)?\s*(20\d{2})",
                r"(20\d{2})\s*(?:batch|graduates?|passouts?|pass[\s-]?outs?)"]

def graduation_years(text: str) -> list[int]:
    t = (text or "").lower()
    return sorted({int(y) for p in GRAD_CONTEXT for y in re.findall(p, t)})

def is_outdated(title: str, snippet: str, posted_iso: str | None = None) -> bool:
    """Outdated: a year in the title / graduation wording is already past, or posted over a year ago."""
    today = date.today()
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", title or "")] + graduation_years(f"{title} {snippet}")
    if years and max(years) < today.year:
        return True
    if posted_iso:
        try:
            return (today - date.fromisoformat(posted_iso)).days > 365
        except ValueError:
            return False
    return False


def is_past_participant(title: str, snippet: str) -> bool:
    """Pages about someone's past result ("1st Prize Winner ...") rather than an event you can join."""
    text = f"{title} {snippet}"
    return bool(PAST_ACHIEVEMENT.search(text)) and not ACTIVE_WORDING.search(text)

# ---- smarter duplicate detection: same event, different title wording ---------------------------
GENERIC_WORDS = set("""hackathon hackathons internship internships program programme programs competition competitions contest
challenge registration register apply applications application open now for students student in the of and at to a an on by with
2025 2026 2027 2028 2029 2030 free online offline""".split())

def core_tokens(title: str, drop: set[str] | None = None) -> set[str]:
    drop = drop or set()
    return {w for w in normalize_title(title).split() if w not in GENERIC_WORDS and w not in drop and not w.isdigit() and len(w) > 1}

def _core_sim(a: str, b: str, drop: set[str] | None = None) -> tuple[float, int, float, int]:
    """(jaccard, smaller core size, containment, extra words) between two titles' core words."""
    ca, cb = core_tokens(a, drop), core_tokens(b, drop)
    if not ca or not cb:
        return 0.0, 0, 0.0, 99
    inter, small = len(ca & cb), min(len(ca), len(cb))
    return inter / len(ca | cb), small, inter / small, len(ca | cb) - small

# ---- which opportunity types did the request ask for? --------------------------------------------
TYPE_WORDS = {
    "Internship": r"\binterns?(?:hips?)?\b", "Hackathon": r"\b(?:hackathons?|codeathons?)\b",
    "Scholarship": r"\bscholarships?\b", "Competition": r"\b(?:competitions?|contests?)\b",
    "Workshop": r"\bworkshops?\b", "Fellowship": r"\bfellowships?\b",
}

def request_types(request: str) -> list[str]:
    t = (request or "").lower()
    return [k for k, p in TYPE_WORDS.items() if re.search(p, t)]