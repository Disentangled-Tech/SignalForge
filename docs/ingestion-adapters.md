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
