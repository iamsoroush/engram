import React from "react";
import type { CaptureDraft } from "../../../domain/appTypes";
import { audioExtensionForMimeType, isSafariBrowser, preferredAudioRecorderOptions } from "../audio";
import { Button, Sheet, Textarea } from "../../../shared/ui/primitives";
import { useT } from "../../../shared/i18n";

export function TextCaptureSheet({
  open,
  onClose,
  onSave,
  initialValue = "",
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
  /** AES-106 "same as last time": seed the note from the prior visit's typed note (editable). */
  initialValue?: string;
}) {
  const t = useT();
  const [value, setValue] = React.useState("");

  React.useEffect(() => {
    if (open) setValue(initialValue);
  }, [open, initialValue]);

  return (
    <Sheet leading={<NoteLeadingIcon />} onClose={onClose} open={open} title={t("dialog.writeNote")}>
      <div className="sheet-stack">
        {initialValue ? <p className="note-prefill-hint">{t("dialog.notePrefillHint")}</p> : null}
        <Textarea
          autoFocus
          onChange={(event) => setValue(event.target.value)}
          placeholder={t("dialog.notePlaceholder")}
          rows={6}
          value={value}
        />
        <Button
          className="note-primary"
          disabled={!value.trim()}
          onClick={() =>
            void onSave({
              kind: "note",
              detail: value.trim(),
              file: new Blob([value.trim()], { type: "text/plain" }),
              filename: `note-${Date.now()}.txt`,
            })
          }
        >
          {t("dialog.saveToSession")}
        </Button>
        <div className="note-links">
          <button
            className="note-link"
            disabled={!value.trim()}
            onClick={() =>
              void onSave(
                {
                  kind: "note",
                  detail: value.trim(),
                  file: new Blob([value.trim()], { type: "text/plain" }),
                  filename: `note-${Date.now()}.txt`,
                },
                true,
              )
            }
            type="button"
          >
            <PhotoNewSessionIcon />
            {t("dialog.saveToNewSession")}
          </button>
        </div>
        <p className="note-trust">
          <PhotoSecurityIcon />
          <span>{t("dialog.encrypted")}</span>
        </p>
      </div>
    </Sheet>
  );
}

function NoteLeadingIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M5 19h14" />
      <path d="M7 15l9-9 2 2-9 9H7z" />
    </svg>
  );
}

type PhotoSource = "camera" | "library";

