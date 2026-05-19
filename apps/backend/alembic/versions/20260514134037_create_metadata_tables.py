"""create metadata tables

Revision ID: 20260514134037
Revises:
Create Date: 2026-05-14 13:40:37.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514134037"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


tenant_status = postgresql.ENUM("active", "suspended", "archived", name="tenant_status")
user_status = postgresql.ENUM("active", "disabled", "invited", name="user_status")
membership_role = postgresql.ENUM("doctor", "assistant", "admin", "patient", name="membership_role")
membership_status = postgresql.ENUM("active", "disabled", "invited", name="membership_status")
patient_status = postgresql.ENUM("active", "archived", name="patient_status")
patient_user_link_status = postgresql.ENUM("active", "revoked", name="patient_user_link_status")
session_status = postgresql.ENUM(
    "unassigned",
    "needs_review",
    "processing",
    "organized",
    "reviewing",
    "verified",
    "reopened",
    "failed",
    name="session_status",
)
organization_source = postgresql.ENUM("none", "staff", "ai-engine", name="organization_source")
capture_type = postgresql.ENUM("audio", "photo", "note", name="capture_type")
capture_status = postgresql.ENUM(
    "received", "processing", "processed", "needs_attention", "deleted", name="capture_status"
)
artifact_kind = postgresql.ENUM(
    "source", "transcript", "ocr_text", "thumbnail", "summary", "normalized_note", "other", name="artifact_kind"
)
ai_job_type = postgresql.ENUM("capture_process", "session_organize", name="ai_job_type")
ai_job_status = postgresql.ENUM("queued", "running", "completed", "failed", name="ai_job_status")


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", tenant_status, server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=240), nullable=True),
        sa.Column("auth_subject", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("status", user_status, server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("auth_subject", name=op.f("uq_users_auth_subject")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        sa.Column("status", membership_status, server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_memberships_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tenant_memberships_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_memberships")),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_id_user_id"),
    )
    op.create_index("ix_tenant_memberships_tenant_id_role", "tenant_memberships", ["tenant_id", "role"])

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("legal_first_name", sa.String(length=120), nullable=True),
        sa.Column("legal_last_name", sa.String(length=120), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("sex", sa.String(length=40), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", patient_status, server_default="active", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_patients_created_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_patients_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patients")),
    )
    op.create_index("ix_patients_tenant_id_date_of_birth", "patients", ["tenant_id", "date_of_birth"])
    op.create_index("ix_patients_tenant_id_display_name", "patients", ["tenant_id", "display_name"])

    op.create_table(
        "patient_user_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", patient_user_link_status, server_default="active", nullable=False),
        sa.Column("linked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["users.id"], name=op.f("fk_patient_user_links_linked_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name=op.f("fk_patient_user_links_patient_id_patients"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_patient_user_links_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_patient_user_links_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_user_links")),
        sa.UniqueConstraint("tenant_id", "patient_id", name="uq_patient_user_links_tenant_id_patient_id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_patient_user_links_tenant_id_user_id"),
    )

    op.create_table(
        "patient_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identifier_type", sa.String(length=80), nullable=False),
        sa.Column("identifier_value", sa.String(length=500), nullable=False),
        sa.Column("normalized_value", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name=op.f("fk_patient_identifiers_patient_id_patients"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_patient_identifiers_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_identifiers")),
    )
    op.create_index("ix_patient_identifiers_patient_id", "patient_identifiers", ["patient_id"])
    op.create_index("ix_patient_identifiers_tenant_id_type_normalized", "patient_identifiers", ["tenant_id", "identifier_type", "normalized_value"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", session_status, server_default="unassigned", nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("generated_summary", sa.Text(), nullable=True),
        sa.Column("organization_source", organization_source, server_default="none", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_sessions_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name=op.f("fk_sessions_patient_id_patients"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_started_by_user_id"], ["users.id"], name=op.f("fk_sessions_review_started_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_sessions_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], name=op.f("fk_sessions_verified_by_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("ix_sessions_tenant_id_patient_id", "sessions", ["tenant_id", "patient_id"])
    op.create_index("ix_sessions_tenant_id_status_updated_at", "sessions", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "captures",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capture_type", capture_type, nullable=False),
        sa.Column("status", capture_status, server_default="received", nullable=False),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_capture_id", sa.String(length=120), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_captures_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], name=op.f("fk_captures_patient_id_patients"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_captures_session_id_sessions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_captures_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_captures")),
        sa.UniqueConstraint("tenant_id", "created_by_user_id", "client_capture_id", name="uq_captures_tenant_id_created_by_user_id_client_capture_id"),
    )
    op.create_index("ix_captures_tenant_id_patient_id", "captures", ["tenant_id", "patient_id"])
    op.create_index("ix_captures_tenant_id_session_id", "captures", ["tenant_id", "session_id"])

    op.create_table(
        "ai_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_type", ai_job_type, nullable=False),
        sa.Column("status", ai_job_status, server_default="queued", nullable=False),
        sa.Column("generated_by", sa.String(length=80), nullable=False),
        sa.Column("input_artifact_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"], name=op.f("fk_ai_jobs_capture_id_captures"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_ai_jobs_created_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_ai_jobs_session_id_sessions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_ai_jobs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_jobs")),
    )
    op.create_index("ix_ai_jobs_tenant_id_session_id", "ai_jobs", ["tenant_id", "session_id"])
    op.create_index("ix_ai_jobs_tenant_id_status_created_at", "ai_jobs", ["tenant_id", "status", "created_at"])

    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_kind", artifact_kind, nullable=False),
        sa.Column("bucket", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("generated_by", sa.String(length=80), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"], name=op.f("fk_artifacts_capture_id_captures"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_artifacts_created_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_job_id"], ["ai_jobs.id"], name=op.f("fk_artifacts_ai_job_id_ai_jobs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_artifacts_session_id_sessions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_artifacts_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
        sa.UniqueConstraint("bucket", "object_key", name="uq_artifacts_bucket_object_key"),
    )
    op.create_index("ix_artifacts_tenant_id_capture_id", "artifacts", ["tenant_id", "capture_id"])
    op.create_index("ix_artifacts_tenant_id_session_id", "artifacts", ["tenant_id", "session_id"])
    op.create_foreign_key(
        op.f("fk_captures_source_artifact_id_artifacts"),
        "captures",
        "artifacts",
        ["source_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_audit_events_actor_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_tenant_id_created_at", "audit_events", ["tenant_id", "created_at"])
    op.create_index("ix_audit_events_tenant_id_target", "audit_events", ["tenant_id", "target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_id_target", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_constraint(op.f("fk_captures_source_artifact_id_artifacts"), "captures", type_="foreignkey")
    op.drop_index("ix_artifacts_tenant_id_session_id", table_name="artifacts")
    op.drop_index("ix_artifacts_tenant_id_capture_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_ai_jobs_tenant_id_status_created_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_tenant_id_session_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_index("ix_captures_tenant_id_session_id", table_name="captures")
    op.drop_index("ix_captures_tenant_id_patient_id", table_name="captures")
    op.drop_table("captures")
    op.drop_index("ix_sessions_tenant_id_status_updated_at", table_name="sessions")
    op.drop_index("ix_sessions_tenant_id_patient_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_patient_identifiers_tenant_id_type_normalized", table_name="patient_identifiers")
    op.drop_index("ix_patient_identifiers_patient_id", table_name="patient_identifiers")
    op.drop_table("patient_identifiers")
    op.drop_table("patient_user_links")
    op.drop_index("ix_patients_tenant_id_display_name", table_name="patients")
    op.drop_index("ix_patients_tenant_id_date_of_birth", table_name="patients")
    op.drop_table("patients")
    op.drop_index("ix_tenant_memberships_tenant_id_role", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("users")
    op.drop_table("tenants")

    ai_job_status.drop(op.get_bind(), checkfirst=True)
    ai_job_type.drop(op.get_bind(), checkfirst=True)
    artifact_kind.drop(op.get_bind(), checkfirst=True)
    capture_status.drop(op.get_bind(), checkfirst=True)
    capture_type.drop(op.get_bind(), checkfirst=True)
    organization_source.drop(op.get_bind(), checkfirst=True)
    session_status.drop(op.get_bind(), checkfirst=True)
    patient_user_link_status.drop(op.get_bind(), checkfirst=True)
    patient_status.drop(op.get_bind(), checkfirst=True)
    membership_status.drop(op.get_bind(), checkfirst=True)
    membership_role.drop(op.get_bind(), checkfirst=True)
    user_status.drop(op.get_bind(), checkfirst=True)
    tenant_status.drop(op.get_bind(), checkfirst=True)
