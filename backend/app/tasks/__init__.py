"""Celery task package.

Task modules are loaded explicitly by the Celery application.  Keeping package
initialization side-effect free is important because API startup imports the
Celery application while the intelligence orchestrator is still being built.
Eagerly importing every task module here creates a circular import and prevents
the production ASGI application from starting.
"""
