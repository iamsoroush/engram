import React from "react";
import { Toast } from "../../shared/ui/primitives";

// Seam A4 (frontend-refactor plan §2). A single transient toast, owned by a provider so it no longer
// threads through props or lives as App state — both the app body and the session store raise toasts
// via `useToast().setToast`. The provider renders the toast + owns its auto-dismiss timer.

type ToastContextValue = {
  toast: string;
  setToast: (message: string) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = React.useState("");

  React.useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const value = React.useMemo<ToastContextValue>(() => ({ toast, setToast }), [toast]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast message={toast} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
