import React from "react";
import type { AuthSession, CaptureDraft, SyncHealth } from "../../domain/appTypes";
import type { Screen } from "../../domain/types";
import { CaptureActions } from "../capture/components/CaptureActions";

export function Shell({
  screen,
  children,
  onNavigate,
  onCapture,
  captureContextLabel,
  auth,
  syncHealth,
  onLogout,
  qaPendingCount = 0,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  captureContextLabel?: string;
  auth: AuthSession;
  syncHealth: SyncHealth;
  onLogout: () => void;
  qaPendingCount?: number;
}) {
  const menuRef = React.useRef<HTMLDetailsElement>(null);
  const displayName = auth.user.displayName || auth.user.email;
  const role = auth.memberships[0]?.role || auth.user.persona || "user";
  const isOffline = !syncHealth.online;
  const closeMenu = () => menuRef.current?.removeAttribute("open");
  const goTo = (target: Screen) => {
    closeMenu();
    onNavigate(target);
  };
  const initials = displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "A";
  // The primary navigator stays the two workspaces (Session, Memory). Q&A is a triage *inbox*, not a
  // workspace — it lives as an icon + pending badge beside Search (Pro only), so the pill never crowds.
  const isPro = auth.tenant.tier !== "basic";
  const navigationItems: Array<{ screen: Screen; label: string; shortLabel: string; icon: React.ReactNode }> = [
    { screen: "active-session", label: "Active Session", shortLabel: "Session", icon: <ActiveSessionNavIcon /> },
    { screen: "patients", label: "Clinical Memory", shortLabel: "Memory", icon: <ClinicalMemoryNavIcon /> },
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
                  className={screen === item.screen ? "active" : ""}
                  key={item.screen}
                  onClick={() => onNavigate(item.screen)}
                  title={item.label}
                  type="button"
                >
                  <span aria-hidden="true">{item.icon}</span>
                  <span>{item.shortLabel}</span>
                </button>
              ))}
            </nav>
            <button
              aria-current={screen === "search" ? "page" : undefined}
              aria-label="Search"
              className={`app-search-button ${screen === "search" ? "active" : ""}`}
              onClick={() => onNavigate("search")}
              title="Search"
              type="button"
            >
              <SearchNavIcon />
            </button>
            {isPro ? (
              <button
                aria-current={screen === "qa-inbox" ? "page" : undefined}
                aria-label={qaPendingCount ? `Q&A inbox, ${qaPendingCount} waiting` : "Q&A inbox"}
                className={`app-search-button app-qa-button ${screen === "qa-inbox" ? "active" : ""}`}
                onClick={() => onNavigate("qa-inbox")}
                title="Q&A inbox"
                type="button"
              >
                <QaInboxNavIcon />
                {qaPendingCount ? (
                  <span className="app-qa-badge" aria-hidden="true">
                    {qaPendingCount > 9 ? "9+" : qaPendingCount}
                  </span>
                ) : null}
              </button>
            ) : null}
          </div>
          <strong className="topbar-brand">Memara</strong>
          <details className="user-menu" ref={menuRef}>
            <summary>
              <span className="user-menu-avatar" aria-hidden="true">{initials}</span>
              <span className="user-menu-label">
                <span>{displayName}</span>
                <small>{role}</small>
              </span>
            </summary>
            <div className="user-menu-panel">
              <div className="user-menu-identity">
                <span className="user-menu-avatar lg" aria-hidden="true">{initials}</span>
                <span className="user-menu-identity-text">
                  <strong>{displayName}</strong>
                  <small>{role} · {auth.tenant.name}</small>
                </span>
              </div>
              <button className="user-menu-item" onClick={() => goTo("profile")} type="button">
                <ProfileMenuIcon />
                Profile
              </button>
              <button className="user-menu-item" onClick={() => goTo("settings")} type="button">
                <SettingsMenuIcon />
                Settings
              </button>
              <button className="user-menu-item user-menu-item-danger" onClick={onLogout} type="button">
                <LogoutMenuIcon />
                Logout
              </button>
            </div>
          </details>
        </div>
      </header>
      {isOffline ? <p className="global-offline-status">Offline · Captures are saved on this device</p> : null}
      {children}
      <CaptureActions compact contextLabel={isOffline ? "Saving on this device" : captureContextLabel} onAction={onCapture} tier={auth.tenant.tier} />
      <footer className="app-version">MVP v2</footer>
    </main>
  );
}

function ProfileMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="12" cy="8.5" r="3.25" />
      <path d="M5.5 19a6.5 6.5 0 0 1 13 0" />
    </svg>
  );
}

function SettingsMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3.5v2M12 18.5v2M4.7 7.5l1.7 1M17.6 15.5l1.7 1M4.7 16.5l1.7-1M17.6 8.5l1.7-1" />
    </svg>
  );
}

function LogoutMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M14 8.5V6.5A1.5 1.5 0 0 0 12.5 5H6.5A1.5 1.5 0 0 0 5 6.5v11A1.5 1.5 0 0 0 6.5 19h6a1.5 1.5 0 0 0 1.5-1.5v-2" />
      <path d="M10 12h9M16 9l3 3-3 3" />
    </svg>
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

function QaInboxNavIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M5.75 5.75h12.5a1.5 1.5 0 0 1 1.5 1.5v7.5a1.5 1.5 0 0 1-1.5 1.5H10l-3.5 3v-3H5.75a1.5 1.5 0 0 1-1.5-1.5v-7.5a1.5 1.5 0 0 1 1.5-1.5Z" />
      <path d="M9 10.25h6M9 12.75h3.5" />
    </svg>
  );
}
