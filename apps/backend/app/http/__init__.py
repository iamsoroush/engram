"""Reusable HTTP plumbing shared by the route modules (not routing itself).

Small, framework-level helpers — byte-range responses for media streaming, multipart form
parsing — that several routers need. Kept out of ``main.py`` (which is app construction + wiring)
and out of the per-domain routers so they have a single, unit-testable home.
"""
