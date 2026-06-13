import React from "react";
import type { CaptureItem } from "../../domain/types";

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
      <section className="patient-gallery-card" aria-label="Photo gallery">
        <div className="patient-gallery-head">
          <h2>Photo gallery</h2>
          <span className="patient-gallery-meta">by visit</span>
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
    <section className="patient-gallery-card" aria-label="Photo gallery">
      <div className="patient-gallery-head">
        <h2>Photo gallery</h2>
        <span className="patient-gallery-meta">by visit</span>
      </div>
      {loaded.map((visit) => (
        <div className="patient-gallery-visit" key={visit.sessionId}>
          <div className="patient-gallery-visit-head">
            {visit.dateLabel}
            {visit.title ? ` · ${visit.title}` : ""}
            <span className="patient-gallery-visit-meta"> · {visit.photos.length} photo{visit.photos.length === 1 ? "" : "s"}</span>
          </div>
          <div className="patient-gallery-photos">
            {visit.photos.map((photo) => (
              <GalleryPhoto key={photo.id} photo={photo} onResolveFile={onResolveFile} onOpen={onOpenVisit ? () => onOpenVisit(visit.sessionId) : undefined} />
            ))}
          </div>
        </div>
      ))}
      <p className="patient-gallery-note">
        No tagging — your photos, grouped by visit, recent first. You compare by eye; <b>Pro</b> labels &amp; pairs them with a slider.
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
    <button className="patient-gallery-photo" onClick={onOpen} type="button" aria-label="Open visit">
      {url ? <img alt="Patient photo" src={url} /> : <span className="patient-gallery-photo-empty" aria-hidden="true" />}
    </button>
  );
}
