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
  const navigationItems: Array<{ screen: Screen; label: string; icon: React.ReactNode }> = [
    { screen: "active-session", label: "Active Session", icon: <ActiveSessionNavIcon /> },
    { screen: "patients", label: "Clinical Memory", icon: <ClinicalMemoryNavIcon /> },
    { screen: "search", label: "Search", icon: <SearchNavIcon /> },
  ];

  return (
    <main className="phone-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-left">
            <nav className="app-navigator" aria-label="Primary">
              {navigationItems.map((item) => (
                <button
                  aria-current={screen === item.screen ? "page" : undefined}
                  aria-label={item.label}
                  className={screen === item.screen ? "active" : ""}
                  key={item.screen}
                  onClick={() => onNavigate(item.screen)}
                  title={item.label}
                  type="button"
                >
                  {item.icon}
                </button>
              ))}
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

function ActiveSessionNavIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M8 4.75h8a2.25 2.25 0 0 1 2.25 2.25v10A2.25 2.25 0 0 1 16 19.25H8A2.25 2.25 0 0 1 5.75 17V7A2.25 2.25 0 0 1 8 4.75Z" />
      <path d="M9 9.25h6M9 12h4.4" />
      <path d="m13.75 16.25 1.35-1.35 1.1 1.1 2.05-2.3" />
    </svg>
  );
}

function ClinicalMemoryNavIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M6.75 6.25h3.9l1.55 1.7h5.05A2.25 2.25 0 0 1 19.5 10.2v6.55A2.25 2.25 0 0 1 17.25 19H6.75a2.25 2.25 0 0 1-2.25-2.25V8.5a2.25 2.25 0 0 1 2.25-2.25Z" />
      <path d="M9.25 14.25a2.75 2.75 0 0 1 5.5 0" />
      <path d="M12 12.15a1.45 1.45 0 1 0 0-2.9 1.45 1.45 0 0 0 0 2.9Z" />
    </svg>
  );
}

function SearchNavIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M16.8 16.8 20 20" />
      <path d="M18 11.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z" />
    </svg>
  );
}
