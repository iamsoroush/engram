import React from "react";
import { formatBytes, type StorageStatus } from "../../../services/storage/storageStatus";
import { useT } from "../../../shared/i18n";

/** Hard-stop shown when durable storage is full and a new capture can't be guaranteed to save
 * (Epic G). Capturing is paused; staff can export queued captures and free space. */
export function StorageGuardDialog({
  storage,
  pendingCount,
  onExport,
  onClose,
}: {
  storage: StorageStatus;
  pendingCount: number;
  onExport: () => Promise<void> | void;
  onClose: () => void;
}) {
  const t = useT();
  const [exporting, setExporting] = React.useState(false);
  const percent = Math.round((storage.usageRatio || 0) * 100);
  const remaining = formatBytes(storage.remainingBytes);
  const exportQueued = () => {
    if (exporting) return;
    setExporting(true);
    void Promise.resolve(onExport()).finally(() => setExporting(false));
  };
  return (
    <div className="assignment-scrim" role="presentation">
      <section aria-labelledby="storage-guard-title" aria-modal="true" className="assignment-sheet storage-guard-sheet" role="dialog">
        <div className="assignment-sheet-handle" aria-hidden="true" />
        <div className="assignment-sheet-header">
          <h2 id="storage-guard-title">{t("storage.title")}</h2>
          <button aria-label={t("storage.close")} className="storage-guard-close" onClick={onClose} type="button">
            <span aria-hidden="true">×</span>
          </button>
        </div>
        <p className="storage-guard-copy">
          {t("storage.bodyBefore")}
          <strong>{t("storage.percentFull", { percent })}</strong>
          {t("storage.bodyAfter", { remaining })}
        </p>
        <div className="storage-guard-actions">
          <button className="storage-guard-export" disabled={exporting || !pendingCount} onClick={exportQueued} type="button">
            {exporting
              ? t("storage.exporting")
              : pendingCount
                ? t("storage.exportQueuedCount", { count: pendingCount })
                : t("storage.exportQueued")}
          </button>
          <button className="storage-guard-dismiss" onClick={onClose} type="button">
            {t("storage.dismiss")}
          </button>
        </div>
        {pendingCount ? null : <p className="storage-guard-note">{t("storage.noQueued")}</p>}
      </section>
    </div>
  );
}
