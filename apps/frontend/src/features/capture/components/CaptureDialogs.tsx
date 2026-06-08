import React from "react";
import type { CaptureDraft } from "../../../domain/appTypes";
import { audioExtensionForMimeType, isSafariBrowser, preferredAudioRecorderOptions } from "../audio";
import { Button, Sheet, Textarea } from "../../../shared/ui/primitives";

export function TextCaptureSheet({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [value, setValue] = React.useState("");

  React.useEffect(() => {
    if (open) setValue("");
  }, [open]);

  return (
    <Sheet onClose={onClose} open={open} title="Write note">
      <div className="sheet-stack">
        <Textarea
          autoFocus
          onChange={(event) => setValue(event.target.value)}
          placeholder="Type the note now. Patient matching can wait."
          rows={7}
          value={value}
        />
        <Button
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
          Save to current session
        </Button>
        <Button
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
          variant="secondary"
        >
          Save into new session
        </Button>
      </div>
    </Sheet>
  );
}

type PhotoSource = "camera" | "library";

export function AddPhotoSheet({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState("");
  const [previewUrl, setPreviewUrl] = React.useState("");
  const [source, setSource] = React.useState<PhotoSource | null>(null);
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
      setError("The selected photo was empty. Open the camera or gallery again.");
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
        <button aria-label="Close add photo" className="add-photo-close" onClick={onClose} type="button">
          <PhotoCloseIcon />
        </button>
        <h2 id="add-photo-title">Add photo</h2>
        <div className="add-photo-segments" aria-label="Photo source">
          <button
            className={source === "camera" ? "active" : ""}
            onClick={() => {
              setSource(null);
              cameraInputRef.current?.click();
            }}
            type="button"
          >
            <PhotoCameraIcon />
            <span>Take photo</span>
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
            <span>Choose a photo</span>
          </button>
        </div>
        <input
          aria-label="Take photo with camera"
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
          aria-label="Choose photo from library"
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
        <div className="add-photo-preview">
          {previewUrl ? (
            <img alt="Selected capture" className="photo-image-preview" src={previewUrl} />
          ) : (
            <div className="add-photo-empty">
              <PhotoEmptyIcon />
              <strong>No photo selected</strong>
              <p>Take a new photo or choose from your device to add it to this session.</p>
            </div>
          )}
        </div>
        {error ? <p className="error-copy">{error}</p> : null}
        <div className="add-photo-actions">
          <Button
            className="add-photo-primary"
            disabled={!file}
            onClick={() => {
              const draft = makeDraft();
              if (draft) void onSave(draft);
            }}
          >
            <PhotoCameraIcon />
            Use photo
          </Button>
          <Button
            className="add-photo-secondary"
            disabled={!file}
            onClick={() => {
              const draft = makeDraft();
              if (draft) void onSave(draft, true);
            }}
            variant="secondary"
          >
            <PhotoNewSessionIcon />
            Save to new session
          </Button>
        </div>
        <p className="add-photo-security">
          <PhotoSecurityIcon />
          <span>Photos are stored securely and encrypted.</span>
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

function PhotoEmptyIcon() {
  return (
    <svg viewBox="0 0 96 72" focusable="false" aria-hidden="true">
      <path d="M25 25h11l5-8h14l5 8h11a8 8 0 0 1 8 8v23a8 8 0 0 1-8 8H25a8 8 0 0 1-8-8V33a8 8 0 0 1 8-8Z" />
      <path d="M48 55a14 14 0 1 0 0-28 14 14 0 0 0 0 28Z" />
      <path d="M48 47a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z" />
      <path d="M14 18v8M10 22h8M79 16v8M75 20h8M84 39v8M80 43h8" />
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
      setError("Microphone recording is not available here. Attach an audio file instead.");
      setRecordingState("error");
      return;
    }

    const recorderOptions = preferredAudioRecorderOptions();
    if (isSafariBrowser() && !recorderOptions) {
      setError("Safari cannot record a playable audio format here. Attach an audio file instead.");
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
        setError("Microphone permission is needed to record audio.");
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
    if (!window.confirm("Discard this audio recording?")) return;
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
  const primaryPauseLabel = isPaused ? "Resume recording" : "Pause recording";

  if (!open) return null;

  if (minimized) {
    return (
      <button className="recording-minibar" onClick={() => setMinimized(false)} type="button">
        <span className="recording-minibar-dot" aria-hidden="true" />
        <span>
          <strong>{isPaused ? "Recording paused" : "Recording in background"}</strong>
          <small>{displayTime}</small>
        </span>
      </button>
    );
  }

  return (
    <div className="overlay recording-sheet-overlay" role="presentation">
      <aside aria-modal="true" aria-labelledby="recording-audio-title" className="recording-sheet" role="dialog">
        <div className="recording-sheet-handle" aria-hidden="true" />
        <button className="recording-discard-button" disabled={isSaving} onClick={discardRecording} type="button" aria-label="Discard recording">
          <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
            <path d="M7 7l10 10M17 7 7 17" />
          </svg>
        </button>
        <div className="recording-sheet-header">
          <span className={`recording-live-dot ${isPaused ? "paused" : ""}`} aria-hidden="true" />
          <h2 id="recording-audio-title">Recording audio</h2>
        </div>

        {storageWarning ? (
          <p className="recording-storage-warning" role="status">
            Device storage is {Math.round((storageWarning.usageRatio || 0) * 100)}% full — a long recording may not fit. Consider exporting queued captures or freeing space first.
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
          Encrypted · listening in background
        </p>

        {error ? <p className="error-copy">{error}</p> : null}
        <input
          ref={fileInputRef}
          aria-label="Select audio file"
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
            {isSaving ? "Saving..." : "Stop & save"}
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
            Continue in background
          </button>
          <button className="recording-link muted" onClick={() => fileInputRef.current?.click()} type="button">
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="M12 16V4M7.5 8.5 12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
            </svg>
            Use audio file
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
