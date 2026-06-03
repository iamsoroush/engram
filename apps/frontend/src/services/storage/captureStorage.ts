import type { CachedCapture, IdMapping, PendingCapture, PendingOperation } from "../../domain/appTypes";
import type { CaptureItem } from "../../domain/types";

const OUTBOX_DB = "aesmem-capture-outbox";
const OUTBOX_STORE = "pendingCaptures";
const CACHE_STORE = "cachedCaptures";
const ID_MAPPING_STORE = "idMappings";
const OPERATION_STORE = "pendingOperations";
const CACHE_LIMIT_BYTES = 50 * 1024 * 1024;

/**
 * Opens the IndexedDB database that backs offline capture recovery.
 * Version 4 owns pending uploads, cached source blobs, local/backend ID maps,
 * and lightweight offline operations that depend on those maps.
 */
export function openOutboxDb() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(OUTBOX_DB, 4);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OUTBOX_STORE)) db.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(CACHE_STORE)) db.createObjectStore(CACHE_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(ID_MAPPING_STORE)) db.createObjectStore(ID_MAPPING_STORE, { keyPath: "id" });
      if (!db.objectStoreNames.contains(OPERATION_STORE)) db.createObjectStore(OPERATION_STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Wraps an IndexedDB request in a promise and closes the database once the
 * transaction settles.
 */
async function dbTransaction<T>(
  storeName: typeof OUTBOX_STORE | typeof CACHE_STORE | typeof ID_MAPPING_STORE | typeof OPERATION_STORE,
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
) {
  const db = await openOutboxDb();
  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const request = run(transaction.objectStore(storeName));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

const outboxTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(OUTBOX_STORE, mode, run);

const cacheTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(CACHE_STORE, mode, run);

const idMappingTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(ID_MAPPING_STORE, mode, run);

const operationTransaction = <T,>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) =>
  dbTransaction(OPERATION_STORE, mode, run);

export const savePendingCapture = (capture: PendingCapture) => outboxTransaction("readwrite", (store) => store.put(capture));

export const removePendingCapture = (id: string) => outboxTransaction("readwrite", (store) => store.delete(id));

export const saveIdMapping = (mapping: IdMapping) => idMappingTransaction("readwrite", (store) => store.put(mapping));

export const loadIdMapping = (id: string) => idMappingTransaction<IdMapping | undefined>("readonly", (store) => store.get(id));

export const savePendingOperation = (operation: PendingOperation) =>
  operationTransaction("readwrite", (store) => store.put(operation));

export const removePendingOperation = (id: string) => operationTransaction("readwrite", (store) => store.delete(id));

export const loadPendingOperations = () =>
  operationTransaction<PendingOperation[]>("readonly", (store) => store.getAll()).then((operations) =>
    operations.sort((a, b) => a.createdAt - b.createdAt),
  );

export async function clearLocalCaptureData() {
  const db = await openOutboxDb();
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction([OUTBOX_STORE, CACHE_STORE, ID_MAPPING_STORE, OPERATION_STORE], "readwrite");
    transaction.objectStore(OUTBOX_STORE).clear();
    transaction.objectStore(CACHE_STORE).clear();
    transaction.objectStore(ID_MAPPING_STORE).clear();
    transaction.objectStore(OPERATION_STORE).clear();
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

export const loadPendingCaptures = () =>
  outboxTransaction<PendingCapture[]>("readonly", (store) => store.getAll()).then((captures) =>
    captures.map(normalizePendingCapture).sort((a, b) => a.createdAt - b.createdAt),
  );

export const loadPendingCapture = (id: string) =>
  outboxTransaction<PendingCapture | undefined>("readonly", (store) => store.get(id)).then((capture) =>
    capture ? normalizePendingCapture(capture) : undefined,
  );

export const loadCachedCaptures = () => cacheTransaction<CachedCapture[]>("readonly", (store) => store.getAll());

/**
 * Updates cache recency when a source blob is read so cache eviction can drop
 * the least recently used captures first.
 */
export async function getCachedCapture(id: string) {
  const cached = await cacheTransaction<CachedCapture | undefined>("readonly", (store) => store.get(id));
  if (cached) void cacheTransaction("readwrite", (store) => store.put({ ...cached, lastAccessedAt: Date.now() }));
  return cached;
}

/**
 * Keeps the local source preview cache bounded without deleting pending upload
 * records from the outbox.
 */
export async function enforceCacheLimit() {
  const cachedCaptures = await loadCachedCaptures();
  let total = cachedCaptures.reduce((sum, capture) => sum + capture.size, 0);
  const oldestFirst = [...cachedCaptures].sort((a, b) => a.lastAccessedAt - b.lastAccessedAt || a.createdAt - b.createdAt);

  for (const capture of oldestFirst) {
    if (total <= CACHE_LIMIT_BYTES) break;
    await cacheTransaction("readwrite", (store) => store.delete(capture.id));
    total -= capture.size;
  }
}

export async function saveSyncedCaptureCache(item: CaptureItem, blob: Blob) {
  await cacheTransaction("readwrite", (store) =>
    store.put({
      id: item.id,
      blob,
      sourceName: item.sourceName,
      contentType: item.contentType || blob.type || "application/octet-stream",
      size: blob.size,
      createdAt: Date.now(),
      lastAccessedAt: Date.now(),
    } satisfies CachedCapture),
  );
  await enforceCacheLimit();
}

/**
 * Atomically reads and updates one pending capture inside a readwrite
 * transaction to avoid racing with outbox processing.
 */
export async function updatePendingCapture(id: string, update: (capture: PendingCapture) => PendingCapture) {
  const db = await openOutboxDb();
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(OUTBOX_STORE, "readwrite");
    const store = transaction.objectStore(OUTBOX_STORE);
    const getRequest = store.get(id);
    getRequest.onsuccess = () => {
      if (!getRequest.result) return;
      store.put(update(getRequest.result as PendingCapture));
    };
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

export async function updatePendingOperation(id: string, update: (operation: PendingOperation) => PendingOperation) {
  const db = await openOutboxDb();
  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(OPERATION_STORE, "readwrite");
    const store = transaction.objectStore(OPERATION_STORE);
    const getRequest = store.get(id);
    getRequest.onsuccess = () => {
      if (!getRequest.result) return;
      store.put(update(getRequest.result as PendingOperation));
    };
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

/**
 * After the first upload creates a backend session, binds sibling local captures
 * to that same backend session instead of creating extra sessions.
 */
export async function bindPendingSession(localSessionId: string, sessionId: string) {
  const captures = await loadPendingCaptures();
  await Promise.all(
    captures
      .filter((capture) => capture.localSessionId === localSessionId)
      .map((capture) =>
        updatePendingCapture(capture.id, (current) => ({
          ...current,
          sessionId,
          backendSessionId: sessionId,
          intoNew: false,
        })),
      ),
  );
}

export function normalizePendingCapture(capture: PendingCapture) {
  const clientCaptureId = capture.clientCaptureId || capture.id;
  const localCaptureId = capture.localCaptureId || capture.id;
  return {
    ...capture,
    localCaptureId,
    clientCaptureId,
    backendSessionId: capture.backendSessionId || capture.sessionId,
    item: {
      ...capture.item,
      id: capture.item.id || localCaptureId,
      clientCaptureId: capture.item.clientCaptureId || clientCaptureId,
    },
  };
}
