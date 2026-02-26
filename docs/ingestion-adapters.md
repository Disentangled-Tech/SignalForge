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
