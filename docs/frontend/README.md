# Frontend Docs

Frontend docs describe the current app and the backend contracts it consumes.

## Documents

- [Frontend overview](overview.md): capture-first UX, feature structure, IndexedDB outbox, synced cache, and mobile testing notes.
- [Authentication and login](auth-login.md): dev persona login, production token flow, and patient persona separation.
- [Internationalization](i18n.md): fa/en + RTL, the chrome-vs-content axis, surface language authorities, and deferred scopes.
- [Sync outbox](sync-outbox.md): local-first capture, authenticated sync, backend ID mapping, and cache policy.

## Testing

Two Playwright layers: the **hermetic** suite (`tests/e2e/`, mocked API) and the merge-blocking
**real-stack** suite (`tests/e2e-stack/`, real compose backend) with its gateway-less **P0** gate and
mock-gateway **P1** tier. How to run each, the fixture-capture determinism seams, and the CI jobs are
documented in the app README's [Testing section](../../apps/frontend/README.md).

## Direction

The frontend remains capture-first. Login gates backend sync, not local capture safety: unsynced captures are protected in IndexedDB and only transferred after a user and tenant are authenticated.
