# Implementation Plan: GitHub Issue #15 — LLM Client Abstraction

**Issue**: [LLM client abstraction](https://github.com/Disentangled-Tech/SignalForge/issues/15)  
**Acceptance Criteria**:
- Swappable providers
- Logs prompt + token usage

**Tasks from issue**:
- Provider interface
- Model configuration
- Timeout & retry
- Model Router (no hardcoding): `analyze_model = reasoning_model`, `json_model = cheap_model`, `outreach_model = conversational_model`

---

## Architecture Context

The PRD specifies:
- LLM is a reasoning component only (classify stage, interpret signals, generate explanations, draft outreach)
- Provider abstraction module
- Log LLM failures

**Model role mapping**:

| Role        | Use case                    | Default model   |
|-------------|-----------------------------|-----------------|
| REASONING   | Stage, pain, explanation    | gpt-4o          |
| JSON        | Briefing entry JSON         | gpt-4o-mini     |
| OUTREACH    | Outreach draft              | gpt-4o-mini     |

---

## Configuration

| Env var               | Default     | Description                          |
|-----------------------|-------------|--------------------------------------|
| LLM_MODEL_REASONING   | gpt-4o      | Analysis: stage, pain, explanation    |
| LLM_MODEL_JSON        | gpt-4o-mini | Cheap: briefing entry JSON           |
| LLM_MODEL_OUTREACH    | gpt-4o-mini | Conversational: outreach draft       |
| LLM_TIMEOUT           | 60          | Seconds per request                  |
| LLM_MAX_RETRIES       | 3           | Retries on rate limit / timeout      |
| LLM_MODEL             | gpt-4o-mini | Legacy: used for all roles if above unset |

---

## Implementation Summary

- **Model Router**: `get_llm_provider(role=ModelRole.REASONING|JSON|OUTREACH)` returns provider configured for that role
- **Provider cache**: Keyed by `provider_name:role` for one instance per role
- **Retry**: Rate limit, timeout, and connection errors trigger exponential backoff
- **Logging**: INFO = prompt preview (100 chars) + tokens + latency; DEBUG = full prompt
