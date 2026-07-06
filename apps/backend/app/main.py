"""FastAPI application construction and router wiring.

This module is intentionally thin: it builds the ``app`` object (Sentry, Prometheus, CORS), exposes
the ``/health`` probe, and mounts the per-domain routers. All route handlers live in their domain
router modules (``app/<domain>_api.py``); no request logic lives here. See ``docs/backend/README.md``
for the router map.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.observability import init_sentry, instrument

API_V1_PREFIX = "/api/v1"

# Error tracking is initialized once, before the app is built, so any startup-time errors are
# captured. No-op when BACKEND_SENTRY_DSN is empty (dev / Basic / unconfigured envs unaffected).
init_sentry()

app = FastAPI(
    title=settings.app_name,
    docs_url=f"{API_V1_PREFIX}/docs",
    redoc_url=f"{API_V1_PREFIX}/redoc",
    openapi_url=f"{API_V1_PREFIX}/openapi.json",
)

# Prometheus instrumentation: exposes /metrics (NOT under /api/v1) for the internal-network scrape.
instrument(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix=API_V1_PREFIX)


@api_v1.get("/health")
def health_check() -> dict[str, str]:
    """Check whether the API process is running and able to serve requests."""
    return {"status": "ok"}


app.include_router(api_v1)

# Per-domain routers extracted from this file. Each is a thin, self-contained APIRouter mounted at
# /api/v1 (its handlers delegate to app/services/*). See docs/backend/README.md for the map.
from app.auth_api import auth_api  # noqa: E402
from app.tenant_config_api import tenant_config_api  # noqa: E402
from app.patients_api import patients_api  # noqa: E402
from app.sessions_api import sessions_api  # noqa: E402
from app.captures_api import captures_api  # noqa: E402
from app.worklist_api import worklist_api  # noqa: E402
from app.aftercare_api import aftercare_api  # noqa: E402
from app.shares_api import shares_api  # noqa: E402
from app.team_api import team_api  # noqa: E402

app.include_router(auth_api)
app.include_router(tenant_config_api)
app.include_router(patients_api)
app.include_router(sessions_api)
app.include_router(captures_api)
app.include_router(worklist_api)
app.include_router(aftercare_api)
app.include_router(shares_api)
app.include_router(team_api)

# Internal AI-engine → backend worker-callback API (distinct trust boundary). Self-contained router.
from app.internal_api import internal_api  # noqa: E402

app.include_router(internal_api)

# Post-session patient Q&A (Pro payload of the patient surface; AES-402). Self-contained routers.
from app.qa_api import qa_api, qa_internal_api  # noqa: E402

app.include_router(qa_api)
app.include_router(qa_internal_api)

# Smart lists + lot/product recall (Pro; AES-501 / AES-502). Self-contained router.
from app.smart_lists_api import smart_lists_api  # noqa: E402

app.include_router(smart_lists_api)

# AI-quality feedback harvester (eval golden-set; eval-epic §1b). Self-contained router.
from app.feedback_api import feedback_api  # noqa: E402

app.include_router(feedback_api)

# Clinic insights (owner/admin analytics; treatments payload Pro-gated). Self-contained router.
from app.insights_api import insights_api  # noqa: E402

app.include_router(insights_api)

# Unified attention roll-up (Close-the-day sweep + indicator; AES-1001). Self-contained router.
from app.attention_api import attention_api  # noqa: E402

app.include_router(attention_api)
