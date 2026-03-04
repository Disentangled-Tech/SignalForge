# ADR-012: LLM Provider — Anthropic (Claude) Only

**Status:** Accepted  
**Date:** 2026-03-04

---

## Context

SignalForge uses an LLM for analysis, Scout evidence extraction, outreach drafting, and event interpretation. The codebase previously supported two providers (OpenAI and Anthropic) via `app/llm/router.py` and environment variable `LLM_PROVIDER`. Maintaining two providers increases surface area for config, testing, and security review, and the product direction is to standardize on Claude for reasoning quality and safety alignment.

---

## Decision

- **Single provider:** The application supports **Anthropic (Claude) only** as the LLM provider.
- **OpenAI removed:** The OpenAI provider implementation (`app/llm/openai_provider.py`) and its dependency (`openai` in pyproject.toml) are removed. `LLM_PROVIDER` must be set to `anthropic` (or omitted; default is `anthropic`).
- **Config and docs:** `CLAUDE.md`, `.env.example`, and `app/config.py` document Anthropic-only. Default model names are Claude models (e.g. `claude-3-5-haiku-20241022`, `claude-sonnet-4-20250514`). Any reference to OpenAI or multiple providers is removed or updated.
- **Runtime behavior:** If a user sets `LLM_PROVIDER` to any value other than `anthropic`, the router raises `ValueError` with a message that the supported provider is Anthropic.

---

## Consequences

- **Positive:** Single code path and dependency set; simpler config and ops; consistent model behavior and safety posture.
- **Negative:** Deployments that relied on `LLM_PROVIDER=openai` will break and must switch to Anthropic and obtain an API key. No migration path for OpenAI-specific config beyond reconfiguration.
- **References:** `app/llm/router.py`, `app/llm/__init__.py`, `app/config.py`, `CLAUDE.md`, `.env.example`; ADR-011 (interpretation layer is provider-agnostic).
