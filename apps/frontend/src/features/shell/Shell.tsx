import React from "react";
import type { AttentionCounts, AttentionResponse, AuthSession, CaptureDraft, SyncHealth } from "../../domain/appTypes";
import type { Screen } from "../../domain/types";
import { useT } from "../../shared/i18n";
import { CaptureActions } from "../capture/components/CaptureActions";
import { attentionBadgeCount, hasAttention, HIGHEST_TIER_TONE } from "../memory/components/attentionModel";
import "../memory/attention.css";

export function Shell({
  screen,
  children,
  onNavigate,
  onOpenFinder,
  onCapture,
  captureContextLabel,
  auth,
  syncHealth,
  onLogout,
  onReplayGuide,
  attentionCounts = null,
  attentionHighestTier = null,
  onOpenAttention,
  qaPendingCount = 0,
  qaUrgent = false,
}: {
  screen: Screen;
  children: React.ReactNode;
  onNavigate: (screen: Screen) => void;
  /** Open the unified finder overlay (the top-bar search affordance + desktop ⌘K launcher). Absent on
   *  surfaces without the finder (e.g. therapy), where the search affordance is simply not rendered. */
  onOpenFinder?: () => void;
  onCapture: (kind: CaptureDraft["kind"]) => void;
  captureContextLabel?: string;
  auth: AuthSession;
  syncHealth: SyncHealth;
  onLogout: () => void;
  onReplayGuide?: () => void;
  /** Unified attention roll-up counts for the top-bar indicator (AES-1003); null while unknown. */
  attentionCounts?: AttentionCounts | null;
  attentionHighestTier?: AttentionResponse["highestTier"];
  /** Opens the Close-the-day sweep (the Attention tab of Clinical Memory). */
  onOpenAttention?: () => void;
  /** Pending Q&A threads (scoped like the inbox) for the glanceable Q&A badge (AES-1801); 0 hides it. */
  qaPendingCount?: number;
  /** Any pending question tripped a red flag — the badge turns to the danger tone. */
  qaUrgent?: boolean;
}) {
  const t = useT();
  const menuRef = React.useRef<HTMLDetailsElement>(null);
  const displayName = auth.user.displayName || auth.user.email;
  // The role for the ACTIVE tenant (a cross-clinic user has a membership per clinic).
  const activeMembership = auth.memberships.find((membership) => membership.tenantId === auth.tenant.id);
  const role = activeMembership?.role || auth.user.persona || "user";
  // Localized role label (full enum is in the catalog). Fall back to the raw role only for an unknown
  // value — every reachable role has a key, so fa never shows raw English.
  const roleKey = `role.${role}`;
  const roleLabel = t(roleKey) === roleKey ? role : t(roleKey);
  // Member management is owner/admin only (the backend enforces it; we also hide the entry).
  const canManageTeam = activeMembership?.role === "owner" || activeMembership?.role === "admin";
  // Offer a clinic switcher only to users who belong to more than one clinic.
  const multiClinic = new Set(auth.memberships.map((membership) => membership.tenantId)).size > 1;
  // Account / utility pages have no capture context — the capture bar would overlap their content.
  // The Q&A inbox likewise hides it: capturing has no meaning there, and it would clash with the
  // per-reply voice-edit mic (AES-1801). Q&A gets its own bottom Inbox|Library bar instead.
  const isAccountScreen =
    screen === "settings" || screen === "profile" || screen === "team" || screen === "insights" || screen === "plan" || screen === "switch-clinic";
  const hideCaptureBar = isAccountScreen || screen === "qa-inbox";
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
  // The unified Attention indicator (AES-1003) merges the old needs-input + Q&A badges into one
  // severity-coloured count. Surface-by-exception: it renders only when something is open (an empty
  // top bar means the checks ran and passed). The "to-do" number is confirm + messages; a safety
  // flag with nothing else to confirm shows a bare red dot (shown, never counted).
  const attentionCount = attentionCounts ? attentionBadgeCount(attentionCounts) : 0;
  const showAttention = Boolean(onOpenAttention && attentionCounts && hasAttention(attentionCounts));
  const attentionTone = attentionHighestTier ? HIGHEST_TIER_TONE[attentionHighestTier] : "amber";
  // The clinical encounter is a "visit" everywhere in aesthetics chrome; therapy keeps "session".
  // Pick the primary-nav label by vertical so it matches the rest of the surface's vocabulary.
  const encounterNavKey = auth.tenant.vertical === "therapy" ? "nav.activeSession" : "nav.activeVisit";
  const navigationItems: Array<{ screen: Screen; label: string; shortLabel: string; icon: React.ReactNode }> = [
    { screen: "active-session", label: t(encounterNavKey), shortLabel: t(`${encounterNavKey}.short`), icon: <ActiveSessionNavIcon /> },
    { screen: "patients", label: t("nav.memory"), shortLabel: t("nav.memory.short"), icon: <ClinicalMemoryNavIcon /> },
  ];

  return (
    <main className="phone-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="topbar-left">
            <nav className="app-navigator" aria-label={t("nav.primaryAria")}>
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
                  <span className="nav-label">{item.shortLabel}</span>
                </button>
              ))}
            </nav>
            {/* The unified finder (AES-1201): opens the app-wide finder overlay — mobile-first full-screen
                sheet; desktop also has a ⌘K launcher. Not a screen anymore, so no `aria-current`. Only
                rendered where a finder is wired (aesthetics), not on the therapy surface. */}
            {onOpenFinder ? (
              <button
                aria-label={t("nav.search")}
                className="app-search-button"
                onClick={onOpenFinder}
                title={t("nav.search")}
                type="button"
              >
                <SearchNavIcon />
              </button>
            ) : null}
            {isPro ? (
              <button
                aria-current={screen === "qa-inbox" ? "page" : undefined}
                aria-label={
                  qaPendingCount
                    ? t(qaUrgent ? "nav.qaInbox.urgent" : "nav.qaInbox.count", { n: qaPendingCount })
                    : t("nav.qaInbox")
                }
                className={`app-search-button app-qa-button ${screen === "qa-inbox" ? "active" : ""}`}
                onClick={() => onNavigate("qa-inbox")}
                title={t("nav.qaInbox")}
                type="button"
              >
                {/* Messages earn their own glanceable badge again (AES-1801 — a deliberate partial-revert
                    of the E16 merge; the unified bell keeps its merged count). A red-flagged question
                    turns the badge to the danger tone. */}
                <QaInboxNavIcon />
                {qaPendingCount ? (
                  <span
                    className={`app-qa-badge ${qaUrgent ? "tone-urgent" : ""}`}
                    data-testid="qa-pending-badge"
                    aria-hidden="true"
                  >
                    {qaPendingCount > 9 ? "9+" : qaPendingCount}
                  </span>
                ) : null}
              </button>
            ) : null}
            {showAttention ? (
              <button
                aria-label={attentionCount ? t("nav.attention.count", { n: attentionCount }) : t("nav.attention.safety")}
                className="app-search-button app-attention-button"
                onClick={onOpenAttention}
                title={t("nav.attention")}
                type="button"
              >
                <AttentionBellIcon />
                {attentionCount ? (
                  <span className={`app-attention-badge tone-${attentionTone}`} aria-hidden="true">
                    {attentionCount > 9 ? "9+" : attentionCount}
                  </span>
                ) : (
                  <span className="app-attention-dot" aria-hidden="true" />
                )}
              </button>
            ) : null}
          </div>
          {/* Brand wordmark — an intentional Latin token; bidi-isolate so it can't reorder against
              adjacent Persian chrome in the RTL topbar. */}
          <strong className="topbar-brand"><bdi>{t("brand.name")}</bdi></strong>
          <details className="user-menu" ref={menuRef}>
            <summary>
              <span className="user-menu-avatar" aria-hidden="true">{initials}</span>
              <span className="user-menu-label">
                <span>{displayName}</span>
                <small>{roleLabel}</small>
              </span>
            </summary>
            <div className="user-menu-panel">
              <div className="user-menu-identity">
                <span className="user-menu-avatar lg" aria-hidden="true">{initials}</span>
                <span className="user-menu-identity-text">
                  <strong>{displayName}</strong>
                  <small>{roleLabel} · {auth.tenant.name}</small>
                  {/* Tier name is an intentional Latin token (matches the public surface); bidi-isolate it. */}
                  <span className={`tier-pill ${isPro ? "pro" : "basic"}`}><bdi>{isPro ? "Pro" : "Basic"}</bdi></span>
                </span>
              </div>
              <button className="user-menu-item" onClick={() => goTo("profile")} type="button">
                <ProfileMenuIcon />
                {t("menu.profile")}
              </button>
              <button className="user-menu-item" onClick={() => goTo("settings")} type="button">
                <SettingsMenuIcon />
                {t("menu.settings")}
              </button>
              {/* Owner/admin clinic-management actions grouped under a labelled "Clinic" section, so
                  they read as clinic-level tools distinct from the personal identity actions above. */}
              {canManageTeam ? (
                <div className="user-menu-section-label" role="presentation">{t("menu.clinicSection")}</div>
              ) : null}
              {canManageTeam ? (
                <button className="user-menu-item" onClick={() => goTo("insights")} type="button">
                  <InsightsMenuIcon />
                  {t("menu.insights")}
                </button>
              ) : null}
              {canManageTeam ? (
                <button className="user-menu-item" onClick={() => goTo("team")} type="button">
                  <TeamMenuIcon />
                  {t("menu.team")}
                </button>
              ) : null}
              {canManageTeam ? (
                <button className="user-menu-item" onClick={() => goTo("plan")} type="button">
                  <PlanMenuIcon />
                  {t("menu.plan")}
                </button>
              ) : null}
              {multiClinic ? (
                <button className="user-menu-item" onClick={() => goTo("switch-clinic")} type="button">
                  <SwitchClinicMenuIcon />
                  {t("menu.switchClinic")}
                </button>
              ) : null}
              {onReplayGuide ? (
                <button
                  className="user-menu-item"
                  onClick={() => {
                    closeMenu();
                    onReplayGuide();
                  }}
                  type="button"
                >
                  <GuideMenuIcon />
                  {t("menu.replayGuide")}
                </button>
              ) : null}
              <button className="user-menu-item user-menu-item-danger" onClick={onLogout} type="button">
                <LogoutMenuIcon />
                {t("menu.logout")}
              </button>
            </div>
          </details>
        </div>
      </header>
      {isOffline ? <p className="global-offline-status">{t("shell.offline")}</p> : null}
      {children}
      {hideCaptureBar ? null : (
        <CaptureActions compact contextLabel={isOffline ? t("shell.savingOnDevice") : captureContextLabel} onAction={onCapture} tier={auth.tenant.tier} />
      )}
      <footer className="app-version">{t("shell.version")}</footer>
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

function InsightsMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-4M12 16V8M16 16v-6" />
    </svg>
  );
}

function TeamMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <path d="M16 5.5a3 3 0 0 1 0 5.8" />
      <path d="M17 13.2a5.5 5.5 0 0 1 3.5 5.1" />
    </svg>
  );
}

function PlanMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M5 7h14v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7Z" />
      <path d="M9 4.5h6V7H9z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function SwitchClinicMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M4 8h13l-3-3" />
      <path d="M20 16H7l3 3" />
    </svg>
  );
}

function GuideMenuIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.7-.9 1.4v.4" />
      <path d="M12 16.5h.01" />
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

function AttentionBellIcon() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="M12 4.5a4.75 4.75 0 0 0-4.75 4.75c0 4-1.5 5.25-2.25 6h14c-.75-.75-2.25-2-2.25-6A4.75 4.75 0 0 0 12 4.5Z" />
      <path d="M10 18.5a2 2 0 0 0 4 0" />
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
