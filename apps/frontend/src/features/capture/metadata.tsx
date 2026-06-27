import type { CaptureItem } from "../../domain/types";
import { useT, type Translator } from "../../shared/i18n";
import { Badge } from "../../shared/ui/primitives";

export function assignmentSourceLabel(source: string | null | undefined, t: Translator) {
  if (source === "staff") return t("model.assignment.staff");
  if (source === "ai_engine" || source === "ai-engine") return t("model.assignment.aiSuggested");
  if (source === "ai_matched") return t("model.assignment.aiMatched");
  if (source === "ai_created") return t("model.assignment.aiCreated");
  // An unknown source value (content, not a known enum) is shown verbatim in the "Assigned by …" frame.
  return source ? t("model.assignment.bySource", { source }) : "";
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
  // Notes are a pure passthrough (decoration removed): the doctor's raw words, never "AI-generated".
  return metadataRecord(metadata.note);
}

export function isGeneratedMetadata(metadata: Record<string, unknown>) {
  return Boolean(metadata.generated_by || metadata.generatedBy || metadata.ai_job_id || metadata.aiJobId || metadata.artifact_id);
}

export function CaptureMetadataSummary({ item }: { item: CaptureItem }) {
  const t = useT();
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedLabel = isGeneratedMetadata(generated) ? t("model.meta.aiGeneratedUnverified") : "";
  const rows: Array<{ label: string; value: string }> = [];

  if (item.type === "audio" || item.type === "voice") {
    rows.push(
      { label: t("model.meta.transcriptStatus"), value: metadataDisplay(generated.status || metadata.transcript_status) },
      { label: t("model.meta.language"), value: metadataDisplay(generated.language || metadata.language) },
      { label: t("model.meta.duration"), value: metadataDisplay(generated.duration || metadata.duration) },
    );
  } else if (item.type === "photo") {
    const width = metadataDisplay(generated.width || metadata.width);
    const height = metadataDisplay(generated.height || metadata.height);
    rows.push(
      { label: t("model.meta.captionStatus"), value: metadataDisplay(generated.status || metadata.caption_status || metadata.ocr_status) },
      { label: t("model.meta.dimensions"), value: width && height ? `${width} x ${height}` : "" },
      { label: t("model.meta.thumbnail"), value: metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl) },
    );
  } else {
    rows.push(
      { label: t("model.meta.extractionStatus"), value: metadataDisplay(generated.status || metadata.extraction_status) },
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
