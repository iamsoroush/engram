import React from "react";

/**
 * The aesthetics before/after surface (redesign-pro-report §2.4): a paired before/after photo with two
 * modes — **side-by-side** (honest, scannable; the default) and **compare** (a draggable slider that
 * overlays after-over-before for aligned progress reading). The rendering *consumes* the deterministic
 * `photo_pairing` (it never pairs); a small toggle switches the two modes. Bilingual + RTL-aware.
 */

/** Resolve a capture's file URL through the app's signed-URL resolver (mirrors MarkdownImage). */
function useResolvedFile(captureId: string | undefined, onResolveFile: (endpoint: string) => Promise<string>): string {
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    let cancelled = false;
    setUrl("");
    if (!captureId) return;
    onResolveFile(`/api/v1/captures/${captureId}/file-content`)
      .then((resolved) => {
        if (!cancelled) setUrl(resolved);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [captureId, onResolveFile]);
  React.useEffect(() => () => {
    if (url.startsWith("blob:")) URL.revokeObjectURL(url);
  }, [url]);
  return url;
}

export type BeforeAfterPhoto = { captureId?: string; caption?: string };

export function BeforeAfterSlider({
  before,
  after,
  onResolveFile,
  isPersian,
}: {
  before: BeforeAfterPhoto;
  after: BeforeAfterPhoto;
  onResolveFile: (endpoint: string) => Promise<string>;
  isPersian?: boolean;
}) {
  const beforeUrl = useResolvedFile(before.captureId, onResolveFile);
  const afterUrl = useResolvedFile(after.captureId, onResolveFile);
  const [mode, setMode] = React.useState<"side" | "compare">("side");
  const [pos, setPos] = React.useState(50); // % of the before layer revealed from the left
  const frameRef = React.useRef<HTMLDivElement>(null);
  const draggingRef = React.useRef(false);

  const t = isPersian
    ? { before: "قبل", after: "بعد", side: "کنار هم", compare: "مقایسه", title: "قبل و بعد" }
    : { before: "Before", after: "After", side: "Side by side", compare: "Compare", title: "Before / after" };

  const setFromClientX = React.useCallback((clientX: number) => {
    const el = frameRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const next = ((clientX - rect.left) / rect.width) * 100;
    setPos(Math.max(0, Math.min(100, next)));
  }, []);

  const onPointerDown = (event: React.PointerEvent) => {
    draggingRef.current = true;
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    setFromClientX(event.clientX);
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (!draggingRef.current) return;
    setFromClientX(event.clientX);
  };
  const endDrag = () => {
    draggingRef.current = false;
  };

  const captionRow = (
    <div className="ba-captions">
      {before.caption ? <span className="ba-caption" dir="auto">{before.caption}</span> : <span />}
      {after.caption ? <span className="ba-caption" dir="auto">{after.caption}</span> : <span />}
    </div>
  );

  return (
    <figure className="before-after" dir={isPersian ? "rtl" : "ltr"} aria-label={t.title}>
      <div className="ba-toolbar" role="group" aria-label={t.title}>
        <button type="button" className={mode === "side" ? "on" : ""} onClick={() => setMode("side")}>
          {t.side}
        </button>
        <button type="button" className={mode === "compare" ? "on" : ""} onClick={() => setMode("compare")}>
          ⟷ {t.compare}
        </button>
      </div>

      {mode === "side" ? (
        <>
          <div className="ba-side">
            <div className="ba-fig">
              <span className="ba-tag">{t.before}</span>
              {beforeUrl ? <img src={beforeUrl} alt={before.caption || t.before} /> : <span className="ba-empty" aria-hidden="true" />}
            </div>
            <div className="ba-fig">
              <span className="ba-tag">{t.after}</span>
              {afterUrl ? <img src={afterUrl} alt={after.caption || t.after} /> : <span className="ba-empty" aria-hidden="true" />}
            </div>
          </div>
          {captionRow}
        </>
      ) : (
        <>
          <div
            className="ba-compare"
            ref={frameRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
            role="slider"
            aria-label={t.compare}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pos)}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") setPos((p) => Math.max(0, p - 4));
              if (e.key === "ArrowRight") setPos((p) => Math.min(100, p + 4));
            }}
          >
            {afterUrl ? <img className="ba-layer ba-after" src={afterUrl} alt={after.caption || t.after} draggable={false} /> : <span className="ba-empty" aria-hidden="true" />}
            {beforeUrl ? (
              <img
                className="ba-layer ba-before"
                src={beforeUrl}
                alt={before.caption || t.before}
                draggable={false}
                style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
              />
            ) : null}
            <span className="ba-tag ba-tag-l">{t.before}</span>
            <span className="ba-tag ba-tag-r">{t.after}</span>
            <span className="ba-handle" style={{ left: `${pos}%` }} aria-hidden="true">
              <span className="ba-knob">⟷</span>
            </span>
          </div>
          {captionRow}
        </>
      )}
    </figure>
  );
}
