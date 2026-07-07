# Frontend v1 Current App

## Stack

- Vite
- React
- TypeScript
- Plain CSS with shadcn/Tailwind-inspired component conventions

The active app entrypoint is:

```text
apps/frontend/src/main.tsx
apps/frontend/src/app/App.tsx
```

## Composition root & seams

`App.tsx` is a **composition root**, not a god-component: it assembles a layered set of provider seams
and dispatches routes. Everything cross-cutting is consumed through **hooks**, not threaded as props —
so a new feature attaches to a module seam instead of adding App state + a callback + a panel. The
layering (outer → inner), in `src/app/providers`:

```text
App() composition root
  ToastProvider          useToast()          transient toast, no prop-threading
  ApiProvider            useApi()            memoized auth-aware apiFetch + 401 refresh/retry   (INFRA)
  AuthProvider           useAuth()           auth session + login/register/logout/switch        (INFRA)
    AppLangProvider      (reads tenant.appLanguage → UI language + RTL)
  CapabilitiesProvider   useCapabilities()   tier × role → named affordances (the Basic/Pro fork) (INFRA)
  SyncProvider           useSync()           offline outbox engine (captures + operations)
  SessionStoreProvider   useSessions() / useActiveSession() / useSessionActions()
                         sessions[]/activeSession + the session/patient action layer              (seam C)
  NavigationProvider     useNavigation()     screen + navigateScreen + history + return-context   (seam D)
  AppInner               the app body — consumes the seams above via hooks; the top-level vertical
                         branch (unauth → patient-preview → therapy → aesthetics) lives here
```

- **Infra vs shell.** `Api`/`Auth`/`Capabilities`/`Toast` are shared infrastructure (the therapy
  vertical and patient-preview branch consume them too). `Sync`/`SessionStore`/`Navigation` are the
  aesthetics shell. `TherapyApp` is a self-contained app and is not dragged through it.
- **Session store (seam C).** `SessionStoreProvider` owns `sessions[]` / `activeSession` /
  `selectedSessionId` / `assignmentSessionId` / `memoryRefreshSignal`, the async-correctness refs, and
  the whole non-navigating session/patient action layer. It provides the outbox engine's `SessionSink`
  (see [sync outbox](sync-outbox.md)) and splits a **stable actions context** from the **volatile state
  slice** so dispatch-only consumers don't re-render on data churn. Its subtle list transitions
  (upsert id-swap, item-status propagation, the 404 self-heal patient-strip, staff-assignment
  enrichment) live as pure, unit-tested functions in `src/app/sessionStoreReducers.ts`.
- **Navigation (seam D).** `NavigationProvider` owns the top-level `screen`, `navigateScreen` (which
  owns the hash sync + back-stack reset), and the return-context. In-screen levels (patient file,
  smart-list drill-in, historical review) keep their synthetic-history mechanism in
  `shared/lib/backStack`. **Navigation-race rule:** an explicit location hash present at first load
  always wins over restore-last-screen (see [navigation](../ux/navigation.md)).
- **Feature API hooks (seam A1/E).** Per-feature binders wrap the client with `apiFetch` from context
  and gate by capability internally — e.g. `useMemoryApi()` (Clinical Memory) resolves its Pro-only
  binders to `undefined` for Basic. Memoized on `apiFetch` + capabilities so they don't re-fire child
  effects. This is why `PatientsHome` takes ~7 nav/route props instead of 45, and `CaptureScreen`
  reads its session mutations from `useSessionActions()` instead of ~40 callback props.
- **Region components (seam E).** Heavy screens compose region components (e.g. `CaptureRegions` —
  `SessionSafetyPanel` / `NextLinedUpBar` / `SessionReviewRegion`) so a UX epic attaches to a region,
  not a monolith.

## Source Layout

- `src/app`: the composition root (above), the navigation + session-store seams, and pure
  session-state helpers (`sessionState.ts`, `sessionStoreReducers.ts`).
- `src/app/outbox`: the framework-agnostic outbox engine (`createOutboxEngine`) that `SyncProvider`
  drives — serial capture upload, dependent-operation replay, retry, and the optimistic `saveDraft`.
  It touches no React/IndexedDB directly (injected ports), so it is unit-tested against a fake storage
  adapter (`outboxEngine.test.ts`). The durable stores + upload flow are unchanged; see
  [sync outbox](sync-outbox.md).
- `src/domain`: frontend session/capture/auth types and UX status mapping.
- `src/features/auth`: login and patient-preview gates.
- `src/features/capture`: capture dialogs, active session workspace, capture metadata, audio helpers, and local capture modeling.
- `src/features/memory`: Clinical Memory and Search screens.
- `src/features/shell`: authenticated app shell and sync safety banner.
- `src/services/api`: backend client and response normalizers.
- `src/services/storage`: IndexedDB/localStorage persistence boundaries.
- `src/shared`: small UI primitives and environment config.

## Shared UI primitives

