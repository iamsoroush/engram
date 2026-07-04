import React from "react";
import { currentUserRoles, isAdmin, isStaffWriter } from "../../shared/lib/multiseat";
import { useAuth } from "./AuthProvider";

// Seam A3 (frontend-refactor plan §2). One home for "what can this tenant/user do", derived from
// tier + role, so the Basic/Pro fork stops living as scattered `tier === "basic"` checks and
// `onFetchX = isPro ? cb : undefined` prop-gating in the App god-component. Feature affordances are
// named by capability (not by tier) so the Basic/Pro-convergence epic can flip a gate in one place;
// they currently all resolve to `isPro`, which is fine — the point is the semantic seam.

export type Capabilities = {
  tier: string | undefined;
  isPro: boolean;
  isBasic: boolean;
  /** Post-session patient Q&A (inbox badge, inbox screen, per-patient channel). Pro-gated. */
  canUseQa: boolean;
  /** Smart lists tab + lot ledger/recall. Pro-gated. */
  canUseSmartLists: boolean;
  /** The Pro curated pre-visit brief (line-up card) on the session context. */
  canUseCuratedBrief: boolean;
  /** The Basic-only ghost-photo overlay for the next shot. */
  showGhostPhoto: boolean;
  isStaffWriter: boolean;
  isAdmin: boolean;
  roles: string[];
};

const CapabilitiesContext = React.createContext<Capabilities | null>(null);

export function CapabilitiesProvider({ children }: { children: React.ReactNode }) {
  const { auth } = useAuth();
  const value = React.useMemo<Capabilities>(() => {
    const tier = auth?.tenant.tier;
    const isPro = Boolean(auth) && tier !== "basic";
    const isBasic = tier === "basic";
    return {
      tier,
      isPro,
      isBasic,
      canUseQa: isPro,
      canUseSmartLists: isPro,
      canUseCuratedBrief: isPro,
      showGhostPhoto: isBasic,
      isStaffWriter: isStaffWriter(auth),
      isAdmin: isAdmin(auth),
      roles: currentUserRoles(auth),
    };
  }, [auth]);
  return <CapabilitiesContext.Provider value={value}>{children}</CapabilitiesContext.Provider>;
}

export function useCapabilities(): Capabilities {
  const ctx = React.useContext(CapabilitiesContext);
  if (!ctx) throw new Error("useCapabilities must be used within CapabilitiesProvider");
  return ctx;
}
