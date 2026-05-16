# Frontend Docs

Frontend docs describe the current prototype and the v2 contracts it must support.

## Documents

- [Current prototype](v1-current.md): capture-first UX, IndexedDB outbox, synced cache, and mobile testing notes.
- [Authentication and login](auth-login.md): dev persona login, production token flow, and patient persona separation.
- [Sync outbox](sync-outbox.md): local-first capture, authenticated sync, backend ID mapping, and cache policy.

## Direction

The frontend remains capture-first. Login gates backend sync, not local capture safety: unsynced captures are protected in IndexedDB and only transferred after a user and tenant are authenticated.
