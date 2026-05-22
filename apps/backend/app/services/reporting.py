import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureType, Patient, PatientIdentifier, Session

REPORT_MODEL_VERSION = "2026-05-21.structured-report.v1"
DEFAULT_REPORT_TEMPLATE_KEY = "default"


@dataclass(frozen=True)
class ReportTemplate:
    """Central report template definition for rendered reports."""

    key: str
    clinic_name: str
    clinic_information: tuple[str, ...]
    section_order: tuple[Literal["clinic_header", "patient_information", "body"], ...]


# TODO(report-templates): Replace this singleton with tenant-aware multi-template selection.
DEFAULT_REPORT_TEMPLATE = ReportTemplate(
    key=DEFAULT_REPORT_TEMPLATE_KEY,
    clinic_name="AesMem Demo Clinic",
    clinic_information=("Clinical memory report",),
    section_order=("clinic_header", "patient_information", "body"),
)


def get_report_template(template_key: str | None = None) -> ReportTemplate:
    """Return the report template for a stable template key."""
    safe_key = template_key or DEFAULT_REPORT_TEMPLATE_KEY
    # TODO(report-templates): Support additional template keys and validation here.
    if safe_key != DEFAULT_REPORT_TEMPLATE_KEY:
        raise ValueError("Unsupported report template")
    return DEFAULT_REPORT_TEMPLATE


def report_template_payload(template_key: str | None = None) -> dict[str, str]:
    """Serialize the singleton template for the AI engine boundary."""
    template = get_report_template(template_key)
    content = "\n".join(
        [
            "# Clinic Information",
            "",
            f"Clinic: {template.clinic_name}",
            *template.clinic_information,
            "",
            "# Patient Information",
            "",
            "{{ patient_information }}",
            "",
            "# Body",
            "",
            "{{ body }}",
            "",
        ]
    )
    return {"key": template.key, "content": content}


def report_template_context(template_key: str | None = None) -> dict[str, Any]:
    """Return frontend-renderable template context that is not AI-generated."""
    template = get_report_template(template_key)
    return {
        "key": template.key,
        "clinic": {
            "name": template.clinic_name,
            "information": list(template.clinic_information),
        },
    }


def empty_report_model(*, title: str | None, template_key: str | None = None) -> dict[str, Any]:
    """Create an empty structured report model."""
    template = get_report_template(template_key)
    return {
        "schemaVersion": REPORT_MODEL_VERSION,
        "templateKey": template.key,
        "title": title or "Untitled session",
        "sections": [],
        "findings": [],
        "sourceReferences": [],
    }


