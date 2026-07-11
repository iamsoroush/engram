// Report version-history sheet (E14 / AES-14xx): timeline → read-only preview → owner-only revert.
// Fully self-contained — the only CaptureScreen touch-point is the header button that opens it.
import React from "react";
import "./reportHistory.css";
import type { CaptureSession, ReportVersionDetail, ReportVersionSummary } from "../../../domain/types";
import { Badge, Button, Sheet } from "../../../shared/ui/primitives";
import { LiveReportView } from "../components/LiveReport";
import { ClockHistoryIcon } from "../components/CaptureIcons";
import { useT } from "../../../shared/i18n";
import { useApi } from "../../../app/providers/ApiProvider";
import { useAuth } from "../../../app/providers/AuthProvider";
import { useToast } from "../../../app/providers/ToastProvider";
import { useMemoryApi } from "../../memory/useMemoryApi";
import { useSessionActions } from "../../../app/providers/SessionStoreProvider";
import { fetchReportVersion, fetchReportVersions } from "../../../services/api/client";
import { formatTime } from "../../../shared/lib/datetime";
import { buildReportVersionPreviewSession, reportVersionRemovedCaptures, reportVersionTriggerLabel } from "./reportHistoryModel";

export function ReportHistorySheet({
  session,
  canRestore,
  onClose,
}: {
  session: CaptureSession;
  canRestore: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const apiFetch = useApi();
  const tenant = useAuth().auth?.tenant;
  const { resolveSourceFile } = useMemoryApi();
  const { setToast } = useToast();
  const { restoreReportVersion } = useSessionActions();

  const [versions, setVersions] = React.useState<ReportVersionSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState(false);
  const [selected, setSelected] = React.useState<ReportVersionSummary | null>(null);
  const [detail, setDetail] = React.useState<ReportVersionDetail | null>(null);
  const [detailError, setDetailError] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [restoring, setRestoring] = React.useState(false);

  const loadVersions = React.useCallback(async () => {
    setLoadError(false);
    setVersions(null);
    try {
      setVersions(await fetchReportVersions(apiFetch, session.id));
    } catch {
      setLoadError(true);
    }
  }, [apiFetch, session.id]);

  React.useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  const openVersion = React.useCallback(
    async (version: ReportVersionSummary) => {
      setSelected(version);
      setDetail(null);
      setDetailError(false);
      setConfirming(false);
      try {
        setDetail(await fetchReportVersion(apiFetch, session.id, version.id));
      } catch {
        setDetailError(true);
      }
    },
    [apiFetch, session.id],
  );

  const backToList = React.useCallback(() => {
    setSelected(null);
    setDetail(null);
    setDetailError(false);
    setConfirming(false);
  }, []);

  const doRestore = React.useCallback(async () => {
    if (!selected) return;
    setRestoring(true);
    try {
      await restoreReportVersion(session.id, selected.id);
      onClose();
    } catch (err) {
      const status = (err as { status?: number }).status;
      setToast(status === 409 ? t("capture.history.restoreGone") : t("capture.history.restoreError"));
      setConfirming(false);
      void loadVersions(); // the timeline changed under us — reload it
    } finally {
      setRestoring(false);
    }
  }, [selected, restoreReportVersion, session.id, onClose, setToast, t, loadVersions]);

  const previewSession = React.useMemo(
    () => (detail ? buildReportVersionPreviewSession(session, detail) : null),
    [session, detail],
  );

  const spinner = (
    <div className="report-history-loading" role="status" aria-label={t("capture.history.title")}>
      <span className="report-history-spinner" aria-hidden="true" />
    </div>
  );

  // Nodes are pre-computed (not chained inline in JSX) so the render tree stays flat and readable.
  const renderTimeline = () => {
    if (loadError) {
      return (
        <div className="report-history-error">
          <p>{t("capture.history.loadError")}</p>
          <Button size="sm" variant="ghost" onClick={() => void loadVersions()}>
            {t("capture.history.retry")}
          </Button>
        </div>
      );
    }
    if (versions === null) return spinner;
    if (versions.length <= 1) return <p className="report-history-empty">{t("capture.history.empty")}</p>;
    return (
      <ul className="report-history-rows">
        {versions.map((version) => (
          <li key={version.id}>
            <button className="report-history-row" type="button" onClick={() => void openVersion(version)}>
              <span className="report-history-row-main">
                <span className="report-history-row-trigger">{reportVersionTriggerLabel(version.trigger, t)}</span>
                <span className="report-history-row-meta">
                  <span data-content="time">{formatTime(version.generatedAt || version.createdAt)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{t(version.captureCount === 1 ? "capture.captureCountOne" : "capture.captureCountOther", { count: version.captureCount })}</span>
                  {version.generatedBy ? <span className="report-history-row-ai">{t("capture.history.aiGenerated")}</span> : null}
                </span>
              </span>
              {version.isCurrent ? <Badge tone="blue">{t("capture.history.current")}</Badge> : null}
            </button>
          </li>
        ))}
      </ul>
    );
  };

  const renderPreviewBody = () => {
    if (detailError) return <p className="report-history-error">{t("capture.history.previewLoadError")}</p>;
    if (!previewSession) return spinner;
    return (
      <div className="report-history-preview-body">
        <LiveReportView
          isPro
          session={previewSession}
          onResolveFile={resolveSourceFile}
          canEditTreatments={false}
          currentUserId={null}
          reportLanguage={tenant?.reportLanguage ?? null}
          appLanguage={tenant?.appLanguage ?? null}
        />
      </div>
    );
  };

  const renderPreviewFooter = () => {
    if (!selected || selected.isCurrent) return null;
    if (confirming) {
      const removedCount = reportVersionRemovedCaptures(session, selected).length;
      return (
        <div className="report-history-confirm">
          <p className="report-history-confirm-title">{t("capture.history.restoreConfirmTitle")}</p>
          <p className="report-history-confirm-body">
            {t("capture.history.restoreConfirmBody", { time: formatTime(selected.generatedAt || selected.createdAt) })}
          </p>
          {removedCount > 0 ? (
            <p className="report-history-confirm-removal">
              {t(removedCount === 1 ? "capture.history.restoreRemovalOne" : "capture.history.restoreRemovalOther", { count: removedCount })}
            </p>
          ) : null}
          <div className="report-history-confirm-actions">
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={restoring}>
              {t("capture.history.cancel")}
            </Button>
            <Button size="sm" variant="danger" onClick={() => void doRestore()} disabled={restoring}>
              {t("capture.history.restoreConfirm")}
            </Button>
          </div>
        </div>
      );
    }
    if (selected.restorable && canRestore) {
      return (
        <div className="report-history-preview-actions">
          <Button variant="danger" onClick={() => setConfirming(true)}>
            {t("capture.history.restore")}
          </Button>
        </div>
      );
    }
    if (!selected.restorable) return <p className="report-history-note">{t("capture.history.previewOnlyHint")}</p>;
    return null;
  };

  const renderPreview = () => (
    <div className="report-history-preview">
      <div className="report-history-banner">
        <span className="report-history-banner-label">
          {t("capture.history.viewing", { time: formatTime(selected?.generatedAt || selected?.createdAt) })}
        </span>
        <Button size="sm" variant="ghost" onClick={backToList}>
          {t("capture.history.backToCurrent")}
        </Button>
      </div>
      {renderPreviewBody()}
      {renderPreviewFooter()}
    </div>
  );

  return (
    <Sheet open title={t("capture.history.title")} leading={<ClockHistoryIcon />} onClose={onClose}>
      <div className="report-history">
        {selected ? (
          renderPreview()
        ) : (
          <div className="report-history-list">
            <p className="report-history-subtitle">{t("capture.history.subtitle")}</p>
            {renderTimeline()}
          </div>
        )}
      </div>
    </Sheet>
  );
}
