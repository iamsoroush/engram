import type { CaptureDraft } from "../../domain/appTypes";

export function audioExtensionForMimeType(mimeType: string) {
  if (mimeType.includes("mp4") || mimeType.includes("mpeg") || mimeType.includes("aac")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("wav")) return "wav";
  return "webm";
}

export function isSafariBrowser() {
  return /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
}

export function preferredAudioRecorderOptions() {
  const mimeTypes = isSafariBrowser()
    ? ["audio/mp4", "audio/mp4;codecs=mp4a.40.2", "audio/aac"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  const mimeType = mimeTypes.find((type) => MediaRecorder.isTypeSupported(type));
  return mimeType ? { mimeType } : undefined;
}

/**
 * Prepares an audio capture draft for upload.
 *
 * Audio is uploaded AS RECORDED — the browser's native container (Chrome `webm/opus`, Safari
 * `mp4/AAC`), already ~8× smaller than the old WAV-PCM re-encode. The backend transcodes once on
 * ingest to the canonical stored format and measures duration server-side, so the client no longer
 * runs the OfflineAudioContext WAV re-encode (heavy on old phones) or computes duration. This stays as
 * the outbox `standardizeDraft` seam; it only records the original content-type as provenance now.
 * Any optimistic `duration` the recorder already stamped (elapsed seconds) is preserved for the
 * pre-sync UI; the server's measured duration replaces it once the upload completes.
 */
export async function standardizeCaptureDraft(draft: CaptureDraft): Promise<CaptureDraft> {
  if (draft.kind !== "audio") return draft;
  return {
    ...draft,
    metadata: {
      ...draft.metadata,
      original_audio_content_type: draft.file.type || "application/octet-stream",
    },
  };
}
