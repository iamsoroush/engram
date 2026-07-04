import {
  bindPendingSession,
  clearLocalCaptureData,
  loadIdMapping,
  loadPendingCapture,
  loadPendingCaptures,
  loadPendingOperations,
  normalizePendingCapture,
  removePendingCapture,
  removePendingOperation,
  savePendingCapture,
  savePendingOperation,
  saveSyncedCaptureCache,
  updatePendingCapture,
  updatePendingOperation,
} from "../../services/storage/captureStorage";
import { exportPendingCaptures } from "../../services/storage/exportCaptures";
import type { StoragePort } from "./types";

// The production StoragePort: the IndexedDB outbox + the ZIP export escape hatch, gathered behind the
// engine's storage seam so the engine never imports IndexedDB directly (and tests can swap a fake).
export const indexedDbStoragePort: StoragePort = {
  loadPendingCaptures,
  loadPendingCapture,
  savePendingCapture,
  updatePendingCapture,
  removePendingCapture,
  loadPendingOperations,
  savePendingOperation,
  updatePendingOperation,
  removePendingOperation,
  loadIdMapping,
  bindPendingSession,
  saveSyncedCaptureCache,
  normalizePendingCapture,
  clearLocalCaptureData,
  exportPendingCaptures,
};
