import React from "react";
import type { AuthSession, CaptureDraft } from "../appTypes";
import type { Screen } from "../types";
import { Button, Card } from "../ui";
import { CaptureActions } from "./CaptureActions";

export function Shell({
  screen,
  children,
  onNavigate,
  onCapture,
  auth,
  onLogout,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  auth: AuthSession;
  onLogout: () => void;
}) {
  const displayName = auth.user.displayName || auth.user.email;
  const role = auth.memberships[0]?.role || auth.user.persona || "user";
  const initials = displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "A";

  return (
    <main className="phone-shell">
      <header className="topbar">
        <div className="topbar-left">
          <nav className="top-nav" aria-label="Primary">
            <button className={screen === "active-session" ? "active" : ""} onClick={() => onNavigate("active-session")} type="button">
              Active Session
            </button>
            <button className={screen === "patients" ? "active" : ""} onClick={() => onNavigate("patients")} type="button">
              Patients
            </button>
            <button className={screen === "search" ? "active" : ""} onClick={() => onNavigate("search")} type="button">
              Search
            </button>
          </nav>
        </div>
        <strong className="topbar-brand">AesMem</strong>
        <details className="user-menu">
          <summary>
            <span className="user-menu-avatar" aria-hidden="true">{initials}</span>
            <span className="user-menu-label">
              <span>{displayName}</span>
              <small>{role}</small>
            </span>
          </summary>
          <div className="user-menu-panel">
            <div>
              <span>Profile</span>
              <strong>{displayName}</strong>
              <span>{role} - {auth.tenant.name}</span>
            </div>
            <Button onClick={onLogout} size="sm" variant="secondary">
              Logout
            </Button>
          </div>
        </details>
      </header>
      {children}
      <CaptureActions compact onAction={onCapture} />
      <footer className="app-version">MVP v2</footer>
    </main>
  );
}

export function SyncSafetyBanner({
  pendingCount,
  syncing,
  onClearLocal,
  onRetry,
}: {
  pendingCount: number;
  syncing: boolean;
  onClearLocal: () => void;
  onRetry: () => void;
}) {
  if (!pendingCount) return null;

  return (
    <Card className="sync-warning">
      <div>
        <strong>{pendingCount} capture{pendingCount === 1 ? "" : "s"} saved on this device</strong>
        <p>Keep this browser data until transfer is complete. Closing or clearing site data could lose unsynced captures.</p>
      </div>
      <div className="sync-actions">
        <Button disabled={syncing} onClick={onRetry} size="sm" variant="secondary">
          {syncing ? "Syncing" : "Retry now"}
        </Button>
        <Button disabled={syncing} onClick={onClearLocal} size="sm" variant="ghost">
          Clear local
        </Button>
      </div>
    </Card>
  );
}