export function AddPhotoSheet({
  open,
  onClose,
  onSave,
  ghostPhotoUrl = "",
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
  /** AES-105 — a prior photo to faintly overlay as an alignment aid (no Before/After taxonomy, no AI). */
  ghostPhotoUrl?: string;
}) {
  const t = useT();
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState("");
  const [previewUrl, setPreviewUrl] = React.useState("");
  const [source, setSource] = React.useState<PhotoSource | null>(null);
  const [ghostOn, setGhostOn] = React.useState(false);
  const cameraInputId = React.useId();
  const libraryInputId = React.useId();
  const cameraInputRef = React.useRef<HTMLInputElement | null>(null);
  const libraryInputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  React.useEffect(() => {
    if (!open) return;
    setError("");
    setFile(null);
    setSource(null);
    setGhostOn(false);
  }, [open]);

  const makePhotoDraft = (selectedFile: File): CaptureDraft => ({
    kind: "photo",
    detail: "Clinical photo saved for later review.",
    file: selectedFile,
    filename: selectedFile.name || `photo-${Date.now()}.jpg`,
  });

  const selectFile = (selectedFile: File | null, nextSource: PhotoSource) => {
    setSource(selectedFile ? nextSource : null);
    if (selectedFile && selectedFile.size === 0) {
      setFile(null);
      setError(t("dialog.photoEmptyError"));
      return;
    }
    setError("");
    setFile(selectedFile);
  };

  const makeDraft = (): CaptureDraft | null =>
    file ? makePhotoDraft(file) : null;

  if (!open) return null;

  return (
    <div className="overlay add-photo-overlay" role="presentation">
      <aside aria-labelledby="add-photo-title" aria-modal="true" className="add-photo-sheet" role="dialog">
        <div className="add-photo-handle" aria-hidden="true" />
        <button aria-label={t("dialog.closeAddPhoto")} className="add-photo-close" onClick={onClose} type="button">
          <PhotoCloseIcon />
        </button>
        <div className="add-photo-header">
          <span className="add-photo-chip" aria-hidden="true">
            <PhotoCameraIcon />
          </span>
          <h2 id="add-photo-title">{t("dialog.addPhoto")}</h2>
        </div>
        <div className="add-photo-segments" aria-label={t("dialog.photoSource")}>
          <button
            className={source === "camera" ? "active" : ""}
            onClick={() => {
              setSource(null);
              cameraInputRef.current?.click();
            }}
            type="button"
          >
            <PhotoCameraIcon />
            <span>{t("dialog.takePhoto")}</span>
          </button>
          <button
            className={source === "library" ? "active" : ""}
            onClick={() => {
              setSource(null);
              libraryInputRef.current?.click();
            }}
            type="button"
          >
            <PhotoLibraryIcon />
            <span>{t("dialog.choose")}</span>
          </button>
        </div>
        <input
          aria-label={t("dialog.takePhotoWithCamera")}
          accept="image/*"
          capture="environment"
          className="visually-hidden-file"
          id={cameraInputId}
          onChange={(event) => {
            selectFile(event.target.files?.[0] ?? null, "camera");
            event.target.value = "";
          }}
          ref={cameraInputRef}
          type="file"
        />
        <input
          aria-label={t("dialog.choosePhotoFromLibrary")}
          accept="image/*"
          className="visually-hidden-file"
          id={libraryInputId}
          onChange={(event) => {
            selectFile(event.target.files?.[0] ?? null, "library");
            event.target.value = "";
          }}
          ref={libraryInputRef}
          type="file"
        />
        {ghostPhotoUrl ? (
          <button
            aria-pressed={ghostOn}
            className={`add-photo-ghost-toggle${ghostOn ? " active" : ""}`}
            onClick={() => setGhostOn((value) => !value)}
            type="button"
          >
            <span aria-hidden="true">⊕</span>
            {ghostOn ? t("dialog.aligningToLastPhoto") : t("dialog.alignToLastPhoto")}
          </button>
        ) : null}
        {previewUrl ? (
          <div className="add-photo-preview">
            <img alt={t("dialog.selectedCapture")} className="photo-image-preview" src={previewUrl} />
            {ghostPhotoUrl && ghostOn ? <img alt="" aria-hidden="true" className="add-photo-ghost-overlay" src={ghostPhotoUrl} /> : null}
            <button
              aria-label={t("dialog.removeSelectedPhoto")}
              className="add-photo-remove"
              onClick={() => {
                setFile(null);
                setSource(null);
                setError("");
              }}
              type="button"
            >
              <PhotoCloseIcon />
            </button>
          </div>
        ) : (
          <div className="add-photo-empty">
            {ghostPhotoUrl && ghostOn ? (
              <img alt="" aria-hidden="true" className="add-photo-ghost-overlay" src={ghostPhotoUrl} />
            ) : null}
            <span className="add-photo-empty-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <path d="M12 16V7M8.5 10.5 12 7l3.5 3.5M5 19h14" />
              </svg>
            </span>
            <span className="add-photo-empty-copy">
              <strong>{t("dialog.noPhotoYet")}</strong>
              <small>{ghostPhotoUrl ? t("dialog.alignGhostHint") : t("dialog.takeOrPickHint")}</small>
            </span>
          </div>
        )}
        {error ? <p className="error-copy">{error}</p> : null}
        {file ? (
          <>
            <Button
              className="add-photo-primary"
              onClick={() => {
                const draft = makeDraft();
                if (draft) void onSave(draft);
              }}
            >
              <PhotoCameraIcon />
              {t("dialog.usePhoto")}
            </Button>
            <div className="add-photo-links">
              <button
                className="add-photo-link"
                onClick={() => {
                  const draft = makeDraft();
                  if (draft) void onSave(draft, true);
                }}
                type="button"
              >
                <PhotoNewSessionIcon />
                {t("dialog.saveToNewSession")}
              </button>
            </div>
          </>
        ) : null}
        <p className="add-photo-security">
          <PhotoSecurityIcon />
          <span>{t("dialog.encryptedStoredSecurely")}</span>
        </p>
      </aside>
    </div>
  );
}

function PhotoCameraIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M6.8 7.2h2.1l1.4-2h3.4l1.4 2h2.1a3 3 0 0 1 3 3v6.4a3 3 0 0 1-3 3H6.8a3 3 0 0 1-3-3v-6.4a3 3 0 0 1 3-3Z" />
      <path d="M12 16.7a3.9 3.9 0 1 0 0-7.8 3.9 3.9 0 0 0 0 7.8Z" />
    </svg>
  );
}

function PhotoCloseIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m7 7 10 10" />
      <path d="m17 7-10 10" />
    </svg>
  );
}

function PhotoLibraryIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M5 4.8h14a2.2 2.2 0 0 1 2.2 2.2v10a2.2 2.2 0 0 1-2.2 2.2H5A2.2 2.2 0 0 1 2.8 17V7A2.2 2.2 0 0 1 5 4.8Z" />
      <path d="m4 16 4.3-4.2 3.2 3.1 2.4-2.3 5.9 5.7" />
      <path d="M16.2 9.2h.1" />
    </svg>
  );
}

function PhotoNewSessionIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M7 3.8h7.4L19 8.4V20a2.2 2.2 0 0 1-2.2 2.2H7A2.2 2.2 0 0 1 4.8 20V6A2.2 2.2 0 0 1 7 3.8Z" />
      <path d="M14.2 4.2V9h4.6" />
      <path d="M12 12.2v5.2" />
      <path d="M9.4 14.8h5.2" />
    </svg>
  );
}

function PhotoSecurityIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 3.5 19 6v5.4c0 4.2-2.8 7.4-7 9.1-4.2-1.7-7-4.9-7-9.1V6l7-2.5Z" />
      <path d="m9 12.1 2 2 4.2-4.5" />
    </svg>
  );
}

/**
 * Owns microphone capture lifecycle and falls back to file attachment when the
 * browser cannot produce a supported recording stream.
 */