`src/shared/ui/primitives.tsx` holds the app's presentational building blocks. Beyond the base
`Button`/`Card`/`Input`/`Badge`/`Dialog`/`Sheet`, these are the shared consistency primitives every
screen composes from — build on them rather than re-styling per surface:

- **`ScreenHeader` / `BackButton`** — the one back-button + title pattern for account/utility
  screens (Settings, Profile, Team, Plan, Switch clinic, Insights). The back button is a ≥44px tap
  target with an SVG chevron mirrored under RTL (points inline-start in both fa and en) — no literal
  `←` glyph. Replaces the old copy-pasted `.account-header` + sub-44px `.account-back` pill.
- **`Tabs`** — a horizontal segmented control (bordered pill, active state on the primary token,
  `overflow-x` scroll below 640px). Used by Insights' section tabs and chart series toggle.
- **`Select`** — a thin styled-native `<select>` wrapper (`appearance:none`, token border/radius,
  SVG caret whose side mirrors under RTL, ≥44px). It is visually identical **closed** to the
  portal'd **`SelectMenu`** (custom dropdown) — the two are one system: use `SelectMenu` for
  long/portal-sensitive lists, `Select` (or the `.select` class on a native `<select>`) for short
  native ones.
- **`DisclosureRow`** — a full-width toggle row (≥44px, `aria-expanded`, chevron that rotates 90°
  open and mirrors under RTL). Adopted on non-session surfaces (e.g. the Q&A thread expander); the
  session-layout epic consumes the same primitive.

## Design tokens & layout system

`src/styles.css` opens with the token block (`:root`) — the single source for color, radius, space,
text-size, shadow, **content-width** and **icon-size** scales. Rules reference tokens, not raw
values:

- **One primary blue** — `--color-primary` (`#075eff`). Buttons, tabs, links, focus rings and the
  Q&A surface all resolve to it (the old `#2563eb`/`#3753e6` divergences were migrated). Every `.btn`
  and interactive control carries a `:focus-visible` ring (`--color-primary-soft`).
- **One content-width system** — `--content-max` (820px, aligned with the topbar) and
  `--content-wide` (940px, the shell). Every primary column (account screens, Search, Q&A inbox,
  Visit, Memory) and the bottom capture bar resolve to `--content-max`, so content no longer jumps
  width between screens. New responsive work standardizes on the **640 / 768 / 1024** breakpoints.
- **Icon-size tokens** — `--icon-xs/sm/md/lg` (14/16/18/22px); SVG sizing rules use them, not raw px.
- Off-scale hex/radius literals that exactly matched a token were swept onto `var()`; `qaInbox.css`
  (previously near-token-free) is fully tokenized.

## UX Principles

- The default destination is `Capture`.
- Empty capture shows only three large actions: `Record audio`, `Take photo`, `Write note`.
- The first successful capture creates an active session automatically.
- New captures go into the current session by default.
- The doctor can start a `New session` quickly.
- Each capture flow includes a secondary action to save into a new session.
- Capture must remain available while syncing, processing, matching, or organizing happens in the background.
- Clinical Memory follows the UX docs: Today is session-first, Patients is patient-memory-first, and Needs input is decision-first with focused resolver actions.

## Local-First Capture

The frontend uses IndexedDB before any backend request. This is intentional.

Stores:

- `pendingCaptures`: unsynced source blobs and metadata.
- `cachedCaptures`: synced source blobs for fast local preview.

Visible state labels are owned by [UX states](../ux/states.md). Technical outbox semantics live in [sync outbox](sync-outbox.md).

## Outbox Recovery

The outbox should resume when:

- the browser fires the `online` event;
- the app hydrates with pending captures.

While unsynced captures exist, the UI reassures the user that captures are saved on this device. A `beforeunload` warning is acceptable when leaving could endanger device-only clinical material.

## Cache Policy

Synced captures are kept in `cachedCaptures` for faster previews. This cache is capped at `50 MB`.

Eviction policy:

- Only synced cached captures may be evicted.
- Unsynced pending captures must never be automatically deleted.
- Oldest/least recently accessed cached captures are evicted first.
- If local cache is missing, preview falls back to the backend source URL.

Known gaps:

- visible storage meter;
- warning when pending unsynced data grows too large;
- per-file limits for audio/photo;
- client-side image compression/resizing;
- chunked upload for long audio or large media.

## Mobile/LAN Testing

Run Vite on all interfaces:

```sh
cd apps/frontend
npm run dev -- --host 0.0.0.0
```

Use the `Network` URL printed by Vite on a phone connected to the same Wi-Fi.

Important: if `VITE_API_URL` points to `localhost`, the frontend falls back to `/api/v1` when opened by LAN IP. This prevents the phone from trying to call its own `localhost`.

## Browser Media Notes

Photo capture uses:

```text
<input type="file" accept="image/*" capture="environment">
```

Audio capture uses `MediaRecorder` when available and an audio file input fallback. Phone browsers commonly require HTTPS for microphone access, so local LAN HTTP testing may need the fallback.

## Development Commands

```sh
cd apps/frontend
npm install
npm run dev
npm run build
```
