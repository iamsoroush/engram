import type { CaptureItem } from "./types";
import { Badge, Card } from "./ui";

export function assignmentSourceLabel(source?: string | null) {
  if (source === "staff") return "Assigned by staff";
  if (source === "ai_engine" || source === "ai-engine") return "Suggested by AI processing";
  return source ? `Assigned by ${source}` : "";
}

export function metadataRecord(value: unknown) {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function metadataText(value: unknown) {
  return typeof value === "string" && value.trim() ? value : "";
}

export function metadataDisplay(value: unknown) {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

export function generatedMetadataFor(item: CaptureItem) {
  const metadata = metadataRecord(item.metadata);
  if (item.type === "audio" || item.type === "voice") return metadataRecord(metadata.transcript);
  if (item.type === "photo") return metadataRecord(metadata.caption || metadata.ocr);
  return metadataRecord(metadata.decorated_text || metadata.normalized_note);
}

export function isGeneratedMetadata(metadata: Record<string, unknown>) {
  return Boolean(metadata.generated_by || metadata.generatedBy || metadata.ai_job_id || metadata.aiJobId || metadata.artifact_id);
}

export function captureGeneratedLabel(item: CaptureItem) {
  if (item.type === "audio" || item.type === "voice") return "Transcription";
  if (item.type === "photo") return "Caption";
  return "Decorated text";
}

export function captureGeneratedFallback(item: CaptureItem) {
  if (item.status === "saved" || item.status === "syncing" || item.status === "failed") {
    return "Waiting for safe transfer before processing starts.";
  }
  if (item.status === "processing") return "Processing. Placeholder output is expected after about 5 seconds.";
  if (item.type === "audio" || item.type === "voice") return "Transcript placeholder will appear here.";
  if (item.type === "photo") return "Caption placeholder will appear here.";
  return "Decorated text placeholder will appear here.";
}

export function CaptureGeneratedDetails({ item }: { item: CaptureItem }) {
  const generated = generatedMetadataFor(item);
  const text = metadataText(generated.text);
  const isReady = metadataDisplay(generated.status) === "completed" || Boolean(text);
  return (
    <details className={`capture-generated ${isReady ? "" : "processing"}`}>
      <summary>
        <span>{captureGeneratedLabel(item)}</span>
        {isReady ? null : <span className="capture-processing-indicator" aria-label="Processing" />}
      </summary>
      <p>{text || captureGeneratedFallback(item)}</p>
    </details>
  );
}

export function CaptureMetadataSummary({ item }: { item: CaptureItem }) {
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedLabel = isGeneratedMetadata(generated) ? "AI-generated - not verified" : "";
  const rows: Array<{ label: string; value: string }> = [];

  if (item.type === "audio" || item.type === "voice") {
    rows.push(
      { label: "Transcript status", value: metadataDisplay(generated.status || metadata.transcript_status) },
      { label: "Language", value: metadataDisplay(generated.language || metadata.language) },
      { label: "Duration", value: metadataDisplay(generated.duration || metadata.duration) },
    );
  } else if (item.type === "photo") {
    const width = metadataDisplay(generated.width || metadata.width);
    const height = metadataDisplay(generated.height || metadata.height);
    rows.push(
      { label: "Caption status", value: metadataDisplay(generated.status || metadata.caption_status || metadata.ocr_status) },
      { label: "Dimensions", value: width && height ? `${width} x ${height}` : "" },
      { label: "Thumbnail", value: metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl) },
    );
  } else {
    rows.push(
      { label: "Extraction status", value: metadataDisplay(generated.status || metadata.extraction_status) },
    );
  }

  const visibleRows = rows.filter((row) => row.value);
  if (!visibleRows.length && !generatedLabel) return null;

  return (
    <div className="capture-metadata">
      {generatedLabel ? <Badge tone="amber">{generatedLabel}</Badge> : null}
      {visibleRows.map((row) => (
        <div key={row.label}>
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}