export function AudioDialog({
  open,
  onClose,
  onSave,
  storageWarning,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
  /** Set when durable storage is low (~85%+): a long recording may not fit (Epic G). */
  storageWarning?: { usageRatio: number } | null;
}) {
  const t = useT();
  const [seconds, setSeconds] = React.useState(0);
  const [recorder, setRecorder] = React.useState<MediaRecorder | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [error, setError] = React.useState("");
  const [waveHeights, setWaveHeights] = React.useState(defaultRecordingWaveHeights);
  const [minimized, setMinimized] = React.useState(false);
  const [recordingState, setRecordingState] = React.useState<"idle" | "recording" | "paused" | "saving" | "saved" | "error">("idle");
  const audioContextRef = React.useRef<AudioContext | null>(null);
  const analyserFrameRef = React.useRef(0);
  const chunksRef = React.useRef<BlobPart[]>([]);
  const discardNextStopRef = React.useRef(false);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const onSaveRef = React.useRef(onSave);
  const streamRef = React.useRef<MediaStream | null>(null);
  const saveOnStopRef = React.useRef(false);

  React.useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds((value) => (recordingState === "recording" ? value + 1 : value));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [recordingState]);

  React.useEffect(() => {
    if (!open) return;
    setSeconds(0);
    chunksRef.current = [];
    discardNextStopRef.current = false;
    saveOnStopRef.current = false;
    setAudioUrl("");
    setError("");
    setWaveHeights(defaultRecordingWaveHeights);
    setMinimized(false);
    setRecordingState("idle");

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError(t("dialog.micUnavailable"));
      setRecordingState("error");
      return;
    }

    const recorderOptions = preferredAudioRecorderOptions();
    if (isSafariBrowser() && !recorderOptions) {
      setError(t("dialog.safariUnsupported"));
      setRecordingState("error");
      return;
    }

    navigator.mediaDevices
      ?.getUserMedia({ audio: true })
      .then((mediaStream) => {
        streamRef.current = mediaStream;
        startLevelMonitor(mediaStream, setWaveHeights, audioContextRef, analyserFrameRef);
        const nextRecorder = new MediaRecorder(mediaStream, recorderOptions);
        nextRecorder.ondataavailable = (event) => {
          if (event.data.size) chunksRef.current.push(event.data);
        };
        nextRecorder.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: nextRecorder.mimeType || "audio/webm" });
          const filename = `audio-${Date.now()}.${audioExtensionForMimeType(blob.type)}`;
          streamRef.current?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          if (discardNextStopRef.current) {
            discardNextStopRef.current = false;
            return;
          }
          setAudioUrl(URL.createObjectURL(blob));
          if (saveOnStopRef.current && blob.size) {
            setRecordingState("saving");
            void onSaveRef.current({
              kind: "audio",
              detail: "Clinical audio captured and saved to the backend.",
              file: blob,
              filename,
            }).then(() => setRecordingState("saved"));
            return;
          }
          setRecordingState("saved");
        };
        nextRecorder.start();
        setRecorder(nextRecorder);
        setRecordingState("recording");
      })
      .catch(() => {
        setError(t("dialog.micPermissionNeeded"));
        setRecordingState("error");
      });

    return () => {
      setRecorder((current) => {
        discardNextStopRef.current = true;
        saveOnStopRef.current = false;
        if (current && current.state !== "inactive") current.stop();
        return null;
      });
      stopLevelMonitor(audioContextRef, analyserFrameRef);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [open]);

  React.useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const stopAndSaveRecording = () => {
    if (!recorder || recorder.state === "inactive") return;
    saveOnStopRef.current = true;
    setRecordingState("saving");
    recorder.stop();
  };

  const pauseRecording = () => {
    if (recorder?.state !== "recording") return;
    recorder.pause();
    setRecordingState("paused");
  };

  const resumeRecording = () => {
    if (recorder?.state !== "paused") return;
    recorder.resume();
    setRecordingState("recording");
  };

  const useAudioFile = (file: File) => {
    saveOnStopRef.current = false;
    discardNextStopRef.current = true;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopLevelMonitor(audioContextRef, analyserFrameRef);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setAudioUrl(URL.createObjectURL(file));
    setRecordingState("saving");
    const fallbackName = `audio-${Date.now()}.${audioExtensionForMimeType(file.type)}`;
    void onSaveRef.current({
      kind: "audio",
      detail: "Clinical audio captured and saved to the backend.",
      file,
      filename: file.name || fallbackName,
    }).then(() => setRecordingState("saved"));
  };

  const discardRecording = () => {
    if (!window.confirm(t("dialog.discardAudioConfirm"))) return;
    discardNextStopRef.current = true;
    saveOnStopRef.current = false;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopLevelMonitor(audioContextRef, analyserFrameRef);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setRecordingState("idle");
    onClose();
  };

  const displayTime = formatRecordingTime(seconds);
  const isRecording = recordingState === "recording";
  const isPaused = recordingState === "paused";
  const isSaving = recordingState === "saving";
  const primaryPauseLabel = isPaused ? t("dialog.resumeRecording") : t("dialog.pauseRecording");

  if (!open) return null;

  if (minimized) {
    return (
      <button className="recording-minibar" onClick={() => setMinimized(false)} type="button">
        <span className="recording-minibar-dot" aria-hidden="true" />
        <span>
          <strong>{isPaused ? t("dialog.recordingPaused") : t("dialog.recordingInBackground")}</strong>
          <small>{displayTime}</small>
        </span>
      </button>
    );
  }

  return (
    <div className="overlay recording-sheet-overlay" role="presentation">
      <aside aria-modal="true" aria-labelledby="recording-audio-title" className="recording-sheet" role="dialog">
        <div className="recording-sheet-handle" aria-hidden="true" />
        <button className="recording-discard-button" disabled={isSaving} onClick={discardRecording} type="button" aria-label={t("dialog.discardRecording")}>
          <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
            <path d="M7 7l10 10M17 7 7 17" />
          </svg>
        </button>
        <div className="recording-sheet-header">
          <span className={`recording-live-dot ${isPaused ? "paused" : ""}`} aria-hidden="true" />
          <h2 id="recording-audio-title">{t("dialog.recordingAudio")}</h2>
        </div>

        {storageWarning ? (
          <p className="recording-storage-warning" role="status">
            {t("dialog.storageWarning", { pct: Math.round((storageWarning.usageRatio || 0) * 100) })}
          </p>
        ) : null}

        <div className="recording-capsule" aria-live="polite">
          <strong className="recording-capsule-time">{displayTime}</strong>
          <div className={`recording-waveform ${isPaused ? "paused" : ""}`} aria-hidden="true">
            {waveHeights.map((height, index) => (
              <span key={index} style={{ "--wave-index": index, "--wave-height": `${height}px` } as React.CSSProperties} />
            ))}
          </div>
        </div>

        <p className="recording-trust">
          <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
            <path d="M12 3.5 19 7v5.5c0 4-2.8 6.7-7 8-4.2-1.3-7-4-7-8V7l7-3.5Z" />
            <path d="M9.5 12h5v4h-5zM10.5 12v-1.2a1.5 1.5 0 0 1 3 0V12" />
          </svg>
          {t("dialog.encryptedListeningInBackground")}
        </p>

        {error ? <p className="error-copy">{error}</p> : null}
        <input
          ref={fileInputRef}
          aria-label={t("dialog.selectAudioFile")}
          accept="audio/*"
          capture
          className="visually-hidden-file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            useAudioFile(file);
            event.currentTarget.value = "";
          }}
          type="file"
        />

        {audioUrl && recordingState === "saved" ? <audio className="recording-playback" controls src={audioUrl} /> : null}

        <div className="recording-actions">
          <button
            className="recording-action pause"
            disabled={isSaving || (!isRecording && !isPaused)}
            onClick={isPaused ? resumeRecording : pauseRecording}
            type="button"
            aria-label={primaryPauseLabel}
          >
            <span className={`recording-action-symbol ${isPaused ? "play" : "pause"}`} aria-hidden="true" />
          </button>
          <button
            className="recording-action stop"
            disabled={isSaving || !recorder || recorder.state === "inactive"}
            onClick={stopAndSaveRecording}
            type="button"
          >
            <span aria-hidden="true" />
            {isSaving ? t("dialog.saving") : t("dialog.stopAndSave")}
          </button>
        </div>

        <div className="recording-links">
          <button
            className="recording-link"
            disabled={isSaving || (!isRecording && !isPaused)}
            onClick={() => setMinimized(true)}
            type="button"
          >
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="M8 6H5.5A1.5 1.5 0 0 0 4 7.5v11A1.5 1.5 0 0 0 5.5 20h11A1.5 1.5 0 0 0 18 18.5V16M13 4h7v7M11 13 20 4" />
            </svg>
            {t("dialog.continueInBackground")}
          </button>
          <button className="recording-link muted" onClick={() => fileInputRef.current?.click()} type="button">
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="M12 16V4M7.5 8.5 12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
            </svg>
            {t("dialog.useAudioFile")}
          </button>
        </div>
      </aside>
    </div>
  );
}

function formatRecordingTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

const defaultRecordingWaveHeights = [8, 9, 10, 11, 14, 22, 28, 34, 42, 50, 58, 68, 60, 54, 48, 54, 60, 56, 48, 42, 36, 30, 24, 18, 13, 11, 10, 9, 8];

function startLevelMonitor(
  mediaStream: MediaStream,
  setWaveHeights: React.Dispatch<React.SetStateAction<number[]>>,
  audioContextRef: React.MutableRefObject<AudioContext | null>,
  frameRef: React.MutableRefObject<number>,
) {
  const AudioContextClass =
    window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextClass) return;

  stopLevelMonitor(audioContextRef, frameRef);
  const context = new AudioContextClass();
  if (context.state === "suspended") void context.resume();
  const analyser = context.createAnalyser();
  analyser.fftSize = 128;
  analyser.smoothingTimeConstant = 0.72;
  const source = context.createMediaStreamSource(mediaStream);
  source.connect(analyser);
  const timeData = new Uint8Array(analyser.fftSize);
  audioContextRef.current = context;

  const tick = () => {
    analyser.getByteTimeDomainData(timeData);
    const sumSquares = timeData.reduce((sum, value) => {
      const centered = (value - 128) / 128;
      return sum + centered * centered;
    }, 0);
    const rms = Math.sqrt(sumSquares / timeData.length);
    const level = Math.min(1, rms * 5.8);
    const nextHeights = defaultRecordingWaveHeights.map((baseHeight, index) => {
      const centerDistance = Math.abs(index - (defaultRecordingWaveHeights.length - 1) / 2);
      const centerWeight = 1 - centerDistance / ((defaultRecordingWaveHeights.length - 1) / 2);
      const ripple = 0.78 + 0.22 * Math.sin(Date.now() / 95 + index * 0.72);
      return Math.round(baseHeight * 0.72 + level * (24 + centerWeight * 42) * ripple);
    });
    setWaveHeights(nextHeights);
    frameRef.current = window.requestAnimationFrame(tick);
  };

  tick();
}

function stopLevelMonitor(audioContextRef: React.MutableRefObject<AudioContext | null>, frameRef: React.MutableRefObject<number>) {
  if (frameRef.current) window.cancelAnimationFrame(frameRef.current);
  frameRef.current = 0;
  void audioContextRef.current?.close();
  audioContextRef.current = null;
}
