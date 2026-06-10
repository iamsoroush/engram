import type { CaptureItem, CaptureSession, Screen } from "../../domain/types";
import type { CaptureDraft, StoredWorkspaceState } from "../../domain/appTypes";

const WORKSPACE_STORAGE_KEY = "notari-active-workspace";

function stripVolatileCapturePreview(item: CaptureItem): CaptureItem {
  const { sourceUrl, url, ...rest } = item;
  return {
    ...rest,
    ...(sourceUrl && !sourceUrl.startsWith("blob:") ? { sourceUrl } : {}),
    ...(url && !url.startsWith("blob:") ? { url } : {}),
  };
}

function stripVolatileSessionPreview(session: CaptureSession): CaptureSession {
  return {
    ...session,
    items: session.items.map(stripVolatileCapturePreview),
  };
}

export function persistWorkspaceState(state: {
  tenantId?: string;
  screen: Screen;
  activeSession: CaptureSession | null;
  selectedSessionId: string;
  assignmentSessionId: string;
  pendingCaptureKind: CaptureDraft["kind"] | null;
}) {
  const stored: StoredWorkspaceState = {
    schemaVersion: 1,
    tenantId: state.tenantId,
    screen: state.screen,
    activeSession: state.activeSession ? stripVolatileSessionPreview(state.activeSession) : null,
    selectedSessionId: state.selectedSessionId,
    assignmentSessionId: state.assignmentSessionId,
    pendingCaptureKind: state.pendingCaptureKind,
    updatedAt: Date.now(),
  };
  window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(stored));
}

export function loadWorkspaceState(tenantId?: string) {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredWorkspaceState;
    if (parsed.schemaVersion !== 1) return null;
    if (tenantId && parsed.tenantId && parsed.tenantId !== tenantId) return null;
    return parsed;
  } catch {
    window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    return null;
  }
}

export function clearWorkspaceState() {
  window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
}
