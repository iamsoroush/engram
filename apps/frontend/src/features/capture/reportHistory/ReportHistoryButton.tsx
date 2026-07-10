// Report version-history entry point (E14 / AES-14xx) — the SINGLE CaptureScreen mount surface. It owns
// its own open state and lazily renders the sheet, so the report card only ever mounts this one element.
import React from "react";
import type { CaptureSession } from "../../../domain/types";
import { ClockHistoryIcon } from "../components/CaptureIcons";
import { useT } from "../../../shared/i18n";
import { ReportHistorySheet } from "./ReportHistorySheet";

export function ReportHistoryButton({ session, canRestore }: { session: CaptureSession | null; canRestore: boolean }) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  if (!session) return null;
  return (
    <>
      <button
        className="report-history-button"
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("capture.history.open")}
        title={t("capture.history.openHint")}
      >
        <ClockHistoryIcon />
        <span className="report-history-button-label">{t("capture.history.open")}</span>
      </button>
      {open ? <ReportHistorySheet session={session} canRestore={canRestore} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
