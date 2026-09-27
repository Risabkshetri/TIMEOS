# TimeOS Browser Extension

Domain-level web attribution for Brave, Chromium, and Firefox — see
`docs/TIMEOS_ENGINEERING_SPEC.md` §11 and §38 Phase 9. Built with
[Plasmo](https://docs.plasmo.com/).

**No `host_permissions`, no content scripts, in either manifest.** This is structurally enforced,
not promised — `npm test` builds both real targets and asserts on the generated `manifest.json`.
Without a host permission the extension cannot read page content in any engine: it only ever sees
a tab's URL, reduces it to a registrable domain in the background context, and never stores or
sends the URL itself (unless you explicitly opt in to §11.6's local-only raw-URL mode).

## Architecture

One TypeScript source tree, two build targets (§11.1):

| Target | Browsers | Background model |
| --- | --- | --- |
| `chrome-mv3` | Brave, Chromium | MV3 service worker (evicted after ~30s idle) |
| `firefox-mv3` | Firefox | MV3 event page (`background.scripts`) |

- `src/lib/psl.ts` — URL → registrable domain (bundled Public Suffix List via `tldts`; the only
  function that ever sees a full URL).
- `src/lib/attribution.ts` — pure reducer implementing §11.2's attribution rule (active tab,
  focused window, not idle) and §11.3's background-lifetime reconciliation. No browser API calls;
  fully unit-testable.
- `src/lib/store.ts` — the IndexedDB event buffer (§11.2: "flush every 5 min or 200 events") plus
  the opt-in, never-synced local raw-URL log (§11.6).
- `src/lib/config.ts` — persistent scalars in `storage.local` (device identity, token, backend
  URL, settings) and Brave-vs-Chromium runtime detection.
- `src/lib/sync.ts` — enrollment and batch flush against the **existing** backend ingest contract
  (`POST /v1/devices/enroll`, `POST /v1/ingest/batch`) — no new backend API was needed.
- `src/background.ts` — the only module that touches a real `tabs`/`windows`/`idle`/`alarms` API;
  wires them to the pure reducer and the storage layers above.
- `src/popup.tsx` — enrollment UI and sync status.
- `src/options.tsx` — backend URL and the raw-URL-mode toggle.

## Develop

```bash
npm install
npm run dev             # chrome-mv3, watches for changes
npm run dev:firefox      # firefox-mv3
```

Load `build/chrome-mv3-dev` as an unpacked extension (`chrome://extensions` or
`brave://extensions`, Developer Mode → Load unpacked). For Firefox, use `about:debugging` →
This Firefox → Load Temporary Add-on during development (wiped on restart — see Distribution
below for permanent installs).

## Test

```bash
npm test          # unit tests + two REAL builds with manifest assertions (~6s)
npm run typecheck
```

## Build

```bash
npm run build           # build/chrome-mv3-prod  (Brave + Chromium, byte-identical)
npm run build:firefox   # build/firefox-mv3-prod
npm run build:all       # both
```

## Enroll a browser

Each browser install enrolls as its own TimeOS device (its own `device_id`, its own token,
independently revocable — §11.4). Generate a one-time enrollment code from the backend:

```bash
cd ../deploy && docker compose exec api python -m timeos.jobs.create_enrollment_code
```

Open the extension's popup, enter the code, and enroll. On a Chromium-target build the popup lets
you confirm Brave vs. Chromium (auto-detected via `navigator.brave`, since the two share one
build); the Firefox build sets `browser_family: firefox` automatically.

## Distribution (§11.5)

- **Brave / Chromium**: Load unpacked survives restarts; a dev-mode warning bubble may appear on
  each launch. This is the expected, permanent install path for both.
- **Firefox**: `about:debugging` temporary installs are wiped on every restart — unusable for
  continuous telemetry. Firefox **requires a signed `.xpi`** from AMO's unlisted (self-distribution)
  signing, which needs a Mozilla Add-on Developer account and involves an automated review with a
  turnaround delay. Start this process early, not at the end of the phase (§11.5's own warning).
  The fallback (Firefox Developer Edition / ESR with `xpinstall.signatures.required = false`) is
  documented but not recommended — it means changing the browser channel for a side project.

## Privacy (§11.2, §11.6)

- Only a registrable domain and a duration ever leave the device — never a path, query string, or
  page title.
- Private/incognito windows (including Brave's Tor windows) are excluded entirely; the extension
  is never granted incognito access.
- `browser_family` is retained for per-browser diagnostics but is **not** in the AI allowlist
  (§20.3) — which browser you used is not behaviourally interesting and is mildly fingerprinting.
- Raw URLs can optionally be kept **on-device only**, per browser, via Settings → "Store full URLs
  locally on this device" — off by default, never synced, never in any AI path.
