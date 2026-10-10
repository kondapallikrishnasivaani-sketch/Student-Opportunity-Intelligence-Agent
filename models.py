"""Data models for the Student Opportunity Intelligence Agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

@dataclass
class StudentProfile:
    name: str = ""
    degree: str = "B.Tech"
    branch: str = "CSE"
    year: str = "2nd Year"
    skills: list[str] = field(default_factory=lambda: ["C", "C++", "Python", "SQL"])
    interests: list[str] = field(default_factory=lambda: ["AI", "Data Science", "Software Development"])
    location: str = "India"
    opportunity_types: list[str] = field(default_factory=lambda: ["Internship", "Hackathon"])

    @property
    def graduation_year(self) -> int:
        """Estimate graduation year from academic year (assuming 4-year degree)."""
        year_map = {
            "1st year": 2029,
            "2nd year": 2028,
            "3rd year": 2027,
            "4th year": 2026,
        }
        return year_map.get(self.year.lower(), 2028)

@dataclass
class SearchEvidence:
    query: str
    source_domain: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "source_domain": self.source_domain,
            "snippet": self.snippet,
        }

@dataclass
class Opportunity:
    title: str
    url: str
    source_domain: str
    snippet: str = ""
    opportunity_type: str = "Unknown"
    organization: str = ""
    deadline: Optional[str] = None
    deadline_confident: bool = False
    eligibility: str = "unclear"  # "likely", "unclear", "unlikely"
    eligibility_reason: str = ""
    match_score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    matched_skills: list[str] = field(default_factory=list)
    match_explanation: str = ""
    potential_concern: str = ""
    evidence: list[SearchEvidence] = field(default_factory=list)
    position: int = 0
    posted_raw: str = ""                 # date text exactly as returned by SerpApi
    posted_iso: Optional[str] = None     # parsed yyyy-mm-dd, None when unknown

    @property
    def is_new(self) -> bool:
        """True when SerpApi reported a posting date within the last 7 days."""
        if not self.posted_iso:
            return False
        try:
            age = (date.today() - date.fromisoformat(self.posted_iso)).days
        except ValueError:
            return False
        return 0 <= age <= 7

    @property
    def eligibility_label(self) -> str:
        return {
            "likely": "Likely Eligible",
            "unclear": "Eligibility Unclear",
            "unlikely": "Likely Not Eligible",
        }.get(self.eligibility, "Eligibility Unclear")

    @property
    def eligibility_icon(self) -> str:
        return {"likely": "🟢", "unclear": "🟡", "unlikely": "🔴"}.get(self.eligibility, "🟡")

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source_domain": self.source_domain,
            "snippet": self.snippet,
            "opportunity_type": self.opportunity_type,
            "organization": self.organization,
            "deadline": self.deadline,
            "deadline_confident": self.deadline_confident,
            "eligibility": self.eligibility,
            "eligibility_label": self.eligibility_label,
            "match_score": self.match_score,
            "score_breakdown": self.score_breakdown,
            "matched_skills": self.matched_skills,
            "match_explanation": self.match_explanation,
            "potential_concern": self.potential_concern,
            "evidence": [e.to_dict() for e in self.evidence],
            "posted_raw": self.posted_raw,
            "posted_iso": self.posted_iso,
            "eligibility_reason": self.eligibility_reason,
            "position": self.position,
        }