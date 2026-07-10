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
BACKEND_DATABASE_URL=postgresql+psycopg://engram:engram@postgres:5432/engram
BACKEND_OBJECT_STORAGE_ENDPOINT=http://minio:9000
BACKEND_OBJECT_STORAGE_BUCKET=engram-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=engram-dev
BACKEND_OBJECT_STORAGE_SECRET_KEY=engram-dev-secret
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
BACKEND_OBJECT_STORAGE_BUCKET=engram-captures
BACKEND_OBJECT_STORAGE_ACCESS_KEY=...
BACKEND_OBJECT_STORAGE_SECRET_KEY=...
BACKEND_OBJECT_STORAGE_SECURE=true
BACKEND_OBJECT_STORAGE_PRESIGNED_URL_TTL_SECONDS=300
BACKEND_OBJECT_STORAGE_PUBLIC_ENDPOINT=https://minio.example.com
```

`BACKEND_OBJECT_STORAGE_PUBLIC_ENDPOINT` (optional, default unset) rewrites the scheme/host of
presigned GET URLs to a browser-reachable address when the backend signs against an internal
MinIO endpoint (e.g. `http://minio:9000` inside the Docker network). Unset, presigned URLs use
the internal endpoint as-is.

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
- owning capture/session/AI job
- generated marker, when applicable
- timestamps

The database is the authority for ownership, authorization, and artifact meaning. MinIO is the binary store.

## Capture Audio Format

Capture audio is **transcoded on ingest** to exactly ONE canonical stored format — **MP3 32 kbps,
16 kHz mono** — regardless of what the browser recorded (Chrome `webm/opus`, Safari `mp4/AAC`) or
what older clients send (WAV). `upload_source_capture` normalizes once with ffmpeg
(`app/services/audio.py`), stores only the canonical bytes with content-type `audio/mpeg`, measures
duration server-side (ffprobe) into `capture_metadata.duration`, and rejects non-audio. The backend
image installs ffmpeg. This is ~8× smaller than the former WAV-PCM-16k store (~1.92 MB/min →
~0.24 MB/min) at zero transcription-accuracy cost.

- **Canonical = MP3** (not Opus): it plays natively in `<audio>` with exact duration + seek on Chrome
  and Safari, incl. iOS, through the byte-range path, and is universally decodable. Flipping the
  canonical to Opus (marginally smaller) is a one-place change in `audio.py`, gated on an iOS-Safari
  playback re-test.
- **Mixed store, no migration:** existing WAV artifacts stay readable/playable — readers serve the
  stored `artifact.mime_type` (byte-range aware), so old WAV and new MP3 both work. Only new captures
  are canonical.
- The transcription worker sends the stored canonical MP3 straight to the gateway (no per-call FLAC
  re-encode); see [ai_engine/processing](../ai_engine/processing.md).

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
