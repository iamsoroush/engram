# One Router Module Per Domain — `main.py` Is Wiring-Only (2026-07-04)

The 1189-line `app/main.py` (81 inline handlers across ~14 domains) is dissolved: `main.py` is now
**wiring-only** (app construction + `/health` + `include_router`), and each domain is a
self-contained `APIRouter` in `app/<domain>_api.py` that delegates to `app/services/*`. This
finishes the pattern the `qa`/`insights`/`smart_lists`/`feedback` routers already set. Standing
convention: **new endpoints go in the matching domain router (or a new `<domain>_api.py`), never
inline in `main.py`.** Request/response models likewise live in per-domain `app/schemas/<domain>.py`
(`schemas/api.py` kept as a compat re-export aggregator). Behavior-preserving — the route surface
(paths, methods, tags, auth dependencies) is invariant, enforced by the new
`tests/test_route_surface.py` snapshot guard, and verified green through the e2e-stack P0 + p1-01
suites. Module map: [backend/README.md](../backend/README.md) "Code layout".
