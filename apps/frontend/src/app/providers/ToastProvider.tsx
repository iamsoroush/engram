import React from "react";
import { Toast } from "../../shared/ui/primitives";

// Seam A4 (frontend-refactor plan §2). A single transient toast, owned by a provider so it no longer
// threads through props or lives as App state — both the app body and the session store raise toasts
// via `useToast().setToast`. The provider renders the toast + owns its auto-dismiss timer.

export type ToastTone = "default" | "danger";
export type ToastOptions = { tone?: ToastTone; durationMs?: number };

type ToastState = { message: string; tone: ToastTone; durationMs: number };
type ToastContextValue = {
  toast: string;
  toastTone: ToastTone;
  /** Raise a toast; `options.tone: "danger"` renders the warning style, `durationMs` overrides the
   *  auto-dismiss (default 2200ms). Callers passing only a message keep the neutral, short toast. */
  setToast: (message: string, options?: ToastOptions) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<ToastState>({ message: "", tone: "default", durationMs: 2200 });

  const setToast = React.useCallback((message: string, options?: ToastOptions) => {
    setState({ message, tone: options?.tone ?? "default", durationMs: options?.durationMs ?? 2200 });
  }, []);

  React.useEffect(() => {
    if (!state.message) return;
    const timer = window.setTimeout(() => setState((prev) => ({ ...prev, message: "" })), state.durationMs);
    return () => window.clearTimeout(timer);
  }, [state.message, state.durationMs]);

  const value = React.useMemo<ToastContextValue>(
    () => ({ toast: state.message, toastTone: state.tone, setToast }),
    [state.message, state.tone, setToast],
  );
  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast message={state.message} tone={state.tone} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
