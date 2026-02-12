"""
Gunicorn configuration for SignalForge production deployment.

Usage:
    gunicorn app.main:app -c gunicorn.conf.py
"""

import multiprocessing

# Bind to all interfaces on port 8000
bind = "0.0.0.0:8000"

# Worker processes: CPU cores * 2 + 1 (Gunicorn recommendation)
workers = multiprocessing.cpu_count() * 2 + 1

# Use Uvicorn's ASGI worker for FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Request timeout (seconds) — generous for LLM calls
timeout = 120

# Keep-alive connections (seconds)
keepalive = 5

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"

