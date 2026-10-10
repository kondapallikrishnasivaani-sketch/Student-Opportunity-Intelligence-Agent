"""
SerpApi client wrapper.

Features:
- Secure API key handling
- Google search through official SerpApi Python client
- Fresh-result support
- Google recency filtering
- Cache bypass
- Posted-date extraction
- Friendly error handling
"""

from __future__ import annotations

import os
from typing import Any

try:
    import serpapi
except ImportError:
    serpapi = None  # type: ignore


class SerpApiError(Exception):
    """User-friendly SerpApi error."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.message = message
        self.kind = kind


def get_api_key() -> str | None:
    """Read SERPAPI_KEY without exposing it."""

    # Environment variable
    key = os.environ.get("SERPAPI_KEY")

    if key:
        key = key.strip()

        if key:
            return key

    # Streamlit secrets
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "SERPAPI_KEY" in st.secrets:
            key = str(st.secrets["SERPAPI_KEY"]).strip()

            if key:
                return key

    except Exception:
        pass

    return None


def is_configured() -> bool:
    """Check whether a SerpApi key is configured."""
    return bool(get_api_key())


def _freshness_filter(freshness_days: int | None) -> str | None:
    """
    Convert freshness window into Google's tbs value.

    1 day  -> qdr:d
    7 days -> qdr:w
    30 days -> qdr:m
    """

    if freshness_days is None:
        return None

    if freshness_days <= 1:
        return "qdr:d"

    if freshness_days <= 7:
        return "qdr:w"

    if freshness_days <= 31:
        return "qdr:m"

    return None


def search(
    query: str,
    num: int = 10,
    freshness_days: int = 30,
    force_fresh: bool = True,
) -> list[dict[str, Any]]:
    """
    Search Google through SerpApi.

    freshness_days:
        30 means prioritize results from the last month.

    force_fresh:
        True tells SerpApi not to use cached results.
    """

    # --------------------------------------------------
    # Check package
    # --------------------------------------------------

    if serpapi is None:
        raise SerpApiError(
            "The `serpapi` Python package is not installed. "
            "Run: pip install serpapi",
            kind="error",
        )

    # --------------------------------------------------
    # Check API key
    # --------------------------------------------------

    key = get_api_key()

    if not key:
        raise SerpApiError(
            "SerpApi API key is not configured. "
            "Set SERPAPI_KEY in your .env file.",
            kind="missing_key",
        )

    query = (query or "").strip()

    if not query:
        raise SerpApiError(
            "Search query is empty.",
            kind="error",
        )

    # --------------------------------------------------
    # Build request
    # --------------------------------------------------

    params: dict[str, Any] = {
        "engine": "google",
        "q": query,
        "num": max(1, min(int(num), 100)),
    }

    # Google freshness filter
    tbs = _freshness_filter(freshness_days)

    if tbs:
        params["tbs"] = tbs

    # Force a fresh SerpApi result
    if force_fresh:
        params["no_cache"] = True

    # --------------------------------------------------
    # Call SerpApi
    # --------------------------------------------------

    try:

        client = serpapi.Client(api_key=key)

        raw = client.search(params)

    except Exception as e:

        msg = str(e).lower()

        if (
            "api key" in msg
            or "api_key" in msg
            or "invalid" in msg
            or "unauthorized" in msg
            or "401" in msg
            or "403" in msg
        ):
            raise SerpApiError(
                "SerpApi rejected the API key as invalid. "
                "Check your SERPAPI_KEY.",
                kind="invalid_key",
            ) from e

        if (
            "quota" in msg
            or "limit" in msg
            or "exceeded" in msg
            or "rate" in msg
            or "429" in msg
        ):
            raise SerpApiError(
                "SerpApi search limit reached. "
                "Check your SerpApi account quota.",
                kind="quota",
            ) from e

        if "timeout" in msg or "timed out" in msg:
            raise SerpApiError(
                "SerpApi request timed out. "
                "Check your internet connection and retry.",
                kind="network",
            ) from e

        if (
            "connection" in msg
            or "network" in msg
            or "dns" in msg
        ):
            raise SerpApiError(
                "Network error while reaching SerpApi. "
                "Check your internet connection.",
                kind="network",
            ) from e

        raise SerpApiError(
            f"SerpApi search failed: {e}",
            kind="error",
        ) from e

    # --------------------------------------------------
    # IMPORTANT FIX
    # --------------------------------------------------
    #
    # Do NOT require:
    #
    #     isinstance(raw, dict)
    #
    # because the SerpApi Python client can return a
    # response object that behaves like a mapping.
    # --------------------------------------------------

    try:

        organic = raw.get("organic_results") or []

    except AttributeError as e:

        raise SerpApiError(
            "SerpApi returned an unexpected response. "
            "The response does not contain organic results.",
            kind="error",
        ) from e

    # --------------------------------------------------
    # Extract results
    # --------------------------------------------------

    results: list[dict[str, Any]] = []

    for i, result in enumerate(organic, start=1):

        if not isinstance(result, dict):
            continue

        title = result.get("title", "") or ""

        link = result.get("link", "") or ""

        snippet = result.get("snippet", "") or ""

        # Some results don't have a normal snippet.
        if not snippet:

            rich = result.get("rich_snippet") or ""

            if isinstance(rich, dict):
                snippet = " ".join(
                    str(value)
                    for value in rich.values()
                )

            else:
                snippet = str(rich)

        # Google/SerpApi may provide a publication date.
        posted_date = result.get("date", "") or ""

        results.append(
            {
                "title": str(title),
                "link": str(link),
                "snippet": str(snippet),
                "source": str(
                    result.get("source", "") or ""
                ),
                "date": str(posted_date),
                "position": result.get(
                    "position",
                    i,
                ),
                "query": query,
            }
        )

    # --------------------------------------------------
    # No results
    # --------------------------------------------------

    if not results:

        raise SerpApiError(
            "SerpApi returned no organic results "
            "for this query. Try a broader request.",
            kind="empty",
        )

    return results