// First-run onboarding flag. Set only when a clinic is created via sign-up (a brand-new founder),
// so the guided "capture your first visit" tour shows once and survives a reload, keyed per user.
// Client-side only — onboarding is training UX, not security.

const KEY = "memara-onboarding-pending";

/** Mark that this freshly signed-up founder should see the guided first-capture tour. */
export function markOnboardingPending(userId: string): void {
  try {
    window.localStorage.setItem(KEY, userId);
  } catch {
    // non-fatal (private mode, etc.)
  }
}

/** Whether the guided tour is still pending for this user. */
export function isOnboardingPending(userId: string): boolean {
  try {
    return window.localStorage.getItem(KEY) === userId;
  } catch {
    return false;
  }
}

/** Clear the pending flag once the tour is completed or skipped. */
export function clearOnboardingPending(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // non-fatal
  }
}
