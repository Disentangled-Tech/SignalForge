# Text Extraction (HTML → Plain Text)

Fetched HTML is converted to plain text by a single shared utility so that scan, Scout, and monitor all use consistent extraction behavior. Aligned with GitHub Issue #12.

## Implementation

- **Module:** `app/services/extractor.py`
- **Function:** `extract_text(html: str | None, *, max_length: int | None = None) -> str` — returns `""` for `None` or empty input; optional `max_length` overrides the default 8000-character cap when provided.

## Behavior

- **Strip set:** Before extracting text, the following tags are removed entirely: `script`, `style`, `nav`, `footer`, `header`, `aside`. This removes nav/footer noise and non-content markup.
- **Output:** Plain text only — no HTML tags, whitespace normalized to single spaces.
- **Length limit:** Output is capped at ~8k characters (`MAX_TEXT_LENGTH = 8000`).

## Call sites

| Consumer | Use |
| -------- | --- |
| `app/services/page_discovery.py` | Company scan: fetch → extract_text → validity check (>100 chars) |
| `app/services/scout/discovery_scout_service.py` | Scout: fetch → extract_text → concatenate into PAGE_CONTENT for LLM |
| `app/monitor/runner.py` | Monitor: fetch → extract_text → diff/snapshot (min 100 chars) |
| `scripts/diagnose_scan.py` | Diagnostics: fetch → extract_text → report length vs MIN_TEXT_LENGTH |

No pack-specific logic; extraction is a shared utility used before evidence or signals are formed. See ADR-010 for the distinction between this HTML extractor and the Evidence-Bundle entity/event extractor in `app/extractor/`.
