// Centralized in-screen back-navigation stack.
//
// The app is a single hash-routed page: top-level screen changes use history.replaceState, so they
// deliberately do NOT stack. A few *in-screen* levels — a patient's file, a smart-list drill-in, a
// historical visit review — used to have no history entry of their own, so a hardware/browser Back
// exited the whole area instead of stepping back one level. This controller gives each active level
// exactly one synthetic history entry and pops that level on Back, so Back steps back through them.
//
// Why centralized rather than a per-component pushState/back: opening one level frequently unmounts
// another in the SAME React commit (e.g. opening a patient from a smart-list row unmounts the list).
// Per-component effects that each pushState on mount and history.back() on unmount race against one
// another and corrupt the stack. Here, register/unregister only mutate an in-memory list; a single
// microtask-batched reconcile then diffs desired depth vs the synthetic-entry depth we own ONCE per
// commit, so a same-commit unregister+register nets to zero history churn and there is no race.

import React from "react";

type Level = { id: number; onExit: () => void };

let levels: Level[] = [];
// Synthetic history entries we currently own, stacked on top of the app's screen entry.
let syntheticDepth = 0;
// popstate events caused by our OWN history.go()/back() unwind (not a user Back gesture) to swallow.
let ignorePops = 0;
let reconcileScheduled = false;
let seq = 0;
let installed = false;

function installListener(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  window.addEventListener("popstate", () => {
    if (ignorePops > 0) {
      ignorePops -= 1; // our own unwind — the level is already gone, don't double-dismiss
      return;
    }
    if (!levels.length) return; // a Back with no active level: let the browser navigate normally
    // A real Back gesture consumed one synthetic entry — dismiss the deepest level and let its owner
    // clear its state. Its own unregister (from the resulting unmount/state change) is then a no-op.
    syntheticDepth = Math.max(0, syntheticDepth - 1);
    const top = levels.pop();
    top?.onExit();
    scheduleReconcile();
  });
}

function scheduleReconcile(): void {
  if (reconcileScheduled || typeof window === "undefined") return;
  reconcileScheduled = true;
  queueMicrotask(reconcile);
}

function reconcile(): void {
  reconcileScheduled = false;
  const desired = levels.length;
  if (desired > syntheticDepth) {
    // New level(s) opened via in-app UI: add a synthetic entry per new level.
    while (syntheticDepth < desired) {
      syntheticDepth += 1;
      window.history.pushState({ backLevel: syntheticDepth }, "");
    }
  } else if (desired < syntheticDepth) {
    // Level(s) closed via in-app UI (their own back button / a state change): unwind our own
    // synthetic entries so a later Back doesn't land on a dead one. A single go(-n) fires one
    // popstate, which we swallow via ignorePops so it isn't mistaken for a user Back.
    const remove = syntheticDepth - desired;
    syntheticDepth = desired;
    ignorePops += 1;
    window.history.go(-remove);
  }
}

/** Register an active in-screen level; returns an id to unregister it. `onExit` is invoked when a
 *  Back gesture dismisses this level (it should clear the level's own state). */
export function registerBackLevel(onExit: () => void): number {
  installListener();
  seq += 1;
  const id = seq;
  levels.push({ id, onExit });
  scheduleReconcile();
  return id;
}

/** Unregister a level closed by in-app UI. A no-op if a Back gesture already popped it. */
export function unregisterBackLevel(id: number): void {
  const idx = levels.findIndex((level) => level.id === id);
  if (idx === -1) return; // already dismissed by a Back gesture — nothing to unwind
  levels.splice(idx, 1);
  scheduleReconcile();
}

/**
 * Forget all synthetic entries without unwinding them. Call this right before a hard SCREEN switch
 * that `replaceState`s the current entry (which may be one of ours) — the sub-levels' components
 * unmount and their state is discarded, so their synthetic entries vanish with the replace. Without
 * this, the later unregister would `history.go(-1)` a real entry and bounce the screen back.
 */
export function resetBackLevels(): void {
  levels = [];
  syntheticDepth = 0;
}

/**
 * Give an in-screen level a browser-history entry so hardware/browser Back steps back to the level
 * beneath it instead of exiting the whole area. While `active`, one synthetic history entry is held;
 * a Back gesture pops it and calls `onExit` (clear this level's state), while closing the level via
 * in-app UI (which flips `active` to false) unwinds the entry cleanly.
 */
export function useBackLevel(active: boolean, onExit: () => void): void {
  const onExitRef = React.useRef(onExit);
  onExitRef.current = onExit;
  React.useEffect(() => {
    if (!active) return;
    const id = registerBackLevel(() => onExitRef.current());
    return () => unregisterBackLevel(id);
  }, [active]);
}
