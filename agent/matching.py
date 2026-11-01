"""Keyword include/exclude matching for Reddit posts (LURK: Listen)."""
from __future__ import annotations

from dataclasses import dataclass

from .reddit import RedditPost


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    keywords: tuple[str, ...]
    excluded_by: str | None = None


def evaluate_post(post: RedditPost, keywords: tuple[str, ...], exclude_terms: tuple[str, ...]) -> MatchResult:
    haystack = f"{post.title}\n{post.selftext}".lower()
    for term in exclude_terms:
        needle = term.lower().strip()
        if needle and needle in haystack:
            return MatchResult(matched=False, keywords=(), excluded_by=term)
    hits = []
    for term in keywords:
        needle = term.lower().strip()
        if needle and needle in haystack:
            hits.append(term)
    if hits:
        return MatchResult(matched=True, keywords=tuple(hits))
    return MatchResult(matched=False, keywords=())
