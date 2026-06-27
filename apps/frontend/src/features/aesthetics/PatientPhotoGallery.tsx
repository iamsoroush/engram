import React from "react";
import type { CaptureItem } from "../../domain/types";
import { useT } from "../../shared/i18n";

export type GalleryVisit = {
  sessionId: string;
  title: string;
  dateLabel: string;
};

type LoadedVisit = GalleryVisit & { photos: CaptureItem[] };

/**
 * AES-202 — per-patient photo gallery, auto-grouped by visit, recent visits prominent. Basic
 * **presents**, it does not tag: no Before/After tags, no app-built pairs, no slider — the eye
 * pairs. Photos are filed to the patient, never the camera roll. Tapping a photo opens the visit.
 */
export function PatientPhotoGallery({
  visits,
  onLoadSessionCaptures,
  onResolveFile,
  onOpenVisit,
  maxVisits = 4,
}: {
  visits: GalleryVisit[];
  onLoadSessionCaptures: (sessionId: string) => Promise<CaptureItem[]>;
  onResolveFile: (endpoint: string) => Promise<string>;
  onOpenVisit?: (sessionId: string) => void;
  maxVisits?: number;
}) {
  const t = useT();
  const [loaded, setLoaded] = React.useState<LoadedVisit[]>([]);
  const [loading, setLoading] = React.useState(true);
  const candidateKey = visits.slice(0, maxVisits).map((visit) => visit.sessionId).join("|");

  React.useEffect(() => {
    let cancelled = false;
    const candidates = visits.filter((visit) => visit.sessionId).slice(0, maxVisits);
    if (!candidates.length) {
      setLoaded([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    void Promise.all(
      candidates.map((visit) =>
        onLoadSessionCaptures(visit.sessionId)
          .then((captures) => ({ ...visit, photos: captures.filter((capture) => capture.type === "photo") }))
          .catch(() => ({ ...visit, photos: [] as CaptureItem[] })),
      ),
    ).then((results) => {
      if (cancelled) return;
      setLoaded(results.filter((visit) => visit.photos.length));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateKey, onLoadSessionCaptures, maxVisits]);

  if (loading) {
    return (
      <section className="patient-gallery-card" aria-label={t("gallery.title")}>
        <div className="patient-gallery-head">
          <h2>{t("gallery.title")}</h2>
          <span className="patient-gallery-meta">{t("gallery.byVisit")}</span>
        </div>
        <div className="patient-gallery-skeleton" aria-hidden="true">
          <span />
          <span />
        </div>
      </section>
    );
  }

  if (!loaded.length) return null;

  return (
    <section className="patient-gallery-card" aria-label={t("gallery.title")}>
      <div className="patient-gallery-head">
        <h2>{t("gallery.title")}</h2>
        <span className="patient-gallery-meta">{t("gallery.byVisit")}</span>
      </div>
      {loaded.map((visit) => (
        <div className="patient-gallery-visit" key={visit.sessionId}>
          <div className="patient-gallery-visit-head">
            <span data-content>{visit.dateLabel}</span>
            {visit.title ? <span data-content>{` · ${visit.title}`}</span> : ""}
            <span className="patient-gallery-visit-meta"> · {visit.photos.length === 1 ? t("gallery.photoCountOne", { n: visit.photos.length }) : t("gallery.photoCountMany", { n: visit.photos.length })}</span>
          </div>
          <div className="patient-gallery-photos">
            {visit.photos.map((photo) => (
              <GalleryPhoto key={photo.id} photo={photo} onResolveFile={onResolveFile} onOpen={onOpenVisit ? () => onOpenVisit(visit.sessionId) : undefined} />
            ))}
          </div>
        </div>
      ))}
      <p className="patient-gallery-note">
        {t("gallery.noteLead")} <b>{t("gallery.noteProName")}</b> {t("gallery.noteTrail")}
      </p>
    </section>
  );
}

function GalleryPhoto({
  photo,
  onResolveFile,
  onOpen,
}: {
  photo: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
  onOpen?: () => void;
}) {
  const t = useT();
  const [url, setUrl] = React.useState(() => (photo.sourceUrl?.startsWith("blob:") ? photo.sourceUrl : ""));
  React.useEffect(() => {
    if (photo.sourceUrl?.startsWith("blob:")) {
      setUrl(photo.sourceUrl);
      return;
    }
    const endpoint = photo.fileEndpoint || (photo.id ? `/api/v1/captures/${photo.id}/file` : "");
    if (!endpoint) return;
    let cancelled = false;
    void onResolveFile(endpoint)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [photo.id, photo.fileEndpoint, photo.sourceUrl, onResolveFile]);
  React.useEffect(() => () => {
    if (url.startsWith("blob:") && url !== photo.sourceUrl) URL.revokeObjectURL(url);
  }, [url, photo.sourceUrl]);

  return (
    <button className="patient-gallery-photo" onClick={onOpen} type="button" aria-label={t("gallery.openVisit")}>
      {url ? <img alt={t("gallery.photoAlt")} src={url} /> : <span className="patient-gallery-photo-empty" aria-hidden="true" />}
    </button>
  );
}
