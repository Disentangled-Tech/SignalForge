"""Query Planner for Discovery Scout — read-only core taxonomy + optional pack emphasis.

Produces a diversified list of search query strings from ICP, core readiness signal
rubric (dimensions/signal_ids for query phrasing only), and optional pack emphasis.
Supports query families and rotation (Issue #282). No DB, no HTTP. Scout path only.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core_taxonomy.loader import load_core_taxonomy
from app.packs.loader import get_pack_dir
from app.scout.query_families import DEFAULT_FAMILY_ID, load_query_families_config

# Known acronyms to keep uppercase in query phrases (read-only, query phrasing only).
_ACRONYMS = frozenset({"cto", "cfo", "coo", "cmo", "api", "ai", "saas", "b2b", "b2c", "ipo"})


def _signal_id_to_phrase(signal_id: str) -> str:
    """Convert signal_id (snake_case) to a readable search phrase."""
    if not signal_id or not isinstance(signal_id, str):
        return ""
    parts = signal_id.strip().lower().split("_")
    words = []
    for p in parts:
        if p in _ACRONYMS:
            words.append(p.upper())
        else:
            words.append(p.capitalize() if p else "")
    return " ".join(w for w in words if w)


def _get_pack_emphasis(pack_id: str) -> list[str]:
    """Return scout_emphasis keywords from pack manifest if present; else [].

    Reads packs/{pack_id}/pack.json for optional 'scout_emphasis' (list of strings).
    Does not load full pack or run validation. Returns [] on missing file or invalid data.
    """
    if not pack_id or not isinstance(pack_id, str):
        return []
    try:
        pack_dir = get_pack_dir(pack_id)
        manifest_path = pack_dir / "pack.json"
        if not manifest_path.is_file():
            return []
        with manifest_path.open(encoding="utf-8") as f:
            manifest = json.load(f)
        emphasis = manifest.get("scout_emphasis")
        if not isinstance(emphasis, list):
            return []
        return [str(x).strip() for x in emphasis if x and isinstance(x, str)]
    except (OSError, ValueError, TypeError):
        return []


# Regex to find site: operator and domain in a query (e.g. "site:example.com" or "site: sub.example.com").
_SITE_OPERATOR_RE = re.compile(r"site:\s*([a-zA-Z0-9._-]+)", re.IGNORECASE)


def _blocked_matches_domain(domain: str, blocked: str) -> bool:
    """Return True if domain is blocked or a subdomain of blocked.

    When blocked is two-label with a two-letter suffix (e.g. co.uk), only exact match
    is used so that denylisting co.uk does not block every *.co.uk (e.g. evil.co.uk).
    """
    if domain == blocked:
        return True
    # Avoid over-matching TLD-like entries: e.g. blocked "co.uk" should not match "evil.co.uk"
    if "." in blocked:
        parts = blocked.split(".")
        if len(parts) == 2 and len(parts[1]) == 2:
            return False  # exact match already handled above
    return domain.endswith("." + blocked)


def _query_targets_denylisted_domain(query: str, denylist: list[str]) -> bool:
    """Return True if query contains site:<domain> and domain is denylisted (or subdomain of one).

    Used to exclude queries that would target denylisted sources at plan time. URL-level
    filtering remains the authority in filter_allowed_sources (sources.py).

    TLD-like denylist entries (e.g. co.uk): only exact match; subdomains of evil.com
    (e.g. blog.evil.com) are matched when evil.com is denylisted.
    """
    if not denylist or not isinstance(query, str):
        return False
    denylist_normalized = frozenset(d.strip().lower() for d in denylist if d and isinstance(d, str))
    if not denylist_normalized:
        return False
    for match in _SITE_OPERATOR_RE.finditer(query):
        domain = match.group(1).strip().lower()
        if not domain:
            continue
        if domain in denylist_normalized:
            return True
        for blocked in denylist_normalized:
            if _blocked_matches_domain(domain, blocked):
                return True
    return False


def _round_robin_by_family(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Reorder (query, family_id) pairs so families are interleaved (round-robin)."""
    if len(pairs) <= 1:
        return list(pairs)
    by_family: dict[str, list[str]] = {}
    for q, fid in pairs:
        by_family.setdefault(fid, []).append(q)
    families_order = list(by_family.keys())
    result: list[tuple[str, str]] = []
    index = 0
    while True:
        added = 0
        for fid in families_order:
            if index < len(by_family[fid]):
                result.append((by_family[fid][index], fid))
                added += 1
        if added == 0:
            break
        index += 1
    return result


