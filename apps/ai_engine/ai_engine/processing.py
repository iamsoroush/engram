import json
import logging
import re
from time import sleep
from typing import Any

from ai_engine.config import settings

# ``processing`` is a transitional re-export shim (Axis-1 increments 1–2): the shared worker
# infrastructure now lives under ``ai_engine.core`` and the job runners under ``ai_engine.jobs``, but
# evals (``eval/*``) and unit tests still import these names from ``ai_engine.processing`` and patch
# them here. The imports below rebind the moved names into this module so
# ``from ai_engine.processing import X`` keeps working until the shim is deleted (increment 5). Any
# job body still defined below resolves its dependencies in this namespace, so
# ``patch("ai_engine.processing.X")`` still intercepts those calls.
from ai_engine.core.backend_client import BackendClient  # noqa: F401
from ai_engine.core.domain import domain_framing
from ai_engine.core.fixtures import (  # noqa: F401
    TEST_CAPTURE_TEXT_BY_FILENAME,
    TEST_FINAL_SUMMARY,
    is_fixture_capture,
)
from ai_engine.core.gateway import (  # noqa: F401
    _MeteredChat,
    _MeteredClient,
    _MeteredCompletions,
    _pending_audio_seconds,
    _record_gateway_usage,
    _usage_sink,
    arm_usage_sink,
    drain_usage_sink,
    gateway_client,
    gateway_settings_for,
    resolve_model,
    resolve_reasoning_effort,
    set_pending_audio_seconds,
    transcription_is_configured,
)
from ai_engine.core.media import (  # noqa: F401
    CAPTION_JPEG_QUALITY,
    CAPTION_MAX_EDGE,
    CAPTION_PRODUCT_LABEL_MAX_EDGE,
    audio_duration_seconds,
    audio_to_flac_mono_16khz_base64,
    downscale_image_for_caption,
    image_to_data_url,
)
from ai_engine.core.text import (  # noqa: F401
    _LATIN_DIGITS,
    TRANSCRIPTION_LANGUAGE_NAMES,
    enrichment_language_directive,
    normalize_digits_to_latin,
    transcription_language_directive,
)
from ai_engine.core.util import clamp_confidence, utc_now  # noqa: F401
from ai_engine.jobs.capture import run_capture_processing_job  # noqa: F401
from ai_engine.jobs.capture_audio import (  # noqa: F401
    ASSIGNMENT_INTENT_BASES,
    PATIENT_INFORMATION_FIELDS,
    TRANSCRIPTION_LANGUAGES,
    completed_audio_metadata,
    detected_patient_from_patient_information,
    empty_patient_information,
    normalize_intents,
    parse_structured_transcription_output,
    structured_transcription_from_text,
    transcribe_audio_content,
    transcription_prompt,
)
from ai_engine.jobs.capture_note import raw_note_text  # noqa: F401
from ai_engine.jobs.capture_photo import (  # noqa: F401
    CAPTION_LOW_CONFIDENCE_THRESHOLD,
    PAIRING_LATERALITIES,
    PAIRING_PHASES,
    caption_image_content,
    caption_output_metadata,
    caption_prompt,
    normalize_caption_pairing,
    parse_caption_output,
)
from ai_engine.jobs.captures_common import (  # noqa: F401
    NOT_DETECTED_PATIENT,
    CaptureProcessingOutput,
    DetectedPatientOutput,
    capture_detected_patient,
    capture_processing_output,
    completed_metadata,
    output_key_for_capture,
    partial_metadata,
    placeholder_text_for_capture,
)
from ai_engine.jobs.patient_memory import (  # noqa: F401
    completed_patient_memory_output,
    parse_patient_memory_output,
    patient_memory_prompt,
    run_patient_memory_job,
)
from ai_engine.jobs.qa_draft import (  # noqa: F401
    completed_qa_draft_output,
    parse_qa_draft_output,
    qa_draft_prompt,
    run_qa_draft_job,
)
from ai_engine.jobs.qa_revise import (  # noqa: F401
    completed_qa_revise_output,
    parse_qa_revise_output,
    qa_revise_prompt,
    run_qa_revise_job,
)
from ai_engine.jobs.safety_reconcile import (  # noqa: F401
    _safety_flag_key,
    parse_safety_reconcile_output,
    reconcile_safety_flags,
    safety_reconcile_json_schema,
    safety_reconcile_prompt,
)
from ai_engine.jobs.session_synthesis import (  # noqa: F401
    SESSION_SYNTHESIS_OUTPUT_VERSION,
    SYNTHESIS_LANGUAGES,
    SYNTHESIS_SECTION_IDS,
    SYNTHESIS_SECTION_TITLES_FA,
    SYNTHESIS_SECTIONS,
    completed_session_output,
    completed_session_synthesis_output,
    first_capture_by_text,
    is_expected_test_fixture,
    parse_session_synthesis_output,
    report_synthesis_json_schema,
    report_synthesis_prompt,
    run_session_processing_job,
    session_synthesis_skip_output,
    synthesis_section_title,
    synthesize_session_report,
)


logger = logging.getLogger(__name__)
