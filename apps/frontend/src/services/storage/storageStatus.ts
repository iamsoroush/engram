export type StorageLevel = "ok" | "warn" | "full";

export type StorageStatus = {
  usageRatio: number;
  remainingBytes: number;
  quotaBytes: number;
  level: StorageLevel;
  supported: boolean;
};

// Durable-storage durability thresholds (Epic G). `warn` matches the existing Clinical Memory
// storage warning (~85% / <150 MB). `full` is the hard-stop: capturing is paused because a new
// capture can no longer be guaranteed to survive.
const WARN_RATIO = 0.85;
const WARN_REMAINING = 150 * 1024 * 1024;
const FULL_RATIO = 0.97;
const FULL_REMAINING = 25 * 1024 * 1024;

export const OK_STORAGE_STATUS: StorageStatus = {
  usageRatio: 0,
  remainingBytes: 0,
  quotaBytes: 0,
  level: "ok",
  supported: false,
};

export async function estimateStorageStatus(): Promise<StorageStatus> {
  if (typeof navigator === "undefined" || !navigator.storage?.estimate) return OK_STORAGE_STATUS;
  try {
    const { quota = 0, usage = 0 } = await navigator.storage.estimate();
    const remainingBytes = quota > usage ? quota - usage : 0;
    const usageRatio = quota ? usage / quota : 0;
    let level: StorageLevel = "ok";
    if (usageRatio >= FULL_RATIO || (quota > 0 && remainingBytes < FULL_REMAINING)) level = "full";
    else if (usageRatio >= WARN_RATIO || (quota > 0 && remainingBytes < WARN_REMAINING)) level = "warn";
    return { usageRatio, remainingBytes, quotaBytes: quota, level, supported: true };
  } catch {
    return OK_STORAGE_STATUS;
  }
}

export function formatBytes(bytes: number): string {
  if (!bytes || bytes < 0) return "0 MB";
  const mb = bytes / (1024 * 1024);
  if (mb < 1024) return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