def _build_query_family_pairs(
    icp: str,
    core_rubric: dict[str, Any],
    pack_id: str | None,
    max_queries: int,
) -> list[tuple[str, str]]:
    """Build (query, family_id) pairs from family config and rubric; deduplicated."""
    config = load_query_families_config()
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []

    # From family config: expand templates that contain {icp}
    for fam in config:
        fid = fam.get("id") or DEFAULT_FAMILY_ID
        templates = fam.get("templates") or []
        for tpl in templates:
            if not isinstance(tpl, str):
                continue
            q = tpl.replace("{icp}", icp).strip()
            if q and q not in seen:
                seen.add(q)
                pairs.append((q, fid))
        if len(pairs) >= max_queries:
            break
    if len(pairs) >= max_queries:
        return _round_robin_by_family(pairs)[:max_queries]

    # Rubric-based: phrases from core taxonomy (same logic as original plan())
    signal_ids = core_rubric.get("signal_ids") or []
    dimensions = core_rubric.get("dimensions") or {}
    phrases_from_rubric: list[str] = []
    for dim_ids in dimensions.values():
        if isinstance(dim_ids, list):
            for sid in dim_ids[:2]:
                if isinstance(sid, str):
                    phrase = _signal_id_to_phrase(sid)
                    if phrase and phrase not in phrases_from_rubric:
                        phrases_from_rubric.append(phrase)
    for sid in signal_ids:
        if isinstance(sid, str):
            phrase = _signal_id_to_phrase(sid)
            if phrase and phrase not in phrases_from_rubric:
                phrases_from_rubric.append(phrase)
        if len(phrases_from_rubric) >= 15:
            break

    for phrase in phrases_from_rubric:
        for template in (f"{icp} {phrase}", f"{phrase} {icp}"):
            t = template.strip()
            if t and t not in seen:
                seen.add(t)
                pairs.append((t, DEFAULT_FAMILY_ID))
        if len(pairs) >= max_queries:
            break

    if pack_id:
        for kw in _get_pack_emphasis(pack_id):
            if not kw:
                continue
            for template in (f"{icp} {kw}", f"{kw} {icp}"):
                t = template.strip()
                if t and t not in seen:
                    seen.add(t)
                    pairs.append((t, DEFAULT_FAMILY_ID))
            if len(pairs) >= max_queries:
                break

    if not pairs:
        pairs = [(icp, DEFAULT_FAMILY_ID)]

    rotated = _round_robin_by_family(pairs)
    return rotated[:max_queries]


class QueryPlanner:
    """Plans diversified search queries from ICP, core rubric, and optional pack emphasis.

    Read-only: uses load_core_taxonomy() and optional pack manifest scout_emphasis.
    No DB, no HTTP.
    """

    def __init__(self, max_queries: int = 30) -> None:
        """Initialize planner with optional cap on number of queries (diversified set)."""
        self._max_queries = max(1, min(100, max_queries))

    def plan_with_families(
        self,
        icp: str,
        core_rubric: dict[str, Any] | None = None,
        pack_id: str | None = None,
        denylist: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Produce diversified queries with family tags; rotation applied.

        When denylist is provided, queries containing site:<denylisted_domain> are excluded.
        URL-level filtering remains in filter_allowed_sources (sources.py).

        Returns:
            (queries, families): same-length lists; families interleaved (round-robin).
        """
        icp = (icp or "").strip()
        if not icp:
            icp = "startup"
        if core_rubric is None:
            core_rubric = load_core_taxonomy()
        pairs = _build_query_family_pairs(
            icp=icp,
            core_rubric=core_rubric,
            pack_id=pack_id,
            max_queries=self._max_queries,
        )
        if denylist:
            pairs = [(q, f) for q, f in pairs if not _query_targets_denylisted_domain(q, denylist)]
            if not pairs and icp and not _query_targets_denylisted_domain(icp, denylist):
                pairs = [(icp, DEFAULT_FAMILY_ID)]
        queries = [q for q, _ in pairs]
        families = [f for _, f in pairs]
        return (queries, families)

    def plan(
        self,
        icp: str,
        core_rubric: dict[str, Any] | None = None,
        pack_id: str | None = None,
        denylist: list[str] | None = None,
    ) -> list[str]:
        """Produce a diversified list of search query strings.

        Args:
            icp: Ideal Customer Profile definition (free text).
            core_rubric: Core taxonomy dict (signal_ids, dimensions). If None, loads
                from load_core_taxonomy().
            pack_id: Optional pack id for emphasis hints (scout_emphasis in pack.json).
            denylist: Optional list of domains to exclude; queries containing site:<domain>
                are dropped. URL filtering remains in filter_allowed_sources.

        Returns:
            Non-empty list of deduplicated query strings (no DB, no HTTP).
        """
        queries, _ = self.plan_with_families(
            icp=icp,
            core_rubric=core_rubric,
            pack_id=pack_id,
            denylist=denylist,
        )
        return queries


def plan_queries(
    icp: str,
    core_rubric: dict[str, Any] | None = None,
    pack_id: str | None = None,
    max_queries: int = 30,
    denylist: list[str] | None = None,
) -> list[str]:
    """Convenience: plan diversified search queries (QueryPlanner().plan()).

    When denylist is provided, queries containing site:<denylisted_domain> are excluded.
    """
    return QueryPlanner(max_queries=max_queries).plan(
        icp=icp,
        core_rubric=core_rubric,
        pack_id=pack_id,
        denylist=denylist,
    )
