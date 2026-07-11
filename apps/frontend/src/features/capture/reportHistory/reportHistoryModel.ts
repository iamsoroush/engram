// Report version-history (E14 / AES-14xx) — pure helpers shared by the button + sheet.
import type { CaptureItem, CaptureSession, ReportVersionDetail, ReportVersionSummary, ReportVersionTrigger } from "../../../domain/types";
import { normalizeApiSession } from "../../../services/api/normalizers";

type Translate = (key: string, vars?: Record<string, string | number>) => string;

const KNOWN_TRIGGER_KINDS = new Set([
  "first_report",
  "photo_added",
  "audio_added",
  "note_added",
  "capture_added",
  "captures_added",
  "capture_removed",
  "captures_removed",
  "transcript_edited",
  "caption_edited",
  "note_edited",
  "capture_edited",
  "captures_edited",
  "marked_out_of_context",
  "marked_relevant",
  "report_updated",
]);

/** Localized label for a version's trigger (chrome — the server sends the kind, the client localizes). */
export function reportVersionTriggerLabel(trigger: ReportVersionTrigger, t: Translate): string {
  const kind = KNOWN_TRIGGER_KINDS.has(trigger.kind) ? trigger.kind : "report_updated";
  return t(`capture.history.trigger.${kind}`, trigger.count != null ? { count: trigger.count } : undefined);
}

/** The synced captures a restore-to-version would remove (current captures the version never knew).
 * Unsynced local captures aren't on the backend, so a restore leaves them — they're excluded here too. */
export function reportVersionRemovedCaptures(live: CaptureSession, version: ReportVersionSummary): CaptureItem[] {
  const known = new Set(version.captureIds || []);
  return (live.items || []).filter((item) => !known.has(item.id) && !item.id.startsWith("local-capture-"));
}

/** A read-only preview session: the version's report artifacts with the LIVE user-state overlay kept on
 * top, so a rejected safety flag / dismissed aftercare / confirmed dose / treatment edit is never
 * time-traveled away (pipeline-versioning D2). Runs through the shared normalizer so reportModel/report
 * are the same shapes the live report renders from. */
export function buildReportVersionPreviewSession(live: CaptureSession, detail: ReportVersionDetail): CaptureSession {
  const liveMeta = live.extractedMetadata && typeof live.extractedMetadata === "object" ? live.extractedMetadata : {};
  const versionMeta = detail.report.extractedMetadata && typeof detail.report.extractedMetadata === "object" ? detail.report.extractedMetadata : {};
  // Version artifact keys win for report CONTENT; the overlay keys (only on the live side) survive because
  // the two key sets are disjoint (see _ARTIFACT_METADATA_KEYS vs OVERLAY_METADATA_KEYS on the backend).
  const mergedMetadata = { ...liveMeta, ...versionMeta };
  return normalizeApiSession({
    id: live.id,
    title: live.label,
    patientId: live.patientId,
    patientName: live.patientName,
    createdAt: live.createdAt ?? undefined,
    updatedAt: detail.version.generatedAt ?? live.updatedAt ?? undefined,
    reportModel: detail.report.reportModel,
    generatedReport: detail.report.generatedReport,
    summary: detail.report.summary ?? undefined,
    generatedSummary: detail.report.generatedSummary,
    reportTemplateKey: detail.report.reportTemplateKey,
    extractedMetadata: mergedMetadata,
  });
}
