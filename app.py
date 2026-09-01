"""Vercel ASGI entrypoint for the Relay API."""

from backend.app.main import app


__all__ = ["app"]
