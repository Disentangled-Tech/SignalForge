"""
Centralized test credentials and secrets.

All test-only credentials are loaded from environment variables when available,
with clearly non-production placeholders as fallbacks. This avoids hardcoded
secrets in test fixtures while satisfying Snyk Code security checks.
"""

from __future__ import annotations

import os

# Passwords: load from env; fallback is a short placeholder (not a real credential)
TEST_PASSWORD = os.environ.get("TEST_PASSWORD") or "x"
TEST_PASSWORD_WRONG = os.environ.get("TEST_PASSWORD_WRONG") or "y"
TEST_PASSWORD_INTEGRATION = os.environ.get("TEST_PASSWORD_INTEGRATION") or "z"

# Usernames for test fixtures
TEST_USERNAME = "admin"
TEST_USERNAME_VIEWS = "testuser"  # used in settings/briefing view mocks

# API keys and tokens: load from env; fallback is obviously a placeholder
TEST_LLM_API_KEY = os.environ.get("TEST_LLM_API_KEY") or "k"
TEST_ACCESS_TOKEN_PLACEHOLDER = os.environ.get("TEST_ACCESS_TOKEN") or "a.b.c"

# App config used by conftest and view tests
TEST_SECRET_KEY = os.environ.get("TEST_SECRET_KEY") or "test-secret-key"
TEST_INTERNAL_JOB_TOKEN = os.environ.get("TEST_INTERNAL_JOB_TOKEN") or "test-internal-token"

# SMTP (email service tests)
TEST_SMTP_PASSWORD = os.environ.get("TEST_SMTP_PASSWORD") or "x"
