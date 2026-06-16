import React from "react";
import ReactDOM from "react-dom/client";

import { initSentry } from "./shared/lib/sentry";

// Error tracking — initialized once for every route branch (clinic, share, qa). No-op when
// VITE_SENTRY_DSN is empty, so dev / unconfigured builds are unaffected.
initSentry();

const root = ReactDOM.createRoot(document.getElementById("root")!);

// Top-level route split. `/share/{token}` is the PUBLIC patient surface — a separate page area with
// no login, no clinic state, and (by design) without the clinic stylesheet. Everything else is the
// clinic app. Imports are dynamic so the public page never pulls in the clinic bundle/styles, and the
// clinic app never pulls in the patient-surface code.
const shareMatch = window.location.pathname.match(/^\/share\/([^/]+)\/?$/);
const qaMatch = window.location.pathname.match(/^\/qa\/([^/]+)\/?$/);

if (shareMatch) {
  void import("./features/patient-surface/PatientSharePage").then(({ PatientSharePage }) => {
    root.render(
      <React.StrictMode>
        <PatientSharePage token={decodeURIComponent(shareMatch[1])} />
      </React.StrictMode>,
    );
  });
} else if (qaMatch) {
  // `/qa/{token}` — the PUBLIC post-session Q&A surface (AES-402). Same isolated, login-free area as
  // the share page; never pulls in the clinic bundle/styles.
  void import("./features/patient-surface/PatientQaPage").then(({ PatientQaPage }) => {
    root.render(
      <React.StrictMode>
        <PatientQaPage token={decodeURIComponent(qaMatch[1])} />
      </React.StrictMode>,
    );
  });
} else {
  void Promise.all([import("./styles.css"), import("./app/App")]).then(([, { App }]) => {
    root.render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
  });
}
