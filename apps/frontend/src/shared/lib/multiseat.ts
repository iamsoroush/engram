// Multi-seat (E9) client helpers: author attribution + viewer-relative session permissions.
//
// These mirror the backend's `services.permissions` so the UI can show "by X", "read-only", and
// owner-only affordances. The BACKEND still enforces every write (403); this is display-only.

import type { AuthSession, RolePermissions, RolePreset } from "../../domain/appTypes";
import type { Attribution, CaptureSession } from "../../domain/types";

const RANK: Record<string, number> = { contribute: 0, reassign: 1, full: 2 };

/** The current user's active roles in the signed-in tenant (membership first, persona fallback). */
export function currentUserRoles(auth: AuthSession | null): string[] {
  if (!auth) return [];
  const roles = auth.memberships.filter((m) => m.tenantId === auth.tenant.id).map((m) => m.role);
  if (roles.length) return roles;
  return auth.user.persona ? [String(auth.user.persona)] : [];
}

/** Only doctors/assistants may write sessions at the route level; admins manage, patients can't. */
export function isStaffWriter(auth: AuthSession | null): boolean {
  const roles = currentUserRoles(auth);
  return roles.includes("doctor") || roles.includes("assistant");
}

export function isAdmin(auth: AuthSession | null): boolean {
  return currentUserRoles(auth).includes("admin");
}

/** The highest preset the user's roles grant as a *non-owner* (admin → full). */
export function rolePermissionLevel(auth: AuthSession | null): RolePreset {
  const roles = currentUserRoles(auth);
  if (roles.includes("admin")) return "full";
  const perms: RolePermissions = auth?.tenant.rolePermissions || {};
  let level = "contribute";
  for (const role of roles) {
    const preset = perms[role];
    if (typeof preset === "string" && RANK[preset] !== undefined && RANK[preset] > RANK[level]) level = preset;
  }
  return level as RolePreset;
}

export function sessionOwnerId(session: Pick<CaptureSession, "ownerUserId" | "createdByUserId">): string | null {
  return session.ownerUserId || session.createdByUserId || null;
}

export function isSessionOwner(session: Pick<CaptureSession, "ownerUserId" | "createdByUserId">, auth: AuthSession | null): boolean {
  const owner = sessionOwnerId(session);
  return Boolean(auth && owner && owner === auth.user.id);
}

/** AES-902: can the viewer edit/curate this session? Owner → yes; else needs the "full" preset.
 *  Also requires being a staff writer, mirroring the backend's staff-only write routes. */
export function canEditSession(
  session: Pick<CaptureSession, "ownerUserId" | "createdByUserId">,
  auth: AuthSession | null,
): boolean {
  if (!isStaffWriter(auth)) return false;
  if (isSessionOwner(session, auth)) return true;
  return RANK[rolePermissionLevel(auth)] >= RANK.full;
}

/** AES-902: should this visit render read-only for the viewer? Only when it has a known owner who
 *  is someone else AND the viewer's role can't edit it. A local/unsynced session (no owner yet) or
 *  the viewer's own session is always editable — never block the capturer's own work. */
export function isSessionReadOnly(
  session: Pick<CaptureSession, "ownerUserId" | "createdByUserId">,
  auth: AuthSession | null,
): boolean {
  const owner = sessionOwnerId(session);
  if (!owner || isSessionOwner(session, auth)) return false;
  return !canEditSession(session, auth);
}

/** Can the viewer reassign this (already-assigned) visit to a different patient? */
export function canReassignSession(
  session: Pick<CaptureSession, "ownerUserId" | "createdByUserId">,
  auth: AuthSession | null,
): boolean {
  if (!isStaffWriter(auth)) return false;
  if (isSessionOwner(session, auth)) return true;
  return RANK[rolePermissionLevel(auth)] >= RANK.reassign;
}

/** "Dr. Demo" / "you" / "" — the author's name (AES-901). Pass the viewer's id to get "you". */
export function attributionName(attribution: Attribution | null | undefined, currentUserId?: string | null): string {
  if (!attribution) return "";
  if (currentUserId && attribution.userId === currentUserId) return "you";
  return attribution.displayName || "another clinician";
}

/** "by Dr. Demo · 14:32" — attribution + an optional time label. */
export function attributionWithTime(
  attribution: Attribution | null | undefined,
  time: string | null | undefined,
  currentUserId?: string | null,
): string {
  const name = attributionName(attribution, currentUserId);
  const who = name ? `by ${name}` : "";
  if (who && time) return `${who} · ${time}`;
  return who || time || "";
}