def structured_report_from_markdown_body(
    *,
    title: str | None,
    body: str,
    template_key: str | None,
    findings: list[dict[str, Any]] | None = None,
    source_capture_ids: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Wrap generated body markdown in the internal structured report model."""
    template = get_report_template(template_key)
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    return {
        "schemaVersion": REPORT_MODEL_VERSION,
        "templateKey": template.key,
        "title": title or "Untitled session",
        "sections": [
            {
                "id": "clinical-report",
                "title": "Clinical report",
                "blocks": [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs],
            }
        ],
        "findings": findings or [],
        "sourceReferences": [
            {"type": "capture", "captureId": capture_id}
            for capture_id in (source_capture_ids or [])
            if _is_uuid_like(capture_id)
        ],
        "generatedAt": generated_at,
    }


def patient_information_from_assignment(db: DbSession | None, session: Session) -> dict[str, Any]:
    """Load patient information from the assigned patient record, never from generated body text."""
    if db is None or session.patient_id is None:
        return {
            "source": "session-assignment",
            "status": "unassigned",
            "patientId": str(session.patient_id) if session.patient_id else None,
        }

    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        return {"source": "session-assignment", "status": "missing", "patientId": str(session.patient_id)}

    national_id = db.execute(
        select(PatientIdentifier.identifier_value)
        .where(
            PatientIdentifier.tenant_id == session.tenant_id,
            PatientIdentifier.patient_id == patient.id,
            PatientIdentifier.identifier_type == "national_id",
        )
        .order_by(PatientIdentifier.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "source": "db",
        "status": "assigned",
        "patientId": str(patient.id),
        "displayName": patient.display_name,
        "legalFirstName": patient.legal_first_name,
        "legalLastName": patient.legal_last_name,
        "dateOfBirth": _format_date(patient.date_of_birth),
        "sex": patient.sex,
        "phone": patient.phone,
        "email": patient.email,
        "nationalId": national_id,
    }


def render_markdown_report(
    report_model: dict[str, Any] | None,
    *,
    patient_information: dict[str, Any],
    template_key: str | None = None,
) -> str:
    """Render markdown from the internal structured report model and assigned patient data."""
    template = get_report_template(template_key or _model_template_key(report_model))
    model = report_model if isinstance(report_model, dict) else empty_report_model(title=None, template_key=template.key)
    body = _render_body(model)
    rendered_sections: list[str] = []
    for section in template.section_order:
        if section == "clinic_header":
            rendered_sections.append(_render_clinic_header(template))
        elif section == "patient_information":
            rendered_sections.append(_render_patient_information(patient_information))
        elif section == "body":
            rendered_sections.append("# Body\n\n" + (body or "No structured report body has been generated yet."))
    return "\n\n".join(rendered_sections).strip()


def render_report_body_markdown(
    report_model: dict[str, Any] | None,
    *,
    db: DbSession | None = None,
    session: Session | None = None,
) -> str:
    """Render backend-owned report body markdown, including source media URLs."""
    model = report_model if isinstance(report_model, dict) else empty_report_model(title=None)
    media, media_captions = _render_source_media(model, db=db, session=session)
    body = _render_body(model, include_section_titles=False, excluded_paragraphs=media_captions)
    rendered = [section for section in (media, body) if section]
    return "\n\n".join(rendered).strip() or "No structured report body has been generated yet."


def _model_template_key(report_model: dict[str, Any] | None) -> str:
    if isinstance(report_model, dict) and isinstance(report_model.get("templateKey"), str):
        return report_model["templateKey"]
    return DEFAULT_REPORT_TEMPLATE_KEY


def _render_clinic_header(template: ReportTemplate) -> str:
    details = "\n".join(template.clinic_information)
    return f"# Clinic Information\n\nClinic: {template.clinic_name}\n{details}".strip()


def _render_patient_information(patient_information: dict[str, Any]) -> str:
    if patient_information.get("status") != "assigned":
        return "# Patient Information\n\nPatient: Unassigned"
    rows = [
        ("Full name", patient_information.get("displayName")),
        ("National ID", patient_information.get("nationalId")),
        ("Date of birth", patient_information.get("dateOfBirth")),
        ("Sex", patient_information.get("sex")),
        ("Phone", patient_information.get("phone")),
        ("Email", patient_information.get("email")),
    ]
    lines = [f"{label}: {value}" for label, value in rows if value]
    return "# Patient Information\n\n" + ("\n".join(lines) if lines else "Patient assigned")


def _render_body(
    report_model: dict[str, Any],
    *,
    include_section_titles: bool = True,
    excluded_paragraphs: set[str] | None = None,
) -> str:
    sections = report_model.get("sections")
    if not isinstance(sections, list):
        return ""
    rendered: list[str] = []
    excluded = {_normalize_report_text(value) for value in (excluded_paragraphs or set())}
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = section.get("title")
        if include_section_titles and isinstance(title, str) and title.strip():
            rendered.append(f"## {title.strip()}")
        blocks = section.get("blocks")
        if isinstance(blocks, list):
            body_start = _last_body_header_index(blocks)
            body_blocks = blocks[body_start + 1 :] if body_start >= 0 else blocks
            for block in body_blocks:
                rendered_block = _render_block(block)
                if (
                    rendered_block
                    and not _is_template_scaffold_text(rendered_block)
                    and _normalize_report_text(rendered_block) not in excluded
                ):
                    rendered.append(rendered_block)
    return "\n\n".join(rendered)


def _last_body_header_index(blocks: list[Any]) -> int:
    for index in range(len(blocks) - 1, -1, -1):
        text = _render_block(blocks[index])
        if _normalize_report_text(text) in {"body", "# body"}:
            return index
    return -1


def _is_template_scaffold_text(value: str) -> bool:
    normalized = _normalize_report_text(value)
    return (
        normalized
        in {
            "clinic information",
            "# clinic information",
            "patient information",
            "# patient information",
            "body",
            "# body",
            "clinical report",
            "## clinical report",
            "{{ patient_information }}",
        }
        or normalized.startswith("clinic: ")
        or normalized.startswith("full name: ")
    )


def _normalize_report_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _render_source_media(report_model: dict[str, Any], *, db: DbSession | None, session: Session | None) -> tuple[str, set[str]]:
    if db is None or session is None:
        return "", set()
    source_references = report_model.get("sourceReferences")
    if not isinstance(source_references, list):
        return "", set()
    capture_ids: list[uuid.UUID] = []
    for reference in source_references:
        if not isinstance(reference, dict) or reference.get("type") != "capture":
            continue
        capture_id = reference.get("captureId")
        if not isinstance(capture_id, str):
            continue
        try:
            capture_ids.append(uuid.UUID(capture_id))
        except ValueError:
            continue
    if not capture_ids:
        return "", set()
    body_media_capture_ids = _body_media_capture_ids(report_model)
    captures = db.execute(
        select(Capture).where(
            Capture.id.in_(capture_ids),
            Capture.tenant_id == session.tenant_id,
            Capture.session_id == session.id,
            Capture.capture_type == CaptureType.photo,
            Capture.source_artifact_id.is_not(None),
        )
    ).scalars()
    rendered: list[str] = []
    captions: set[str] = set()
    for capture in captures:
        if str(capture.id) in body_media_capture_ids:
            continue
        caption = _capture_caption(capture)
        label = caption or "Source image"
        rendered.append(f"![{_markdown_alt(label)}](/api/v1/captures/{capture.id}/file-content)")
        if caption:
            captions.add(caption)
            rendered.append(f"*{caption}*")
    return "\n\n".join(rendered), captions


def _render_block(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None
    block_type = block.get("type")
    if block_type == "paragraph" and isinstance(block.get("text"), str):
        return block["text"].strip()
    if block_type in {"image", "artifact"}:
        capture_id = block.get("captureId")
        if isinstance(capture_id, str) and _is_uuid_like(capture_id):
            caption = block.get("caption")
            label = caption if isinstance(caption, str) and caption.strip() else "Source artifact"
            return f"![{_markdown_alt(label)}](/api/v1/captures/{capture_id}/file-content)"
        artifact_id = block.get("artifactId")
        caption = block.get("caption")
        if isinstance(artifact_id, str) and artifact_id.strip():
            label = caption if isinstance(caption, str) and caption.strip() else "Source artifact"
            return f"![{_markdown_alt(label)}](artifact:{artifact_id})"
    return None


def _body_media_capture_ids(report_model: dict[str, Any]) -> set[str]:
    sections = report_model.get("sections")
    if not isinstance(sections, list):
        return set()
    capture_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") not in {"image", "artifact"}:
                continue
            capture_id = block.get("captureId")
            if isinstance(capture_id, str) and _is_uuid_like(capture_id):
                capture_ids.add(capture_id)
    return capture_ids


def _capture_caption(capture: Capture) -> str:
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    caption = metadata.get("caption")
    if isinstance(caption, dict) and isinstance(caption.get("text"), str):
        return caption["text"].strip()
    ocr = metadata.get("ocr")
    if isinstance(ocr, dict) and isinstance(ocr.get("text"), str):
        return ocr["text"].strip()
    return ""


def _markdown_alt(value: str) -> str:
    return value.replace("[", "(").replace("]", ")").replace("\n", " ").strip()


def _format_date(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def _is_uuid_like(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
