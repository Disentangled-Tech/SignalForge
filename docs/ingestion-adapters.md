# Ingestion Adapters

This document describes the source adapters used by the daily ingestion pipeline (`run_ingest_daily`). Adapters fetch raw events from external APIs, which are then normalized, resolved to companies, and stored as `signal_events`.

See [pipeline.md](pipeline.md) for the high-level adapter table and pipeline flow.

---

## Overview

| Adapter | Env vars | Event types | Notes |
|---------|----------|-------------|-------|
| **Crunchbase** | `CRUNCHBASE_API_KEY`, `INGEST_CRUNCHBASE_ENABLED=1` | funding_raised | Requires Crunchbase API license |
| **Product Hunt** | `PRODUCTHUNT_API_TOKEN`, `INGEST_PRODUCTHUNT_ENABLED=1` | launch_major | Implemented; rate limits apply; retry on 429/5xx |
| **NewsAPI** | `NEWSAPI_API_KEY`, `INGEST_NEWSAPI_ENABLED=1` | funding_raised | Keyword-based queries. 100 req/day free tier. See [NewsAPI](#newsapi). |
| **GitHub** | `GITHUB_TOKEN`, `INGEST_GITHUB_ENABLED=1` | repo_activity | Repo/org events. See [GitHub](#github). |
| **Delaware Socrata** | `INGEST_DELAWARE_SOCRATA_ENABLED=1`, `INGEST_DELAWARE_SOCRATA_DATASET_ID` | incorporation | Incorporation filings from Delaware Open Data. See [Delaware Socrata](#delaware-socrata). |
| **TestAdapter** | `INGEST_USE_TEST_ADAPTER=1` | funding_raised, job_posted_engineering, cto_role_posted | Tests only; when set, only TestAdapter is used |

When `INGEST_USE_TEST_ADAPTER=1`, only TestAdapter is returned. Otherwise, adapters are built from env: each adapter is included when its enable flag is set and its API key/token is present.

---

## Crunchbase

### API Key Acquisition

The Crunchbase adapter uses the [Crunchbase Data API](https://data.crunchbase.com/docs). API access requires a Crunchbase license:

- **Data Licensing** – Integrate Crunchbase data into customer-facing products
- **Data Enrichment** – Feed Crunchbase data into internal systems and workflows

Contact [Crunchbase sales](https://about.crunchbase.com/products/data-licensing/) or [[email protected]](mailto:sales@crunchbase.com) for API access and pricing.

### Configuration

1. Obtain an API key (user key) from your Crunchbase account.
2. Set environment variables:
   ```bash
   export CRUNCHBASE_API_KEY=your-api-key
   export INGEST_CRUNCHBASE_ENABLED=1
   ```
3. Add to `.env` (never commit):
   ```
   CRUNCHBASE_API_KEY=your-api-key
   INGEST_CRUNCHBASE_ENABLED=1
   ```

When `CRUNCHBASE_API_KEY` is unset or empty, the adapter returns `[]` and logs at debug. No exception is raised.

### Rate Limits and Behavior

- **429 Too Many Requests**: The adapter stops pagination and returns partial results. A warning is logged.
- **Non-200 responses**: Pagination stops; a warning is logged.
- **Pagination**: Uses Crunchbase v4 search API with `limit=100` and `after_id` cursor. Fetches funding rounds with `announced_on >= since`.

### Event Mapping

Funding rounds are mapped to `RawEvent` with:

- `event_type_candidate`: `funding_raised`
- `company_name`, `domain`, `website_url` from funded organization
- `event_time` from `announced_on`
- `url`: Crunchbase funding round page

---

## Product Hunt (Implemented)

### API Token Acquisition

The Product Hunt adapter uses the [Product Hunt API 2.0](https://api.producthunt.com/v2/docs) (GraphQL). To obtain a token:

1. Create an application at [Product Hunt OAuth Applications](https://www.producthunt.com/v2/oauth/applications).
2. Use the **developer_token** from the dashboard for server-side scripts (does not expire, linked to your account).
3. For OAuth flows, see [OAuth Client Only Authentication](https://api.producthunt.com/v2/docs/oauth_client_only_authentication/oauth_token_ask_for_client_level_token).

**Note**: The Product Hunt API must not be used for commercial purposes without contacting [hello@producthunt.com](mailto:hello@producthunt.com).

### Configuration

```bash
export PRODUCTHUNT_API_TOKEN=your-token
export INGEST_PRODUCTHUNT_ENABLED=1
```

When `PRODUCTHUNT_API_TOKEN` is unset or empty, the adapter returns `[]` and logs at debug. No exception is raised.

### Rate Limits and Retry

- Product Hunt reserves the right to rate-limit applications.
- **429 Too Many Requests** and **5xx** responses: The adapter retries up to 3 times with exponential backoff (1s, 2s, 4s).
- On final failure after retries: returns `[]` without raising.
- Contact Product Hunt for faster access without rate limits.

### Event Mapping

Product launches map to `RawEvent` with:
- `event_type_candidate`: `launch_major`
- `raw_payload`: includes `votesCount`, `commentsCount`, `makers` (list of `{name}`) when available from the API.

---

## NewsAPI {#newsapi}

### Security: API key in URL

NewsAPI passes the API key as a query parameter in the request URL. **Do not log full request URLs** (e.g. in error handlers or debug logs), as this would expose the key. Ensure error messages and exception handlers never include the API key. Prefer logging only the path or a redacted URL (e.g. `https://newsapi.org/v2/...?apiKey=***`).

### API Key Acquisition

The NewsAPI adapter uses the [NewsAPI.org](https://newsapi.org/) Everything endpoint. To obtain a key:

1. Sign up at [newsapi.org/register](https://newsapi.org/register).
2. Use the API key from your account dashboard.
3. Free tier: 100 requests/day.

### Configuration

```bash
export NEWSAPI_API_KEY=your-api-key
export INGEST_NEWSAPI_ENABLED=1
```

Optional: customize search keywords via `INGEST_NEWSAPI_KEYWORDS` (comma-separated) or `INGEST_NEWSAPI_KEYWORDS_JSON` (JSON array).

When `NEWSAPI_API_KEY` is unset or empty, the adapter returns `[]` and logs at debug. No exception is raised.

### Rate Limits

- Free tier: 100 requests/day.
- Paid plans available for higher limits.

### Security: API Key in Request URL

The NewsAPI API key is passed as a query parameter (`apiKey`) in the request URL. **Ensure HTTP clients and middleware do not log full request URLs** to avoid credential exposure. Configure logging to redact or omit query parameters when logging request URLs.

### Event Mapping

Funding-related articles are mapped to `RawEvent` with:

- `event_type_candidate`: `funding_raised`
- `company_name` extracted from title/description heuristics
- `event_time` from article `publishedAt`
- `url`: article URL

---

## GitHub {#github}

### API Token Acquisition

The GitHub adapter uses the [GitHub REST API](https://docs.github.com/en/rest) to fetch repository and organization events. To obtain a token:

1. Create a [Personal Access Token (PAT)](https://github.com/settings/tokens) with `repo` scope (for private repos) or `public_repo` (for public repos only).
2. For org events, ensure the token has access to the organization.
3. Alternatively, use a [GitHub App](https://docs.github.com/en/apps) installation token for production (documented as future enhancement).

### Configuration

```bash
export GITHUB_TOKEN=your-token
export INGEST_GITHUB_ENABLED=1
```

`GITHUB_PAT` is also accepted as an alias for `GITHUB_TOKEN`.

**Required**: At least one of the following must be set:

- **`INGEST_GITHUB_REPOS`**: Comma-separated list of `owner/repo` (e.g., `org1/repo1,org2/repo2`).
- **`INGEST_GITHUB_ORGS`**: Comma-separated list of organization names.

When `GITHUB_TOKEN` (or `GITHUB_PAT`) is unset or empty, the adapter returns `[]` and logs at debug. No exception is raised. When both `INGEST_GITHUB_REPOS` and `INGEST_GITHUB_ORGS` are unset, the adapter is skipped.

**Optional — Owner metadata cache** (reduces API calls across runs):

- **`INGEST_GITHUB_CACHE_DIR`**: Directory for cache file (default: `~/.cache/signalforge`). Metadata is stored in `github_owner_metadata.json`.
- **`INGEST_GITHUB_METADATA_CACHE_TTL_SECS`**: Cache TTL in seconds (default: 86400 = 24 hours). Set to `0` to disable caching.

### Rate Limits and Behavior

- GitHub API rate limits apply (5,000 requests/hour for authenticated requests).
- **429 Too Many Requests**: Adapter retries up to 3 times with exponential backoff (60s, 120s, 300s) or `Retry-After` header when present.
- **401/403/404/500**: Pagination stops for that repo/org; a warning is logged.
- **404**: Repo or org not found; logged at debug.
- **Owner metadata throttling**: A 0.5s delay is applied between org/user metadata fetches to avoid burst rate limiting.
- Events are filtered by `event_time >= since`; pagination continues until the page is full or no more events.

### Security: Token in API Requests

The token is sent in the `Authorization: Bearer <token>` header. Ensure HTTP clients and middleware do not log request headers to avoid credential exposure.

### Event Mapping

Repository and organization events are mapped to `RawEvent` with:

- `event_type_candidate`: `repo_activity`
- `company_name`: org or owner (from repo owner/repo)
- `event_time` from `created_at`
- `url`: repo URL, commit URL (PushEvent), or PR URL (PullRequestEvent)
- `url` is truncated to 2048 characters; `source_event_id` is stable and unique per event

### Company Resolution (Phase 3)

The adapter fetches org/user metadata (`GET /orgs/{owner}` or `GET /users/{owner}`) to obtain the `blog` field. When present and valid, it is normalized to `website_url` in `RawEvent`, enabling the company resolver to match or create companies by domain. If `blog` is empty or points to github.com, `website_url` remains `None` and resolution falls back to name matching.

**Metadata caching**: Org/user metadata is cached to reduce API calls across runs. When cache is enabled (default), repeated ingest runs for the same orgs/repos skip metadata fetches until the TTL expires. This reduces latency and rate-limit usage when many repos share the same owner.

---

## Delaware Socrata {#delaware-socrata}

### Overview

The Delaware Socrata adapter fetches incorporation filings from [Delaware Open Data](https://data.delaware.gov/) via the Socrata SODA API. No API key is required for public datasets.

### Configuration

```bash
export INGEST_DELAWARE_SOCRATA_ENABLED=1
export INGEST_DELAWARE_SOCRATA_DATASET_ID=your-dataset-id
```

**Required**: `INGEST_DELAWARE_SOCRATA_DATASET_ID` must be set to a valid Socrata dataset ID (e.g., 8-character alphanumeric from data.delaware.gov).

**Optional**: `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` — column name for server-side date filtering (default: `file_date`). Only alphanumeric and underscore allowed; invalid values fall back to client-side filtering. If the dataset uses a different date column (e.g., `insp_date`, `created_at`), set this. On 400 (invalid column), the adapter retries without `$where` and filters client-side.

### Dataset IDs and SoQL Examples

**Dataset IDs** are typically 8-character alphanumeric (e.g., `384s-wygj`). Browse [data.delaware.gov](https://data.delaware.gov/) and search for "corporation", "incorporation", "entity filings", or "Division of Corporations" to find incorporation-style datasets. As of Issue #250, no specific Division of Corporations incorporation filings dataset has been confirmed; users should verify dataset IDs and schemas on the portal.

**Base URL** (SODA API):

```
https://data.delaware.gov/resource/{dataset_id}.json
```

**SoQL examples** used by the adapter:

| Parameter | Example | Description |
|-----------|---------|-------------|
| `$limit` | `1000` | Page size (default 1000) |
| `$offset` | `0`, `1000`, `2000` | Pagination offset |
| `$where` | `file_date >= '2025-01-01'` | Server-side date filter (when `INGEST_DELAWARE_SOCRATA_DATE_COLUMN` is set) |

**Example request** (with date filter):

```
GET https://data.delaware.gov/resource/384s-wygj.json?$limit=1000&$offset=0&$where=file_date%20%3E%3D%20%272025-01-01%27
```

**Expected schema** for incorporation-style datasets:

- **Entity name**: `entity_name`, `entityname`, `company_name`, `name`, or `restname`
- **Date**: `file_date`, `filedate`, `insp_date`, `created_at`, or `date` (ISO 8601 or `YYYY-MM-DD`)
- **Entity type** (optional): `entity_type`, `entitytype`, or `type` (e.g., LLC, Corp)

The adapter supports flexible field mapping; datasets with different column names may work if they match the keys above.

When `INGEST_DELAWARE_SOCRATA_DATASET_ID` is unset or empty, the adapter returns `[]` and logs at debug. No exception is raised.

### Rate Limits and Behavior

- Public SODA APIs typically allow reasonable request rates.
- **429 Too Many Requests**: Adapter retries up to 3 times with exponential backoff (60s, 120s, 300s).
- **400**: May indicate invalid `$where` column; adapter retries once without date filter and filters client-side.
- **401/403/404/500**: Pagination stops; a warning is logged.
- Events are filtered by `event_time >= since`; pagination uses `$limit` and `$offset`.

### Event Mapping

Incorporation filings are mapped to `RawEvent` with:

- `event_type_candidate`: `incorporation`
- `company_name`: from entity name field (tries `entity_name`, `entityname`, `company_name`, `name`, `restname`)
- `event_time` from date field (tries `file_date`, `filedate`, `insp_date`, `created_at`, `date`)
- `url`: Delaware Open Data resource URL
- `source_event_id`: stable and unique per row (max 255 chars)

### Company Resolution

Incorporation filings typically lack `domain` and `website_url`. The company resolver falls back to **name matching** (normalized company name). As a result:

- **Possible duplicate companies**: Similar names (e.g., "Acme LLC" vs "Acme Inc") may resolve to separate companies.
- **Deduplication**: Consider future enhancements (e.g., alias merging, manual merge workflows) if duplicate incorporation entities become an issue.
- **Domain-based resolution**: When a dataset provides a website or domain field, extend the adapter's field mapping to populate `website_url` for more accurate resolution.

---

## TestAdapter

For tests only. When `INGEST_USE_TEST_ADAPTER=1`, `_get_adapters()` returns only `[TestAdapter()]`; no production adapters are used.

Returns three hardcoded `RawEvent`s:

- funding_raised
- job_posted_engineering
- cto_role_posted

---

## Error Handling

One adapter failure does not stop the daily ingest. When an adapter raises during `run_ingest`:

1. The exception is logged with `logger.exception`.
2. The error message is appended to the job's `error_message`.
3. The loop continues to the next adapter.
4. The job completes with `status="completed"`; `errors_count` and `error` reflect failures.

This ensures that a Crunchbase API outage, for example, does not prevent other adapters from running.

---

## GitHub (when configured)

### Cache path for multi-tenant / containerized setups

The GitHub adapter caches owner metadata to reduce API calls. Default cache directory: `~/.cache/signalforge`. For multi-tenant or containerized deployments:

- Set `INGEST_GITHUB_CACHE_DIR` to a tenant-specific or writable path (e.g. `/var/cache/signalforge/{tenant_id}`).
- Ensure the process has write access to the directory.
- Set `INGEST_GITHUB_METADATA_CACHE_TTL_SECS=0` to disable caching if a shared cache is not appropriate.

---

## Delaware Socrata / Incorporation (when configured)

### Company resolution and duplicates

Incorporation events from Delaware Open Data often lack `domain` and `website_url`; resolution falls back to name-only matching via `normalize_name`. This can create duplicate company records when the same entity appears with slight name variations (e.g. "Acme Inc" vs "Acme, Inc."). Future improvements may include fuzzy matching, manual merge workflows, or domain enrichment from external sources.
