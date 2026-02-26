"""GitHub ingestion adapter (Issue #244, Phase 2).

Fetches repository and org events from GitHub API. Emits RawEvents with
event_type_candidate='repo_activity'. Requires GITHUB_TOKEN or GITHUB_PAT.
When unset, returns [] and logs at debug. No exception.

Config: INGEST_GITHUB_REPOS (comma-separated owner/repo) or
INGEST_GITHUB_ORGS (comma-separated org names). At least one required.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.base import SourceAdapter
from app.schemas.signal import RawEvent

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_DEFAULT_PAGE_SIZE = 100


def _get_token() -> str | None:
    """Return GITHUB_TOKEN or GITHUB_PAT if set and non-empty."""
    for key in ("GITHUB_TOKEN", "GITHUB_PAT"):
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return None


def _get_repos_and_orgs() -> tuple[list[str], list[str]]:
    """Return (repos, orgs) from env.

    INGEST_GITHUB_REPOS: comma-separated owner/repo.
    INGEST_GITHUB_ORGS: comma-separated org names.
    """
    repos: list[str] = []
    orgs: list[str] = []
    repos_val = os.getenv("INGEST_GITHUB_REPOS", "").strip()
    if repos_val:
        repos = [r.strip() for r in repos_val.split(",") if r.strip()]
    orgs_val = os.getenv("INGEST_GITHUB_ORGS", "").strip()
    if orgs_val:
        orgs = [o.strip() for o in orgs_val.split(",") if o.strip()]
    return repos, orgs


def _parse_created_at(value: Any) -> datetime:
    """Parse GitHub created_at (ISO 8601) to datetime with UTC."""
    s = str(value) if value is not None else ""
    if not s:
        return datetime.now(UTC)
    try:
        s = s.replace("Z", "+00:00").replace("z", "+00:00")
        parsed = datetime.fromisoformat(s[:26])
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _source_event_id(repo_name: str, event_id: str | int, event_type: str) -> str:
    """Generate stable source_event_id: repo:event_id:type (max 255 chars)."""
    sid = f"{repo_name}:{event_id}:{event_type}"
    return sid[:255] if len(sid) > 255 else sid


def _event_to_raw_event(ev: dict, repo_name: str) -> RawEvent | None:
    """Map a GitHub API event to RawEvent."""
    ev_id = ev.get("id")
    if ev_id is None:
        return None
    ev_type = ev.get("type") or "Event"
    ev_id_str = str(ev_id)

    source_event_id = _source_event_id(repo_name, ev_id_str, ev_type)
    created_at = _parse_created_at(ev.get("created_at"))
    actor_login = ""
    if isinstance(ev.get("actor"), dict):
        actor_login = ev.get("actor", {}).get("login") or ""

    # company_name: org or owner (from repo owner/repo)
    owner = repo_name.split("/")[0] if "/" in repo_name else repo_name
    company_name = owner
    if not company_name or len(company_name) > 255:
        company_name = company_name[:255] if company_name else "Unknown"

    url = f"https://github.com/{repo_name}"
    if ev_type == "PushEvent" and isinstance(ev.get("payload"), dict):
        payload = ev["payload"]
        head = (payload.get("head") or payload.get("before") or "")
        if head:
            url = f"https://github.com/{repo_name}/commit/{head}"
    elif ev_type == "PullRequestEvent" and isinstance(ev.get("payload"), dict):
        pr = ev.get("payload", {}).get("pull_request") or {}
        html_url = pr.get("html_url")
        if html_url:
            url = str(html_url)[:2048]

    return RawEvent(
        company_name=company_name,
        domain=None,
        website_url=None,
        company_profile_url=None,
        event_type_candidate="repo_activity",
        event_time=created_at,
        title=f"{ev_type} in {repo_name}",
        summary=actor_login[:512] if actor_login else None,
        url=url[:2048] if url else None,
        source_event_id=source_event_id,
        raw_payload={
            "type": ev_type,
            "actor": actor_login,
            "repo": repo_name,
        },
    )


def _fetch_repo_events(
    client: httpx.Client,
    token: str,
    owner: str,
    repo: str,
    since: datetime,
    page: int = 1,
) -> tuple[list[dict], int]:
    """Fetch one page of repo events. Returns (events, status_code)."""
    url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"per_page": _DEFAULT_PAGE_SIZE, "page": page}
    try:
        response = client.get(url, headers=headers, params=params, timeout=30.0)
        if response.status_code != 200:
            return [], response.status_code
        data = response.json()
        if not isinstance(data, list):
            return [], 500
        return data, 200
    except Exception as exc:
        logger.warning("GitHub repo events request failed: %s", exc)
        return [], 500


def _fetch_org_events(
    client: httpx.Client,
    token: str,
    org: str,
    since: datetime,
    page: int = 1,
) -> tuple[list[dict], int]:
    """Fetch one page of org events. Returns (events, status_code)."""
    url = f"{_GITHUB_API_BASE}/orgs/{org}/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"per_page": _DEFAULT_PAGE_SIZE, "page": page}
    try:
        response = client.get(url, headers=headers, params=params, timeout=30.0)
        if response.status_code != 200:
            return [], response.status_code
        data = response.json()
        if not isinstance(data, list):
            return [], 500
        return data, 200
    except Exception as exc:
        logger.warning("GitHub org events request failed: %s", exc)
        return [], 500


class GitHubAdapter(SourceAdapter):
    """Adapter for GitHub repository and org events.

    Fetches events via GitHub REST API. Maps to RawEvent with
    event_type_candidate='repo_activity'. Returns [] when
    GITHUB_TOKEN/GITHUB_PAT is unset or when no repos/orgs configured.
    """

    @property
    def source_name(self) -> str:
        return "github"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch repo/org events since given datetime."""
        token = _get_token()
        if not token:
            logger.debug("GITHUB_TOKEN/GITHUB_PAT unset – skipping GitHub fetch")
            return []

        repos, orgs = _get_repos_and_orgs()
        if not repos and not orgs:
            logger.debug("INGEST_GITHUB_REPOS and INGEST_GITHUB_ORGS unset – skipping")
            return []

        events: list[RawEvent] = []
        seen_ids: set[str] = set()

        with httpx.Client() as client:
            for repo_spec in repos:
                if "/" not in repo_spec:
                    logger.warning("Invalid repo spec (expected owner/repo): %s", repo_spec[:50])
                    continue
                parts = repo_spec.split("/", 1)
                owner, repo = parts[0], parts[1]
                page = 1
                while True:
                    evs, status = _fetch_repo_events(client, token, owner, repo, since, page)
                    if status in (401, 403, 404, 429, 500):
                        if status == 404:
                            logger.debug("Repo not found: %s", repo_spec)
                        else:
                            logger.warning("GitHub returned %s for %s", status, repo_spec[:30])
                        break
                    for ev in evs:
                        raw = _event_to_raw_event(ev, repo_spec)
                        if raw and raw.source_event_id and raw.source_event_id not in seen_ids:
                            if raw.event_time >= since:
                                seen_ids.add(raw.source_event_id)
                                events.append(raw)
                    if len(evs) < _DEFAULT_PAGE_SIZE:
                        break
                    page += 1

            for org in orgs:
                page = 1
                while True:
                    evs, status = _fetch_org_events(client, token, org, since, page)
                    if status in (401, 403, 404, 429, 500):
                        if status == 404:
                            logger.debug("Org not found: %s", org)
                        else:
                            logger.warning("GitHub returned %s for org %s", status, org[:30])
                        break
                    for ev in evs:
                        repo_info = ev.get("repo") or {}
                        repo_name = repo_info.get("name", org) if isinstance(repo_info, dict) else org
                        raw = _event_to_raw_event(ev, repo_name)
                        if raw and raw.source_event_id and raw.source_event_id not in seen_ids:
                            if raw.event_time >= since:
                                seen_ids.add(raw.source_event_id)
                                events.append(raw)
                    if len(evs) < _DEFAULT_PAGE_SIZE:
                        break
                    page += 1

        return events
