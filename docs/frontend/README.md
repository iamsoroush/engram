# Frontend Docs

Frontend docs describe the current app and the backend contracts it consumes.

## Documents

- [Frontend overview](overview.md): capture-first UX, feature structure, IndexedDB outbox, synced cache, and mobile testing notes.
- [Authentication and login](auth-login.md): dev persona login, production token flow, and patient persona separation.
- [Sync outbox](sync-outbox.md): local-first capture, authenticated sync, backend ID mapping, and cache policy.

## Direction

The frontend remains capture-first. Login gates backend sync, not local capture safety: unsynced captures are protected in IndexedDB and only transferred after a user and tenant are authenticated.
