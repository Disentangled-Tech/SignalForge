# Discovery Scout — Query Planner (Issue #282)

Links to other docs (e.g. [discovery_scout.md](discovery_scout.md)) are relative to the `docs/` directory.

The **Query Planner** produces a diversified list of search query strings for the Discovery Scout. It is **pack-agnostic**: family definitions and template configuration live in core (`app/scout/`); packs provide optional **scout_emphasis** keywords only (search phrasing), not schema or query structure.

## Query families

Query families group templates by intent (e.g. Hiring, Launch, Geography). Family ids are defined in code and optionally in config:

- **In-code constants** (`app/scout/query_families.py`): `HIRING`, `LAUNCH`, `GEOGRAPHY`, `ROLE_EMPHASIS`, `NICHE`, and `DEFAULT_FAMILY_ID` (`"rubric"`) for rubric-only queries when no YAML is present.
- **Config file:** `app/scout/query_families.yaml` — list of `{ id, label, templates: [strings] }`. The placeholder `{icp}` in a template is replaced with the ICP string at plan time. If the file is missing or invalid, the planner falls back to a single family (`rubric`) and generates queries from the core taxonomy rubric only.

## Rotation

The planner interleaves queries by family (round-robin) so the returned list is diversified across families. When multiple families have templates (or rubric-derived queries), the output order cycles through families rather than returning all of one family then the next.

## Config-based query packs

Loading from `query_families.yaml` allows adding or changing query template sets without code changes. “Query packs” here means the YAML-defined set of families and templates; **pack_id** (pack manifest) still only provides optional `scout_emphasis` hints in `pack.json`, which the planner merges with rubric and family templates.

## Public API

- **`plan_queries(icp, core_rubric=None, pack_id=None, max_queries=30)`** — Returns `list[str]`. Backward-compatible; no family tags.
- **`QueryPlanner.plan_with_families(icp, core_rubric=None, pack_id=None)`** — Returns `(queries: list[str], families: list[str])` with same-length lists; families are family ids (e.g. `"hiring"`, `"rubric"`).
- **`QueryPlanner.plan(...)`** — Returns `list[str]` (same as `plan_queries` for a single planner instance).

The service may call `plan_with_families()` and persist `queries` and `query_families` in `config_snapshot` for observability and analytics; see [discovery_scout.md](discovery_scout.md#config-snapshot-shape).

## Denylist

- **URL filtering:** Always applied when choosing which URLs to fetch (`app/scout/sources.py` — `filter_allowed_sources(allowlist, denylist)`). Denylist takes precedence.
- **Plan-time denylist (optional):** When the planner accepts an optional `denylist`, it avoids generating queries that explicitly target denylisted domains (e.g. `site:blocked.com`). URL-level filtering remains the authority for what is actually fetched.

## Key files

| File | Purpose |
|------|--------|
| `app/scout/query_planner.py` | `QueryPlanner`, `plan_queries()`, `plan_with_families()`, round-robin and rubric expansion. |
| `app/scout/query_families.py` | Family constants, `load_query_families_config()`, default family when YAML missing. |
| `app/scout/query_families.yaml` | Optional declarative families and templates (`{icp}` placeholder). |
