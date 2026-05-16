# Backend Storage

## Summary

Backend v2 uses Postgres for metadata and MinIO for source files and generated artifacts in both development and production. MinIO is used as S3-compatible object storage; do not keep production capture files on the backend filesystem.

## Local Development

Local Compose should include:

- `postgres`
- `minio`
- `backend`
- `frontend`

Development environment variables:

```sh
BACKEND_DATABASE_URL=postgresql+psycopg://aesmem:aesmem@postgres:5432/aesmem
BACKEND_OBJECT_STORAGE_ENDPOINT=http://minio:9000
BACKEND_OBJECT_STORAGE_BUCKET=aesmem-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=aesmem-dev
BACKEND_OBJECT_STORAGE_SECRET_KEY=aesmem-dev-secret
BACKEND_OBJECT_STORAGE_SECURE=false
```

The MinIO console may be exposed locally for debugging, but production should not expose it publicly.

## Production MinIO

Production should use MinIO with hardened configuration:

- Private network only for MinIO API and console.
- Public bucket access disabled.
- Separate credentials for backend app and operational admin.
- Backend credentials limited to required buckets and prefixes.
- Server-side encryption enabled.
- Bucket versioning enabled where practical.
- Lifecycle and retention policies documented before real clinical use.
- Backups cover both Postgres and MinIO object data.
- File access goes through backend authorization or short-lived presigned URLs.

Recommended production variables:

```sh
BACKEND_DATABASE_URL=postgresql+psycopg://...
BACKEND_OBJECT_STORAGE_ENDPOINT=https://minio.internal:9000
BACKEND_OBJECT_STORAGE_BUCKET=aesmem-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=...
BACKEND_OBJECT_STORAGE_SECRET_KEY=...
BACKEND_OBJECT_STORAGE_SECURE=true
BACKEND_OBJECT_STORAGE_PRESIGNED_URL_TTL_SECONDS=300
```

## Object Keys

Object keys must not expose patient names or source filenames.

Recommended pattern:

```text
tenants/{tenant_id}/sessions/{session_id}/captures/{capture_id}/source/{artifact_id}
tenants/{tenant_id}/sessions/{session_id}/captures/{capture_id}/generated/{artifact_id}
tenants/{tenant_id}/sessions/{session_id}/generated/{artifact_id}
```

Store the original source filename only as metadata if needed for display.

## Artifact Metadata

Postgres artifact rows store:

- bucket
- object key
- MIME type
- byte size
- SHA-256 checksum
- artifact kind
- tenant ID
- owning capture/session/fake job
- generated marker, when applicable
- timestamps

The database is the authority for ownership, authorization, and artifact meaning. MinIO is the binary store.

## Upload Safety

The backend must not report upload success until:

1. The object exists in MinIO.
2. The artifact row is committed.
3. The capture row is committed.

If MinIO succeeds and Postgres fails, the backend should delete the object or record it for orphan cleanup. If Postgres succeeds and MinIO fails, the transaction must roll back.

## Download And Preview

Preferred v2 behavior:

- User requests `GET /captures/{capture_id}/file`.
- Backend checks auth, tenant, capture ownership, and artifact visibility.
- Backend returns a short-lived presigned URL or streams the file.

Never expose permanent object URLs or public buckets.

## Backup And Restore

Production backup must include:

- Postgres database backups.
- MinIO bucket/object backups.
- Configuration secrets managed outside git.
- Restore drills that prove DB artifact rows still match object keys.

A restore is incomplete if metadata exists without objects or objects exist without metadata.
