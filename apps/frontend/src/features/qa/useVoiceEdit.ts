import React from "react";
import type { ApiFetch } from "../../domain/appTypes";
import type { Translator } from "../../shared/i18n";
import { preferredAudioRecorderOptions } from "../capture/audio";
import { fetchQaMessageDraft, requestQaVoiceEdit } from "./qaClient";

type VoiceState = "idle" | "recording" | "applying";

/**
 * Records a doctor's voice note for a Q&A reply, uploads it, and polls until the AI has revised or
 * replaced the draft (AES-402). The reply box is the review surface, so the result is handed back via
 * `onApplied(text, mode)` for the doctor to review + Send — nothing auto-sends.
 */
export function useVoiceEdit({
  apiFetch,
  messageId,
  getDraft,
  onApplied,
  onError,
  t,
}: {
  apiFetch: ApiFetch;
  messageId: string | undefined;
  getDraft: () => string;
  onApplied: (text: string, mode: "revise" | "replace") => void;
  onError?: (message: string) => void;
  /** App-language translator — the hook's error copy is chrome and must be localized. */
  t: Translator;
}) {
  const [state, setState] = React.useState<VoiceState>("idle");
  const [seconds, setSeconds] = React.useState(0);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const streamRef = React.useRef<MediaStream | null>(null);
  const timerRef = React.useRef<number | null>(null);
  const cancelledRef = React.useRef(false);

  const cleanup = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const apply = React.useCallback(
    async (blob: Blob) => {
      if (!messageId) return;
      setState("applying");
      setSeconds(0);
      try {
        await requestQaVoiceEdit(apiFetch, messageId, blob, getDraft());
        for (let attempt = 0; attempt < 20; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          const draft = await fetchQaMessageDraft(apiFetch, messageId);
          if (draft.draftStatus !== "revising") {
            // Only surface "Revised" for a GENUINE voice result — `draftMode` is set solely when the
            // draft carries an `ai-voice:` source. A deterministic fallback (unusable output / no
            // gateway) leaves the draft unchanged and surfaces `failed_revise`; never claim success
            // over an edit that didn't land (Q-1, INV-SILENT).
            if (draft.draftStatus === "ready" && draft.draft && draft.draftMode) {
              onApplied(draft.draft, draft.draftMode);
            } else if (draft.draftStatus === "failed_revise") {
              onError?.(t("qa.voiceReviseFailed"));
            } else {
              onError?.(t("qa.voiceApplyError"));
            }
            setState("idle");
            return;
          }
        }
        onError?.(t("qa.voiceTimeout"));
        setState("idle");
      } catch {
        onError?.(t("qa.voiceApplyError"));
        setState("idle");
      }
    },
    [apiFetch, messageId, getDraft, onApplied, onError, t],
  );

  const start = React.useCallback(async () => {
    if (!messageId || state !== "idle") return;
    cancelledRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream, preferredAudioRecorderOptions());
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        cleanup();
        if (cancelledRef.current) {
          setState("idle");
          setSeconds(0);
          return;
        }
        void apply(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      };
      recorderRef.current = recorder;
      recorder.start();
      setState("recording");
      setSeconds(0);
      timerRef.current = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    } catch {
      cleanup();
      onError?.(t("qa.voiceMicNeeded"));
      setState("idle");
    }
  }, [apply, cleanup, messageId, onError, state, t]);

  const stop = React.useCallback(() => {
    if (recorderRef.current && state === "recording") {
      cancelledRef.current = false;
      recorderRef.current.stop();
    }
  }, [state]);

  const cancel = React.useCallback(() => {
    cancelledRef.current = true;
    if (recorderRef.current && state === "recording") recorderRef.current.stop();
    else {
      cleanup();
      setState("idle");
      setSeconds(0);
    }
  }, [cleanup, state]);

  React.useEffect(() => () => cleanup(), [cleanup]);

  return { state, seconds, start, stop, cancel };
}
