import React from "react";
import type { AuthSession, CaptureDraft, SyncHealth } from "../../domain/appTypes";
import type { Screen } from "../../domain/types";
import { Button } from "../../shared/ui/primitives";
import { CaptureActions } from "../capture/components/CaptureActions";

export function Shell({
  screen,
  children,
  onNavigate,
  onCapture,
  captureContextLabel,
  auth,
  syncHealth,
  onClearLocal,
  onLogout,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  captureContextLabel?: string;
  auth: AuthSession;
  syncHealth: SyncHealth;
  onClearLocal?: () => void;
  onLogout: () => void;
}) {
  const displayName = auth.user.displayName || auth.user.email;
  const role = auth.memberships[0]?.role || auth.user.persona || "user";
  const isAdmin = auth.memberships.some((membership) => membership.role === "admin") || auth.user.persona === "admin";
  const isOffline = !syncHealth.online;
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
              {isAdmin && onClearLocal ? (
                <details className="debug-settings">
                  <summary>Debug settings</summary>
                  <Button onClick={onClearLocal} size="sm" variant="ghost">
                    Clear local capture cache
                  </Button>
                </details>
              ) : null}
              <Button onClick={onLogout} size="sm" variant="secondary">
                Logout
              </Button>
            </div>
          </details>
        </div>
      </header>
      {isOffline ? <p className="global-offline-status">Offline · Captures are saved on this device</p> : null}
      {children}
      <CaptureActions compact contextLabel={isOffline ? "Saving on this device" : captureContextLabel} onAction={onCapture} />
      <footer className="app-version">MVP v2</footer>
    </main>
  );
}
