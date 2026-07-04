import React from "react";
import type { CaptureSession, Screen } from "../../domain/types";
import type { ClinicalMemoryReturnContext } from "../../features/memory/components/MemoryScreens";
import { resetBackLevels } from "../../shared/lib/backStack";
import { replaceScreenLocation, screenFromLocation } from "../navigation";
import { useSessionActions } from "./SessionStoreProvider";

// Seam D (frontend-refactor plan §2, increment 7). The navigation + history surface lifted out of the
// App god-component: the top-level `screen`, `navigateScreen` (which owns the hash sync + back-stack
// reset), and the hand-rolled return-context (Clinical-Memory return, the back-to-visit round-trip
// stash, the account-page return target). In-screen levels (patient file, smart-list drill-in,
// historical review) keep their existing synthetic-history mechanism in `shared/lib/backStack`; this
// seam is the home the deferred UX epics (unified finder, close-the-day) add routes to instead of
// stacking more return-context state on App.
//
// Navigation race — codified as a RULE here: an explicit location hash present at FIRST load always
// wins over restore-last-screen. We capture whether the initial URL carried a hash ONCE at mount
// (a ref, so it can't drift if a later navigate replaceState()s the hash) and expose
// `shouldRestoreLastScreen`; the workspace-restore in App only applies the persisted screen when no
// explicit hash was present. Reading a live `window.location.hash` at async-hydrate time was the
// source of the old visual-suite flake (a full reload raced restore against the URL hash).

export type NavigationContextValue = {
  screen: Screen;
  /** Hard top-level screen switch: resets in-screen back levels, replaces the hash, clears the
   *  selected historical session when landing on the capture screen. */
  navigateScreen: (screen: Screen) => void;
  /** True only when the initial load carried NO explicit hash — the sole condition under which
   *  restore-last-screen may override the default screen (the navigation-race rule). */
  shouldRestoreLastScreen: boolean;
  clinicalMemoryReturnContext: ClinicalMemoryReturnContext | null;
  setClinicalMemoryReturnContext: React.Dispatch<React.SetStateAction<ClinicalMemoryReturnContext | null>>;
  /** The in-progress capture visit stashed when jumping to a patient timeline, so "back to this visit"
   *  restores it exactly. */
  captureReturnSession: CaptureSession | null;
  setCaptureReturnSession: React.Dispatch<React.SetStateAction<CaptureSession | null>>;
  /** Where an account/utility page (settings, profile, team…) returns to on Back. */
  accountReturnRef: React.MutableRefObject<Screen>;
};

const NavigationContext = React.createContext<NavigationContextValue | null>(null);

export function NavigationProvider({ children }: { children: React.ReactNode }) {
  const { setSelectedSessionId } = useSessionActions();
  const [screen, setScreen] = React.useState<Screen>(() => screenFromLocation());
  const [clinicalMemoryReturnContext, setClinicalMemoryReturnContext] = React.useState<ClinicalMemoryReturnContext | null>(null);
  const [captureReturnSession, setCaptureReturnSession] = React.useState<CaptureSession | null>(null);
  const accountReturnRef = React.useRef<Screen>("active-session");
  // Captured ONCE at mount — before any navigate can replaceState the hash — so the rule is race-proof.
  const hadExplicitInitialHashRef = React.useRef(typeof window !== "undefined" && Boolean(window.location.hash));

  const navigateScreen = React.useCallback(
    (nextScreen: Screen) => {
      // A hard screen switch replaceState()s the current entry (possibly a sub-level's synthetic one)
      // and unmounts any open in-screen level, so drop the back-stack first (see backStack.ts).
      resetBackLevels();
      setScreen(nextScreen);
      replaceScreenLocation(nextScreen);
      if (nextScreen === "active-session") setSelectedSessionId("");
    },
    [setSelectedSessionId],
  );

  React.useEffect(() => {
    const syncScreenFromLocation = () => {
      const nextScreen = screenFromLocation();
      setScreen(nextScreen);
      if (nextScreen === "active-session") setSelectedSessionId("");
    };
    window.addEventListener("hashchange", syncScreenFromLocation);
    return () => window.removeEventListener("hashchange", syncScreenFromLocation);
  }, [setSelectedSessionId]);

  const value = React.useMemo<NavigationContextValue>(
    () => ({
      screen,
      navigateScreen,
      shouldRestoreLastScreen: !hadExplicitInitialHashRef.current,
      clinicalMemoryReturnContext,
      setClinicalMemoryReturnContext,
      captureReturnSession,
      setCaptureReturnSession,
      accountReturnRef,
    }),
    [screen, navigateScreen, clinicalMemoryReturnContext, captureReturnSession],
  );

  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>;
}

export function useNavigation(): NavigationContextValue {
  const ctx = React.useContext(NavigationContext);
  if (!ctx) throw new Error("useNavigation must be used within NavigationProvider");
  return ctx;
}
