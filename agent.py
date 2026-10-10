"""Agent pipeline: profile + request -> queries -> SerpApi -> dedup -> extract -> eligibility -> score -> rank."""
from __future__ import annotations

from typing import Callable, Optional

import serpapi_client
from eligibility import analyze_eligibility, classify_opportunity_type, detect_organization
from models import Opportunity, SearchEvidence, StudentProfile
from query_planner import plan_queries
from scoring import score_opportunity
from utils import (base_domain, clean_snippet, domain_from_url, find_duplicate,
                   is_non_opportunity, looks_like_opportunity, matches_request, is_outdated,
                   is_past_participant, request_keywords, request_types, normalize_title, normalize_url, parse_posted_date)

ProgressFn = Callable[[str], None]

def run_agent(
    profile: StudentProfile,
    request: str,
    progress: Optional[ProgressFn] = None,
) -> tuple[list[Opportunity], list[str]]:
    """Run the full agent pipeline. Returns (opportunities, queries_used)."""
    def emit(msg: str):
        if progress:
            progress(msg)

    emit("Understanding your profile...")
    emit("Generating search queries...")
    queries = plan_queries(profile, request)
    emit(f"Planned {len(queries)} search queries.")

    emit("Searching the live web with SerpApi...")
    raw_results: list[dict] = []
    for q in queries:
        emit(f"Querying SerpApi: {q}")
        try:
            res = serpapi_client.search(q, num=10)
            for r in res:
                r["query"] = q
            raw_results.extend(res)
        except serpapi_client.SerpApiError as e:
            if e.kind == "empty":
                continue
            raise

    if not raw_results:
        raise serpapi_client.SerpApiError(
            "SerpApi returned no results across any of the planned queries. Try a broader request.",
            kind="empty",
        )

    emit("Collecting results...")
    emit("Filtering out profiles and removing duplicates...")
    seen: dict = {}
    opportunities: list[Opportunity] = []
    skipped_profiles = 0
    skipped_noise = 0
    skipped_off_topic = 0
    skipped_old = 0
    focus = request_keywords(request)
    wanted = request_types(request)
    skipped_type = 0
    if wanted:
        emit(f"Looking only for: {', '.join(t.lower() + 's' for t in wanted)}")
    if focus:
        emit(f"Focusing on: {', '.join(focus)}")
    for r in raw_results:
        url = r.get("link", "")
        title = r.get("title", "")
        if not url or not title:
            continue
        if is_non_opportunity(url, title):
            skipped_profiles += 1
            continue
        domain = domain_from_url(url)
        snippet = clean_snippet(r.get("snippet", ""))
        if is_past_participant(title, snippet):
            skipped_profiles += 1
            continue
        opp_type = classify_opportunity_type(title, snippet, prefer=wanted)
        if wanted and opp_type not in wanted:
            skipped_type += 1
            continue
        if not looks_like_opportunity(title, snippet, opp_type):
            skipped_noise += 1
            continue
        if not matches_request(title, snippet, focus):
            skipped_off_topic += 1
            continue
        if is_outdated(title, snippet, parse_posted_date(r.get("date", ""))):
            skipped_old += 1
            continue
        evidence = SearchEvidence(query=r.get("query", ""), source_domain=domain, snippet=snippet)

        probe = type("O", (), {"url": url, "source_domain": domain, "title": title})()
        dup_key = find_duplicate(probe, seen)
        if dup_key is not None:
            # Same opportunity found again: keep one card, but remember every query that surfaced it.
            existing = opportunities[seen[dup_key][2]]
            existing.evidence.append(evidence)
            if not existing.posted_iso and r.get("date"):
                existing.posted_raw, existing.posted_iso = r["date"], parse_posted_date(r["date"])
            continue

        seen[normalize_url(url)] = (base_domain(domain), normalize_title(title), len(opportunities))
        opportunities.append(Opportunity(
            title=title, url=url, source_domain=domain, snippet=snippet,
            opportunity_type=opp_type,
            organization=detect_organization(title, domain),
            position=r.get("position", 0),
            posted_raw=r.get("date", "") or "",
            posted_iso=parse_posted_date(r.get("date", "")),
            evidence=[evidence],
        ))

    if skipped_profiles:
        emit(f"Skipped {skipped_profiles} profile, forum or social pages.")
    if skipped_noise:
        emit(f"Skipped {skipped_noise} results that do not look like opportunities.")
    if skipped_type:
        emit(f"Skipped {skipped_type} results of other types (you asked for {', '.join(t.lower() + 's' for t in wanted)}).")
    if skipped_off_topic:
        emit(f"Skipped {skipped_off_topic} results that do not mention {', '.join(focus)}.")
    if skipped_old:
        emit(f"Skipped {skipped_old} outdated postings.")
    if not opportunities and wanted and skipped_type:
        raise serpapi_client.SerpApiError(
            f"No {', '.join(t.lower() + 's' for t in wanted)} were found in the results. Try different wording or a broader request.",
            kind="empty",
        )
    if not opportunities and focus and skipped_off_topic:
        raise serpapi_client.SerpApiError(
            f"No result mentioned {', '.join(focus)} in its title or description. Try a broader request or different wording.",
            kind="empty",
        )
    if not opportunities:
        raise serpapi_client.SerpApiError(
            "Only profile pages or unrelated pages came back. Try a more specific request, e.g. name the opportunity type.",
            kind="empty",
        )
    emit("Extracting opportunities...")

    emit("Analyzing eligibility...")
    emit("Checking eligibility signals...")
    analyzed: list[Opportunity] = [analyze_eligibility(opp, profile) for opp in opportunities]

    emit("Calculating transparent match scores...")
    scored: list[Opportunity] = [score_opportunity(opp, profile) for opp in analyzed]

    emit("Ranking personalized results...")
    scored.sort(key=lambda o: o.match_score, reverse=True)

    emit("Preparing personalized results...")
    return scored, queries