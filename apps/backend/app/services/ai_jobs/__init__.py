"""AI processing jobs service.

This package was split out of the former monolithic ``app/services/ai_jobs.py``. Every public name
that module exposed is re-exported here unchanged, so existing ``from app.services.ai_jobs import X``
imports keep working, as does ``app.services.ai_jobs.X`` attribute access (including monkeypatch
targets such as ``match_patient_from_patient_information`` and ``settings``).

Internals are split by concern into base / config / intents / recovery / orchestration / context /
reports / worker submodules. No behavior changed in the split.
"""

# Re-exported so ``app.services.ai_jobs.settings`` and the
# ``app.services.ai_jobs.match_patient_from_patient_information`` monkeypatch target keep resolving
# exactly as they did when this was a single module.
from app.config import settings as settings
from app.services.patient_matching import (
    match_patient_from_patient_information as match_patient_from_patient_information,
)

from app.services.ai_jobs.base import *  # noqa: F401,F403
from app.services.ai_jobs.config import *  # noqa: F401,F403
from app.services.ai_jobs.intents import *  # noqa: F401,F403
from app.services.ai_jobs.recovery import *  # noqa: F401,F403
from app.services.ai_jobs.orchestration import *  # noqa: F401,F403
from app.services.ai_jobs.context import *  # noqa: F401,F403
from app.services.ai_jobs.reports import *  # noqa: F401,F403
from app.services.ai_jobs.worker import *  # noqa: F401,F403
