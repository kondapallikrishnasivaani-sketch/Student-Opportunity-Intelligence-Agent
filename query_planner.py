"""Query planner: turns a student profile + natural-language request into SerpApi queries."""
from __future__ import annotations

import re

from models import StudentProfile
from utils import request_keywords, request_types

OPP_TYPE_PLURAL = {
    "Internship": "internships",
    "Hackathon": "hackathons",
    "Scholarship": "scholarships",
    "Competition": "competitions",
    "Workshop": "workshops",
    "Fellowship": "fellowships",
}

BRANCH_NAMES = {
    "cse": "Computer Science Engineering", "it": "Information Technology",
    "ece": "Electronics and Communication Engineering", "eee": "Electrical and Electronics Engineering",
    "mech": "Mechanical Engineering", "civil": "Civil Engineering",
    "aids": "Artificial Intelligence and Data Science",
}

EXCLUDE = "-site:linkedin.com/in -site:linkedin.com/pub"

def _year_numeral(year: str) -> str:
    m = {"1st year": "1st", "2nd year": "2nd", "3rd year": "3rd", "4th year": "4th"}
    return m.get(year.lower(), year)

def _grad_year(profile: StudentProfile) -> str:
    return str(profile.graduation_year)

def plan_queries(profile: StudentProfile, request: str, max_queries: int = 6) -> list[str]:
    """Generate a diverse set of SerpApi Google search queries from profile + request."""
    queries: list[str] = []
    request = (request or "").strip()
    year_token = _year_numeral(profile.year)
    grad_year = _grad_year(profile)
    skills_top = profile.skills[:3]
    skills_str = " ".join(skills_top) if skills_top else ""
    focus = request_keywords(request)
    if focus:  # the typed request beats the default profile skills
        skills_str = " ".join(focus[:3])
    interests_top = profile.interests[:2]
    interests_str = " ".join(interests_top) if interests_top else ""
    loc = profile.location or "India"
    branch = profile.branch or "CSE"
    branch = BRANCH_NAMES.get(branch.lower(), branch)  # "CSE" alone also means stock exchanges, schools, etc.
    degree = profile.degree or "BTech"
    types = request_types(request) or profile.opportunity_types or ["Internship", "Hackathon"]  # the request wins

    if request:
        base = request
        if loc.lower() not in base.lower():
            base = f"{base} {loc}"
        if str(grad_year) not in base:
            base = f"{base} {grad_year}"
        queries.append(base)

    for opp_type in types[:3]:
        plural = OPP_TYPE_PLURAL.get(opp_type, opp_type.lower() + "s")
        q = f"{year_token} year {degree} {branch} {plural} {skills_str} {loc} {grad_year}".strip()
        q = re.sub(r"\s+", " ", q)
        queries.append(q)

    if interests_str:
        q = f"{interests_str} {OPP_TYPE_PLURAL.get(types[0], 'opportunities')} students {loc} {grad_year}"
        queries.append(q)

    if skills_str:
        q = f"{skills_str} {OPP_TYPE_PLURAL.get(types[0], 'internships')} undergraduate {branch} {loc} {grad_year}"
        queries.append(q)

    q = f"student {OPP_TYPE_PLURAL.get(types[0], 'opportunities')} {branch} {loc} {grad_year}"
    queries.append(q)

    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = re.sub(r"\s+", " ", q.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(q)
    # Ask Google to leave out people's LinkedIn profiles; code-level filtering catches the rest.
    return [f"{x} {EXCLUDE}" for x in unique[:max_queries]]