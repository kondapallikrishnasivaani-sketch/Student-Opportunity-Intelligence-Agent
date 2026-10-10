"""Transparent relevance scoring. Total = 100 points across 6 explainable signals."""
from __future__ import annotations

import re
from datetime import datetime

from models import Opportunity, StudentProfile
from utils import has_term

MAXIMA = {
    "skills": 35, "academic_year": 20, "branch": 15,
    "opportunity_type": 15, "location": 10, "freshness": 5,
}

def score_opportunity(opp: Opportunity, profile: StudentProfile) -> Opportunity:
    text = f"{opp.title} {opp.snippet}".lower()
    breakdown: dict[str, int] = {}

    skills = [s.lower() for s in profile.skills]
    matched = [s for s in skills if has_term(s, text)]
    ratio = len(matched) / len(skills) if skills else 0.0
    breakdown["skills"] = round(ratio * MAXIMA["skills"])

    year_map = {"1st year": 1, "2nd year": 2, "3rd year": 3, "4th year": 4}
    yr_num = year_map.get(profile.year.lower(), 2)
    if re.search(r"undergraduate|college\s+students?|students?\s+only|b\.?\s*tech", text):
        breakdown["academic_year"] = MAXIMA["academic_year"]
    elif re.search(r"2nd\s*year|pre\s*final|3rd\s*year", text):
        breakdown["academic_year"] = MAXIMA["academic_year"] if yr_num <= 2 else 12
    elif re.search(r"final\s*year|4th\s*year", text):
        breakdown["academic_year"] = 5
    else:
        breakdown["academic_year"] = 8

    branch_terms = {
        "cse": [r"computer science", r"\bcse\b", r"b\.?\s*tech\s+cse", r"cs\s+students", r"software", r"programming"],
        "it": [r"information technology", r"it\s+students", r"software"],
        "ece": [r"electronics", r"\bece\b"],
        "eee": [r"electrical", r"\beee\b"],
        "mech": [r"mechanical", r"\bmech\b"],
    }
    bt = branch_terms.get(profile.branch.lower(), [rf"\b{re.escape(profile.branch.lower())}\b"])
    breakdown["branch"] = MAXIMA["branch"] if any(re.search(p, text) for p in bt) else 4

    if opp.opportunity_type in profile.opportunity_types:
        breakdown["opportunity_type"] = MAXIMA["opportunity_type"]
    elif opp.opportunity_type == "Unknown":
        breakdown["opportunity_type"] = 5
    else:
        breakdown["opportunity_type"] = 0

    loc = (profile.location or "").lower()
    if loc and (loc in text or "remote" in text or "online" in text or "india" in text):
        breakdown["location"] = MAXIMA["location"]
    else:
        breakdown["location"] = 2

    current_year = datetime.now().year
    if opp.deadline and opp.deadline_confident:
        breakdown["freshness"] = MAXIMA["freshness"]
    elif str(current_year) in text or str(current_year + 1) in text:
        breakdown["freshness"] = 3
    else:
        breakdown["freshness"] = 1

    opp.score_breakdown = breakdown
    opp.match_score = sum(breakdown.values())
    return opp