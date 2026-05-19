import type { CaptureDraft } from "./appTypes";

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

function writeAscii(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

export function encodeWavPcm16Mono(audioBuffer: AudioBuffer, sampleRate = 16000) {
  const samples = audioBuffer.getChannelData(0);
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * Converts browser-recorded audio into the backend-friendly format expected by
 * the AI pipeline: mono 16 kHz PCM WAV.
 */
export async function standardizeAudioBlob(blob: Blob) {
  const AudioContextClass =
    window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass || !window.OfflineAudioContext) throw new Error("Audio conversion is not available");
  const context = new AudioContextClass();
  try {
    const sourceBuffer = await context.decodeAudioData(await blob.arrayBuffer());
    const sampleRate = 16000;
    const length = Math.max(1, Math.ceil(sourceBuffer.duration * sampleRate));
    const offline = new OfflineAudioContext(1, length, sampleRate);
    const source = offline.createBufferSource();
    source.buffer = sourceBuffer;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return { blob: encodeWavPcm16Mono(rendered, sampleRate), duration: rendered.duration };
  } finally {
    void context.close();
  }
}

/**
 * Preserves original audio details in metadata while replacing the uploaded
 * file with a normalized WAV payload for consistent processing.
 */
export async function standardizeCaptureDraft(draft: CaptureDraft): Promise<CaptureDraft> {
  if (draft.kind !== "audio") return draft;
  const standardized = await standardizeAudioBlob(draft.file);
  return {
    ...draft,
    file: standardized.blob,
    filename: `audio-${Date.now()}.wav`,
    metadata: {
      ...draft.metadata,
      original_audio_filename: draft.filename,
      original_audio_content_type: draft.file.type || "application/octet-stream",
      content_type: "audio/wav",
      codec: "pcm_s16le",
      sample_rate: 16000,
      channels: 1,
      duration: Number(standardized.duration.toFixed(2)),
    },
  };
}
