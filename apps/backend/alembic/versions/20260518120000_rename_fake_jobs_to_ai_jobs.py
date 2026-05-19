"""rename legacy fake job schema to AI job schema

Revision ID: 20260518120000
Revises: 20260517120000
Create Date: 2026-05-18 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260518120000"
down_revision: str | None = "20260517120000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Repair databases that applied the older fake-processing migration names."""
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regtype('public.ai_job_status') IS NULL AND to_regtype('public.fake_job_status') IS NOT NULL THEN
                ALTER TYPE fake_job_status RENAME TO ai_job_status;
            END IF;

            IF to_regtype('public.ai_job_type') IS NULL AND to_regtype('public.fake_job_type') IS NOT NULL THEN
                ALTER TYPE fake_job_type RENAME TO ai_job_type;
            END IF;

            IF to_regclass('public.ai_jobs') IS NULL AND to_regclass('public.fake_jobs') IS NOT NULL THEN
                ALTER TABLE fake_jobs RENAME TO ai_jobs;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TYPE ai_job_status ADD VALUE IF NOT EXISTS 'succeeded'")
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'audio_capture_process'")
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'text_capture_process'")
    op.execute("ALTER TYPE ai_job_type ADD VALUE IF NOT EXISTS 'image_capture_process'")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pk_fake_jobs') THEN
                ALTER TABLE ai_jobs RENAME CONSTRAINT pk_fake_jobs TO pk_ai_jobs;
            END IF;

            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fake_jobs_capture_id_captures') THEN
                ALTER TABLE ai_jobs RENAME CONSTRAINT fk_fake_jobs_capture_id_captures TO fk_ai_jobs_capture_id_captures;
            END IF;

            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fake_jobs_created_by_user_id_users') THEN
                ALTER TABLE ai_jobs RENAME CONSTRAINT fk_fake_jobs_created_by_user_id_users TO fk_ai_jobs_created_by_user_id_users;
            END IF;

            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fake_jobs_session_id_sessions') THEN
                ALTER TABLE ai_jobs RENAME CONSTRAINT fk_fake_jobs_session_id_sessions TO fk_ai_jobs_session_id_sessions;
            END IF;

            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fake_jobs_tenant_id_tenants') THEN
                ALTER TABLE ai_jobs RENAME CONSTRAINT fk_fake_jobs_tenant_id_tenants TO fk_ai_jobs_tenant_id_tenants;
            END IF;

            IF to_regclass('public.ix_fake_jobs_tenant_id_session_id') IS NOT NULL THEN
                ALTER INDEX ix_fake_jobs_tenant_id_session_id RENAME TO ix_ai_jobs_tenant_id_session_id;
            END IF;

            IF to_regclass('public.ix_fake_jobs_tenant_id_status_created_at') IS NOT NULL THEN
                ALTER INDEX ix_fake_jobs_tenant_id_status_created_at RENAME TO ix_ai_jobs_tenant_id_status_created_at;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_artifacts_fake_job_id_fake_jobs') THEN
                ALTER TABLE artifacts DROP CONSTRAINT fk_artifacts_fake_job_id_fake_jobs;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'artifacts' AND column_name = 'fake_job_id'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'artifacts' AND column_name = 'ai_job_id'
            ) THEN
                ALTER TABLE artifacts RENAME COLUMN fake_job_id TO ai_job_id;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_artifacts_ai_job_id_ai_jobs') THEN
                ALTER TABLE artifacts
                    ADD CONSTRAINT fk_artifacts_ai_job_id_ai_jobs
                    FOREIGN KEY (ai_job_id) REFERENCES ai_jobs(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Restore the legacy fake-processing names for rollback."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_artifacts_ai_job_id_ai_jobs') THEN
                ALTER TABLE artifacts DROP CONSTRAINT fk_artifacts_ai_job_id_ai_jobs;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'artifacts' AND column_name = 'ai_job_id'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'artifacts' AND column_name = 'fake_job_id'
            ) THEN
                ALTER TABLE artifacts RENAME COLUMN ai_job_id TO fake_job_id;
            END IF;

            IF to_regclass('public.fake_jobs') IS NULL AND to_regclass('public.ai_jobs') IS NOT NULL THEN
                ALTER TABLE ai_jobs RENAME TO fake_jobs;
            END IF;

            IF to_regtype('public.fake_job_type') IS NULL AND to_regtype('public.ai_job_type') IS NOT NULL THEN
                ALTER TYPE ai_job_type RENAME TO fake_job_type;
            END IF;

            IF to_regtype('public.fake_job_status') IS NULL AND to_regtype('public.ai_job_status') IS NOT NULL THEN
                ALTER TYPE ai_job_status RENAME TO fake_job_status;
            END IF;
        END $$;
        """
    )
