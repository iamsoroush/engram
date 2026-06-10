import type { PendingCapture } from "../../domain/appTypes";

// A dependency-free store-only (uncompressed) ZIP builder, so staff can export queued/unsynced
// captures to disk before clearing space — the durability escape hatch (Epic G).

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function strBytes(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

const u16 = (n: number) => new Uint8Array([n & 0xff, (n >>> 8) & 0xff]);
const u32 = (n: number) => new Uint8Array([n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff]);

type ZipEntry = { name: string; data: Uint8Array };

function buildZip(entries: ZipEntry[]): Blob {
  const fileParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  for (const entry of entries) {
    const nameBytes = strBytes(entry.name);
    const crc = crc32(entry.data);
    const size = entry.data.length;
    const localHeader = concat([
      u32(0x04034b50), u16(20), u16(0), u16(0), u16(0), u16(0),
      u32(crc), u32(size), u32(size), u16(nameBytes.length), u16(0),
    ]);
    fileParts.push(localHeader, nameBytes, entry.data);
    centralParts.push(
      concat([
        u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0),
        u32(crc), u32(size), u32(size), u16(nameBytes.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset),
      ]),
      nameBytes,
    );
    offset += localHeader.length + nameBytes.length + size;
  }
  const centralStart = offset;
  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const eocd = concat([
    u32(0x06054b50), u16(0), u16(0), u16(entries.length), u16(entries.length), u32(centralSize), u32(centralStart), u16(0),
  ]);
  return new Blob([...fileParts, ...centralParts, eocd] as BlobPart[], { type: "application/zip" });
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const safe = (value: string) => value.replace(/[^\w.\-]+/g, "_").slice(0, 80);

/** Bundle every queued (unsynced) capture's media blob + a manifest into a single downloaded ZIP. */
export async function exportPendingCaptures(pending: PendingCapture[], dateStamp: string): Promise<number> {
  const entries: ZipEntry[] = [];
  const manifest: Array<Record<string, unknown>> = [];
  for (const capture of pending) {
    const file = capture.draft?.file;
    const baseName = safe(`${capture.localCaptureId || capture.id}-${capture.draft?.filename || "capture"}`);
    let exportedFile: string | null = null;
    if (file instanceof Blob && file.size) {
      exportedFile = `captures/${baseName}`;
      entries.push({ name: exportedFile, data: new Uint8Array(await file.arrayBuffer()) });
    }
    manifest.push({
      id: capture.id,
      type: capture.draft?.kind,
      filename: capture.draft?.filename || null,
      file: exportedFile,
      sessionId: capture.backendSessionId || capture.sessionId || capture.localSessionId,
      createdAt: new Date(capture.createdAt).toISOString(),
      note: capture.draft?.detail || null,
      retryCount: capture.retryCount,
    });
  }
  entries.push({ name: "manifest.json", data: strBytes(JSON.stringify({ exportedAt: dateStamp, count: pending.length, captures: manifest }, null, 2)) });
  downloadBlob(buildZip(entries), `notari-queued-captures-${dateStamp.slice(0, 10)}.zip`);
  return pending.length;
}
