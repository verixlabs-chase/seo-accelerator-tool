"""Vercel Python function entrypoint.

Configure the Vercel project root as ``backend``. Vercel discovers this module
under ``api/`` and serves the FastAPI ASGI application.
"""

from app.main import app

__all__ = ["app"]
