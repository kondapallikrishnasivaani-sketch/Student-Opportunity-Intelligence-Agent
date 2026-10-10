"""Eligibility analyzer: infers eligibility signals from search-result text."""
from __future__ import annotations

import re

from models import Opportunity, StudentProfile
from utils import detect_deadline, graduation_years, has_term

OPP_TYPE_PATTERNS = {
    "Internship": [r"\binternship\b", r"\bintern\b", r"\binterns\b"],
    "Hackathon": [r"\bhackathon\b"],
    "Scholarship": [r"\bscholarship\b"],
    "Competition": [r"\bcompetition\b", r"\bcontest\b", r"\bchallenge\b"],
    "Workshop": [r"\bworkshop\b"],
    "Fellowship": [r"\bfellowship\b"],
}

NEGATIVE_YEAR_SIGNALS = [
    r"final\s*year", r"4th\s*year", r"graduating\s+2026", r"graduates?\s+of\s+2026",
    r"masters?\s+students?", r"m\.?\s*tech\s+students?", r"phd\s+students?",
    r"post\s*graduate", r"working\s+professionals?\s+only",
    r"experienced\s+professionals?", r"\d+\+?\s+years?\s+experience",
]

STUDENT_OK_SIGNALS = [
    r"undergraduate", r"b\.?\s*tech", r"b\.?\s*e", r"college\s+students?",
    r"students?\s+only", r"student\s+participants?",
    r"2nd\s*year", r"3rd\s*year", r"pre\s*final\s*year",
]

def classify_opportunity_type(title: str, snippet: str, prefer: list[str] | None = None) -> str:
    """Title wins over snippet; types the user asked for are tried first (a hackathon page that
    mentions internship prizes should stay a Hackathon when the user asked for hackathons)."""
    prefer = prefer or []
    order = prefer + [t for t in OPP_TYPE_PATTERNS if t not in prefer]
    for text in (title.lower(), f"{title} {snippet}".lower()):
        for opp_type in order:
            if any(re.search(p, text) for p in OPP_TYPE_PATTERNS[opp_type]):
                return opp_type
    return "Unknown"

def detect_organization(title: str, source_domain: str) -> str:
    if title:
        cleaned = re.sub(
            r"\s*(\d{4}|internship|hackathon|scholarship|competition|workshop|fellowship|programme|program|registration|apply|applications).*",
            "", title, flags=re.IGNORECASE,
        ).strip()
        first = cleaned.split(":")[0].split("|")[0].split(" - ")[0].strip()
        tokens = first.split()
        if 1 <= len(tokens) <= 4 and tokens[0].lower() not in {"find", "best", "top", "list"}:
            return first
    return source_domain or ""

def analyze_eligibility(opp: Opportunity, profile: StudentProfile) -> Opportunity:
    text = f"{opp.title} {opp.snippet}".lower()
    concerns: list[str] = []

    student_ok = any(re.search(p, text) for p in STUDENT_OK_SIGNALS)
    negative_hits = [p for p in NEGATIVE_YEAR_SIGNALS if re.search(p, text)]
    gy = graduation_years(text)
    grad_mismatch = bool(gy) and not any(abs(y - profile.graduation_year) <= 1 for y in gy)

    branch_terms = {
        "cse": [r"computer science", r"\bcse\b", r"b\.?\s*tech\s+cse", r"cs\s+students"],
        "it": [r"information technology", r"it\s+students"],
        "ece": [r"electronics", r"\bece\b", r"ece\s+students"],
        "eee": [r"electrical", r"\beee\b"],
        "mech": [r"mechanical", r"\bmech\b"],
    }
    branch_ok_terms = branch_terms.get(profile.branch.lower(), [rf"\b{re.escape(profile.branch.lower())}\b"])
    branch_ok = any(re.search(p, text) for p in branch_ok_terms)

    loc_lower = (profile.location or "").lower()
    location_ok = loc_lower and (loc_lower in text or "remote" in text or "online" in text)

    skills_matched = [s for s in profile.skills if has_term(s, text)]
    opp.matched_skills = skills_matched

    if negative_hits or grad_mismatch:
        opp.eligibility = "unlikely"
        if grad_mismatch:
            concerns.append(f"Opportunity appears to target {', '.join(map(str, gy))} graduates, you graduate around {profile.graduation_year}.")
        if any(re.search(p, text) for p in [r"final\s*year", r"4th\s*year"]):
            concerns.append("Opportunity appears to target final-year students.")
        if any(re.search(p, text) for p in [r"masters?\s+students?", r"m\.?\s*tech", r"phd"]):
            concerns.append("Opportunity may require postgraduate students.")
        if any(re.search(p, text) for p in [r"\d+\+?\s+years?\s+experience", r"experienced\s+professionals?"]):
            concerns.append("Opportunity may require prior work experience.")
        opp.eligibility_reason = "Potential mismatch detected from search snippet."
    elif student_ok and (skills_matched or branch_ok):
        opp.eligibility = "likely"
        opp.eligibility_reason = "Likely eligible based on available information."
    else:
        opp.eligibility = "unclear"
        opp.eligibility_reason = "Eligibility could not be fully verified from the search snippet."

    dl, confident = detect_deadline(f"{opp.title} {opp.snippet}")
    opp.deadline = dl
    opp.deadline_confident = confident

    expl_parts: list[str] = [
        f"You are a {profile.year} {profile.degree} {profile.branch} student "
        f"and this opportunity appears relevant to undergraduate students."
    ]
    if skills_matched:
        expl_parts.append(f"{', '.join(skills_matched[:3])} listed among matching signals.")
    if branch_ok:
        expl_parts.append(f"Branch ({profile.branch}) is referenced.")
    if location_ok:
        expl_parts.append(f"Location ({profile.location}) or remote/online participation is indicated.")
    opp.match_explanation = " ".join(expl_parts)

    if concerns:
        opp.potential_concern = " ".join(concerns) + " Verify on the official page."
    elif opp.eligibility == "unclear":
        opp.potential_concern = "Some eligibility requirements could not be confirmed from the search result. Check the official page."
    else:
        opp.potential_concern = "Always confirm full eligibility on the original opportunity page."

    return opp