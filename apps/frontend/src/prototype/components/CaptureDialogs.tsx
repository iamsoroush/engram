import React from "react";
import type { CaptureDraft } from "../appTypes";
import { audioExtensionForMimeType, isSafariBrowser, preferredAudioRecorderOptions } from "../audio";
import { Button, Dialog, Sheet, Textarea } from "../ui";

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

export function PhotoPreviewDialog({
  initialFile,
  open,
  onClose,
  onSave,
}: {
  initialFile?: File | null;
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState("");
  const [previewUrl, setPreviewUrl] = React.useState("");

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
    if (initialFile && initialFile.size === 0) {
      setFile(null);
      setError("The selected photo was empty. Open the camera or gallery again.");
      return;
    }
    setFile(initialFile ?? null);
  }, [initialFile, open]);

  const selectFile = (selectedFile: File | null) => {
    if (selectedFile && selectedFile.size === 0) {
      setFile(null);
      setError("The selected photo was empty. Open the camera or gallery again.");
      return;
    }
    setError("");
    setFile(selectedFile);
  };

  const makeDraft = (): CaptureDraft | null =>
    file
      ? {
          kind: "photo",
          detail: "Clinical photo saved for later review.",
          file,
          filename: file.name || `photo-${Date.now()}.jpg`,
        }
      : null;

  return (
    <Dialog onClose={onClose} open={open} title="Photo preview">
      <div className="photo-preview">
        <input
          aria-label="Select photo from gallery"
          accept="image/*"
          className="input"
          onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
          type="file"
        />
        {previewUrl ? (
          <img alt="Selected capture" className="photo-image-preview" src={previewUrl} />
        ) : (
          <div className="photo-frame">
            <span>Select or take a clinical photo</span>
          </div>
        )}
        {error ? <p className="error-copy">{error}</p> : null}
        <div className="dialog-actions">
          <Button
            disabled={!file}
            onClick={() => {
              const draft = makeDraft();
              if (draft) void onSave(draft);
            }}
          >
            Use photo
          </Button>
          <Button
            disabled={!file}
            onClick={() => {
              const draft = makeDraft();
              if (draft) void onSave(draft, true);
            }}
            variant="secondary"
          >
            Save into new session
          </Button>
        </div>
      </div>
    </Dialog>
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
}: {
  open: boolean;
  onClose: () => void;
  onSave: (draft: CaptureDraft, intoNew?: boolean) => Promise<void>;
}) {
  const [seconds, setSeconds] = React.useState(0);
  const [recorder, setRecorder] = React.useState<MediaRecorder | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [error, setError] = React.useState("");
  const [recordingState, setRecordingState] = React.useState<"recording" | "paused" | "stopped">("stopped");
  const chunksRef = React.useRef<BlobPart[]>([]);
  const streamRef = React.useRef<MediaStream | null>(null);
  const saveOnStopRef = React.useRef(false);

  React.useEffect(() => {
    if (!open) return;
    setSeconds(0);
    const timer = window.setInterval(() => {
      setSeconds((value) => (recordingState === "recording" ? value + 1 : value));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [open, recordingState]);

  React.useEffect(() => {
    if (!open) return;
    chunksRef.current = [];
    saveOnStopRef.current = false;
    setAudioUrl("");
    setError("");
    setRecordingState("stopped");

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Microphone recording is not available here. Attach an audio file instead.");
      return;
    }

    const recorderOptions = preferredAudioRecorderOptions();
    if (isSafariBrowser() && !recorderOptions) {
      setError("Safari cannot record a playable audio format here. Attach an audio file instead.");
      return;
    }

    navigator.mediaDevices
      ?.getUserMedia({ audio: true })
      .then((mediaStream) => {
        streamRef.current = mediaStream;
        const nextRecorder = new MediaRecorder(mediaStream, recorderOptions);
        nextRecorder.ondataavailable = (event) => {
          if (event.data.size) chunksRef.current.push(event.data);
        };
        nextRecorder.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: nextRecorder.mimeType || "audio/webm" });
          const filename = `audio-${Date.now()}.${audioExtensionForMimeType(blob.type)}`;
          setAudioUrl(URL.createObjectURL(blob));
          setRecordingState("stopped");
          streamRef.current?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          if (saveOnStopRef.current && blob.size) {
            void onSave({
              kind: "audio",
              detail: "Clinical audio captured and saved to the backend.",
              file: blob,
              filename,
            });
          }
        };
        nextRecorder.start();
        setRecorder(nextRecorder);
        setRecordingState("recording");
      })
      .catch(() => setError("Microphone permission is needed to record audio."));

    return () => {
      setRecorder((current) => {
        saveOnStopRef.current = false;
        if (current && current.state !== "inactive") current.stop();
        return null;
      });
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [open, onSave]);

  React.useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const stopAndSaveRecording = () => {
    if (!recorder || recorder.state === "inactive") return;
    saveOnStopRef.current = true;
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

  return (
    <Dialog onClose={onClose} open={open} title="Audio recording">
      <div className="recording-panel">
        <div className="record-dot" />
        <h1>00:{seconds.toString().padStart(2, "0")}</h1>
        <p>{recordingState === "paused" ? "Recording paused." : recordingState === "recording" ? "Recording now." : "Recording saved."}</p>
        {error ? <p className="error-copy">{error}</p> : null}
        <input
          accept="audio/*"
          capture
          className="input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            setAudioUrl(URL.createObjectURL(file));
            const fallbackName = `audio-${Date.now()}.${audioExtensionForMimeType(file.type)}`;
            void onSave({
              kind: "audio",
              detail: "Clinical audio captured and saved to the backend.",
              file,
              filename: file.name || fallbackName,
            });
          }}
          type="file"
        />
        {audioUrl ? <audio controls src={audioUrl} /> : null}
        <div className="dialog-actions">
          <Button disabled={!recorder || recorder.state !== "recording"} onClick={pauseRecording} variant="secondary">
            Pause
          </Button>
          <Button disabled={!recorder || recorder.state !== "paused"} onClick={resumeRecording} variant="secondary">
            Resume
          </Button>
          <Button disabled={!recorder || recorder.state === "inactive"} onClick={stopAndSaveRecording}>
            Stop and save
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
