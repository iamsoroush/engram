import React from "react";
import type { AuthSession, CaptureDraft, SyncHealth } from "../../domain/appTypes";
import type { Screen } from "../../domain/types";
import { Button, Card } from "../../shared/ui/primitives";
import { CaptureActions } from "../capture/components/CaptureActions";

export function Shell({
  screen,
  children,
  onNavigate,
  onCapture,
  captureContextLabel,
  auth,
  onLogout,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  captureContextLabel?: string;
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
  const navigationItems: Array<{ screen: Screen; label: string }> = [
    { screen: "active-session", label: "Active Session" },
    { screen: "patients", label: "Clinical Memory" },
    { screen: "search", label: "Search" },
  ];

  return (
    <main className="phone-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-left">
            <details className="app-menu">
              <summary aria-label="Open navigation">
                <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                  <path d="M4 6.5h16M4 12h16M4 17.5h16" />
                </svg>
              </summary>
              <nav className="app-menu-panel" aria-label="Primary">
                {navigationItems.map((item) => (
                  <button
                    className={screen === item.screen ? "active" : ""}
                    key={item.screen}
                    onClick={(event) => {
                      onNavigate(item.screen);
                      const menu = event.currentTarget.closest("details");
                      if (menu) menu.open = false;
                    }}
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
              </nav>
            </details>
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
        </div>
      </header>
      {children}
      <CaptureActions compact contextLabel={captureContextLabel} onAction={onCapture} />
      <footer className="app-version">MVP v2</footer>
    </main>
  );
}

export function SyncSafetyBanner({
  syncHealth,
  onClearLocal,
  onRetry,
}: {
  syncHealth: SyncHealth;
  onClearLocal: () => void;
  onRetry: () => void;
}) {
  const pendingCount = syncHealth.pendingCaptures + syncHealth.pendingOperations;
  if (!pendingCount && syncHealth.online && syncHealth.backendReachable !== false) return null;

  const title = !syncHealth.online
    ? "Offline - saved on this device"
    : syncHealth.syncing
      ? "Syncing"
      : syncHealth.backendReachable === false || syncHealth.lastError
        ? "Needs retry"
        : "AI organizing when available";
  const detail = pendingCount
    ? `${syncHealth.pendingCaptures} capture${syncHealth.pendingCaptures === 1 ? "" : "s"} and ${syncHealth.pendingOperations} local change${syncHealth.pendingOperations === 1 ? "" : "s"} are waiting for safe transfer.`
    : "Backend is not reachable right now. Recent local work remains available on this device.";

  return (
    <Card className="sync-warning">
      <div>
        <strong>{title}</strong>
        <p>{detail} Keep this browser data until transfer is complete.</p>
      </div>
      <div className="sync-actions">
        <Button disabled={syncHealth.syncing || !syncHealth.online} onClick={onRetry} size="sm" variant="secondary">
          {syncHealth.syncing ? "Syncing" : "Retry now"}
        </Button>
        <Button disabled={syncHealth.syncing || !pendingCount} onClick={onClearLocal} size="sm" variant="ghost">
          Clear local
        </Button>
      </div>
    </Card>
  );
}
