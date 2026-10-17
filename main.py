"""Vercel/FastAPI entrypoint.

Vercel detects this module and serves the exported FastAPI ``app`` directly.
"""
from app.main import app

__all__ = ["app"]
