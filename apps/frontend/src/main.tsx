import React from "react";
import ReactDOM from "react-dom/client";

const root = ReactDOM.createRoot(document.getElementById("root")!);

// Top-level route split. `/share/{token}` is the PUBLIC patient surface — a separate page area with
// no login, no clinic state, and (by design) without the clinic stylesheet. Everything else is the
// clinic app. Imports are dynamic so the public page never pulls in the clinic bundle/styles, and the
// clinic app never pulls in the patient-surface code.
const shareMatch = window.location.pathname.match(/^\/share\/([^/]+)\/?$/);

if (shareMatch) {
  void import("./features/patient-surface/PatientSharePage").then(({ PatientSharePage }) => {
    root.render(
      <React.StrictMode>
        <PatientSharePage token={decodeURIComponent(shareMatch[1])} />
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
