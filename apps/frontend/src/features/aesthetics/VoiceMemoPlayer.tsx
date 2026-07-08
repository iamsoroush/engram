import React from "react";
import type { CaptureItem } from "../../domain/types";
import { getCachedCapture } from "../../services/storage/captureStorage";
import { useT } from "../../shared/i18n";

/**
 * A compact voice-memo player for Basic audio — a play/pause button, a slim seekable progress bar,
 * and a small time read-out. Replaces the cramped native <audio controls> on mobile. Resolves the
 * source from the local cache first, then the authenticated file endpoint.
 */
export function VoiceMemoPlayer({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const t = useT();
  const [src, setSrc] = React.useState(() => (item.sourceUrl && !item.sourceUrl.startsWith("/api/v1/") ? item.sourceUrl : ""));
  const [playing, setPlaying] = React.useState(false);
  const [current, setCurrent] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const ownsUrlRef = React.useRef(false);
  const fileEndpoint = item.fileEndpoint || (item.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");

  React.useEffect(() => {
    let cancelled = false;
    void getCachedCapture(item.id)
      .then((cached) => {
        if (cancelled || !cached) return false;
        const url = URL.createObjectURL(cached.blob);
        ownsUrlRef.current = true;
        setSrc(url);
        return true;
      })
      .then((found) => {
        if (found || cancelled || !fileEndpoint) return;
        void onResolveFile(fileEndpoint).then((url) => {
          if (!cancelled) {
            ownsUrlRef.current = url.startsWith("blob:");
            setSrc(url);
          }
        }).catch(() => undefined);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [item.id, fileEndpoint, onResolveFile]);

  React.useEffect(() => () => {
    if (ownsUrlRef.current && src.startsWith("blob:")) URL.revokeObjectURL(src);
  }, [src]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play();
    else audio.pause();
  };

  const seek = (event: React.ChangeEvent<HTMLInputElement>) => {
    const audio = audioRef.current;
    if (!audio || !duration) return;
    audio.currentTime = (Number(event.target.value) / 100) * duration;
  };

  // Some WAV/streamed blobs report `duration` as 0 or Infinity from `loadedmetadata` until the media
  // engine scans to the end — Safari notably shows 0:00 where Chrome infers the length (R6). When the
  // reported duration isn't a positive finite number, force a one-shot seek to the end so the engine
  // computes the real duration, then reset the playhead. Guarded so it only runs while still unknown.
  const readDuration = (audio: HTMLAudioElement) => {
    const reported = audio.duration;
    if (Number.isFinite(reported) && reported > 0) {
      setDuration(reported);
      return;
    }
    const onProbe = () => {
      audio.removeEventListener("timeupdate", onProbe);
      if (Number.isFinite(audio.duration) && audio.duration > 0) setDuration(audio.duration);
      try {
        audio.currentTime = 0;
      } catch {
        /* ignore — resetting the playhead is best-effort */
      }
    };
    audio.addEventListener("timeupdate", onProbe, { once: true });
    try {
      audio.currentTime = 1e101; // clamped to the end by the browser; triggers a real duration scan
    } catch {
      audio.removeEventListener("timeupdate", onProbe);
    }
  };

  const pct = duration ? Math.min(100, (current / duration) * 100) : 0;

  return (
    <div className="voice-memo-player">
      <audio
        ref={audioRef}
        src={src || undefined}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) => readDuration(event.currentTarget)}
        onDurationChange={(event) => {
          const d = event.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) setDuration(d);
        }}
        onEnded={() => {
          setPlaying(false);
          setCurrent(0);
        }}
        preload="metadata"
      />
      <button className="voice-memo-play" onClick={toggle} type="button" aria-label={playing ? t("voice.pause") : t("voice.play")} disabled={!src}>
        {playing ? (
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" rx="1" /><rect x="13.5" y="6" width="3.5" height="12" rx="1" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6.5v11l9-5.5-9-5.5Z" /></svg>
        )}
      </button>
      <input
        className="voice-memo-track"
        type="range"
        min={0}
        max={100}
        value={pct}
        onChange={seek}
        aria-label={t("voice.seek")}
        style={{ "--vm-progress": `${pct}%` } as React.CSSProperties}
        disabled={!src || !duration}
      />
      <span className="voice-memo-time" data-content>{formatTime(current)}{duration ? ` / ${formatTime(duration)}` : ""}</span>
    </div>
  );
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
