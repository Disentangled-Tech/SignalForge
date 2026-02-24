# Ingestion Adapter Interface (Issue #89)

This document describes the pluggable adapter framework for signal sources. Adapters fetch raw events from external sources; the ingestion pipeline normalizes, resolves companies, and stores events with deduplication.

## Adapter Contract

Implement the `SourceAdapter` abstract base class:

```python
from abc import ABC, abstractmethod
from datetime import datetime
from app.schemas.signal import RawEvent

class SourceAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this adapter (e.g. 'crunchbase', 'producthunt')."""
        ...

    @abstractmethod
    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch raw events from source since given datetime."""
        ...
```

- **source_name**: Unique identifier used for the `source` column in `signal_events`. Used for deduplication.
- **fetch_events(since)**: Return a list of `RawEvent` instances. The pipeline handles normalization, company resolution, and storage.

## RawEvent Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `company_name` | str | Yes | Company name |
| `domain` | str \| None | No | Domain (e.g. example.com) |
| `website_url` | str \| None | No | Full website URL |
| `company_profile_url` | str \| None | No | Profile URL (website or LinkedIn) |
| `event_type_candidate` | str | Yes | Event type; must be in canonical taxonomy |
| `event_time` | datetime | Yes | When the event occurred |
| `title` | str \| None | No | Event title |
| `summary` | str \| None | No | Event summary |
| `url` | str \| None | No | Event URL |
| `source_event_id` | str \| None | No | Upstream ID for deduplication |
| `raw_payload` | dict \| None | No | Original payload for audit |

## Normalization Flow

1. **Validate event type**: `event_type_candidate` must be in the pack taxonomy `signal_ids` (production) or `SIGNAL_EVENT_TYPES` when pack is None (test fallback). Unknown types are skipped.
2. **Build CompanyCreate**: From `company_name`, `domain`, `website_url`, `company_profile_url`. LinkedIn URLs map to `company_linkedin_url`.
3. **Build signal event data**: Maps to `SignalEvent` columns with default `confidence=0.7`.

## Deduplication Rules

- **Unique constraint**: `(source, source_event_id)` WHERE `source_event_id IS NOT NULL`
- If `source_event_id` is provided and a matching row exists, the event is skipped (no insert).
- Events with `source_event_id=None` are not deduplicated; multiple such events may be stored.

## How to Add a New Adapter

1. Create a new file in `app/ingestion/adapters/` (e.g. `crunchbase_adapter.py`).
2. Implement `SourceAdapter`:

   ```python
   from app.ingestion.base import SourceAdapter
   from app.schemas.signal import RawEvent

   class CrunchbaseAdapter(SourceAdapter):
       @property
       def source_name(self) -> str:
           return "crunchbase"

       def fetch_events(self, since: datetime) -> list[RawEvent]:
           # Fetch from API/RSS, return RawEvent list
           ...
   ```

3. Use `run_ingest(db, adapter, since)` to run the pipeline.
4. Ensure `event_type_candidate` values match the pack taxonomy `signal_ids` (see `packs/fractional_cto_v1/taxonomy.yaml`). For tests without a pack, `app/ingestion/event_types.py` provides a fallback.

## Canonical Event Types

Production uses pack taxonomy (e.g. `packs/fractional_cto_v1/taxonomy.yaml`). See `docs/v2-spec.md` §3. Examples: `funding_raised`, `job_posted_engineering`, `cto_role_posted`, `launch_major`, etc.
