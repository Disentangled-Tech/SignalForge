# Implementation Plan: GitHub Issue #26 — Secure Internal Job Endpoints

**Issue**: [Secure internal job endpoint](https://github.com/Disentangled-Tech/SignalForge/issues/26)

**Acceptance Criteria**:
- Requires secret token
- Cannot be accessed publicly

**Endpoints**:
- `POST /internal/run_scan`
- `POST /internal/run_briefing`

---

## Architecture Context (CURSOR_PRD.md)

The PRD Internal Job Endpoints section states:

> Cloudways cron will call:
> - POST /internal/scan
> - POST /internal/briefing
>
> Requirements:
> - require secret token header
> - create JobRun record
> - never crash server
> - return JSON status

**Note**: The PRD uses `/internal/scan` and `/internal/briefing`; the implementation uses `/internal/run_scan` and `/internal/run_briefing`. The latter are more descriptive and already in use by scripts and tests. No path change recommended.

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Token validation | Implemented | `app/api/internal.py:_require_internal_token` |
| Header | `X-Internal-Token` | Required by `Header(...)` dependency |
| Config | `INTERNAL_JOB_TOKEN` | `app/config.py`, `.env.example` |
| Scripts | Use token | `scripts/run_scan.sh`, `scripts/run_briefing.sh` |
| Tests | Valid/wrong/missing token | `tests/test_internal.py` |
| Missing token | 422 Unprocessable Entity | FastAPI default for missing required header |
| Wrong token | 403 Forbidden | `_require_internal_token` |
| Empty config token | Rejects all requests | `if not expected` guard |

---

## Gap Analysis: Issue #26 vs Current Implementation

| Requirement | Current State | Gap |
|-------------|---------------|-----|
| **Requires secret token** | ✅ Implemented | None — `X-Internal-Token` header required; wrong/empty token → 403 |
| **Cannot be accessed publicly** | ✅ Achieved via token | None — Without token, requests fail (422 or 403). Public callers cannot succeed. |

**Conclusion**: The acceptance criteria are already met. The implementation plan below addresses **hardening** and **documentation** gaps to align with security-first design and PRD guidance.

---

## Recommended Hardening (Non-Breaking)

### 1. Constant-Time Token Comparison

**Risk**: String comparison `!=` can leak timing information, enabling timing attacks to guess the token byte-by-byte.

**Fix**: Use `secrets.compare_digest()` for constant-time comparison.

```python
# app/api/internal.py
import secrets

def _require_internal_token(x_internal_token: str = Header(...)) -> None:
    expected = get_settings().internal_job_token
    if not expected or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=403, detail="Invalid internal token")
```

**Tests**: Existing tests pass; add a test that timing is not trivially distinguishable (optional; `compare_digest` is well-tested in stdlib).

---

### 2. Hide Internal Endpoints from OpenAPI Docs

**Risk**: When `DEBUG=true`, `/docs` and `/redoc` expose internal endpoint paths and parameters. While the token is not exposed, reducing attack surface is prudent.

**Fix**: Set `include_in_schema=False` on the internal router or endpoints.

```python
# app/api/internal.py
router = APIRouter(prefix="/internal", include_in_schema=False)
```

**Impact**: Internal endpoints no longer appear in Swagger/ReDoc. Cron scripts and tests unaffected (they call URLs directly).

---

### 3. Audit Logging for Failed Auth (Optional)

**Benefit**: Security auditing — know when someone attempts to access internal endpoints without a valid token.

**Fix**: Log at WARNING level when token validation fails (do not log the token or provided value).

```python
def _require_internal_token(x_internal_token: str = Header(...)) -> None:
    expected = get_settings().internal_job_token
    if not expected or not secrets.compare_digest(x_internal_token, expected):
        logger.warning("Internal endpoint auth failed: invalid or missing token")
        raise HTTPException(status_code=403, detail="Invalid internal token")
```

---

### 4. Startup Validation (Optional, Configurable)

**Benefit**: Fail fast in production if `INTERNAL_JOB_TOKEN` is empty, preventing accidental deployment without token.

**Approach**: In `create_app()` or lifespan, when `debug=False`, check `internal_job_token` and log CRITICAL (or raise) if empty. Allow override via env var `SKIP_INTERNAL_TOKEN_CHECK=true` for local dev without cron.

**Recommendation**: Defer. Current behavior (reject all requests when token empty) is safe. Startup validation adds complexity; scripts already fail if token unset.

---

## Documentation Updates

| File | Change |
|------|--------|
| `README.md` | Fix paths: `/internal/scan` → `/internal/run_scan`, `/internal/briefing` → `/internal/run_briefing` |
| `rules/CURSOR_PRD.md` | Align paths with implementation (or add note that run_scan/run_briefing are the actual paths) |
| `.env.example` | Ensure comment emphasizes: "Required in production. Generate: `python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"`" |

---

## Implementation Checklist

| Task | Priority | Breaking? |
|------|----------|-----------|
| 1. Use `secrets.compare_digest` for token comparison | High | No |
| 2. Set `include_in_schema=False` on internal router | Medium | No |
| 3. Add audit log for failed auth attempts | Low | No |
| 4. Update README paths | Low | No |
| 5. Update PRD or add path note | Low | No |
| 6. Strengthen .env.example token guidance | Low | No |

---

## Test Plan

1. **Existing tests** (`tests/test_internal.py`): All must pass unchanged.
2. **Regression**: Run `pytest tests/test_internal.py -v`.
3. **Manual**: With `INTERNAL_JOB_TOKEN` set, `curl -X POST http://localhost:8000/internal/run_scan -H "X-Internal-Token: $INTERNAL_JOB_TOKEN"` returns 200.
4. **Manual**: Without header or wrong token returns 422/403.
5. **Docs**: With `DEBUG=true`, verify `/docs` does not list internal endpoints (after step 2).

---

## Out of Scope (Per PRD Simplicity)

- **Rate limiting**: Adds complexity; token auth is sufficient for single-operator V1.
- **IP allowlist**: Cloudways IPs can change; token is more portable.
- **Token rotation**: Static token is acceptable for cron; document rotation procedure in README if needed.

---

## Summary

The internal job endpoints **already meet** the acceptance criteria for Issue #26. The recommended changes are **hardening and documentation** only:

1. **Constant-time comparison** — Security best practice.
2. **Hide from OpenAPI** — Reduce attack surface.
3. **Audit logging** — Optional but useful.
4. **Doc alignment** — README/PRD paths match implementation.

No breaking changes to existing functionality.
