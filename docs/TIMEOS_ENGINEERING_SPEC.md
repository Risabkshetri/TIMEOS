# TimeOS — Personal Time Intelligence System
## Engineering Specification (v1.0)

> Status: **Design complete, implementation not started.**
> Audience: a strong coding agent implementing this phase-by-phase without redesigning architecture.
> Author role: Principal Architect / Staff Systems / Android Systems / Privacy Engineering.

---

## 1. Executive Summary

TimeOS is a **private, local-first personal telemetry system** that reconstructs how the owner spends
time across an Android phone (primary), a Linux laptop (secondary) and a browser (secondary), then
answers behavioural questions about focus, fragmentation, distraction and goal alignment.

The defining architectural constraints are:

1. **Deterministic software computes all numbers.** Durations, sessions, focus, context switches,
   fragmentation, and trends are produced by ordinary, unit-tested code. The LLM never computes a
   metric.
2. **The LLM is an interpreter behind a technical privacy boundary.** It receives only an allowlisted,
   schema-validated, aggregate `AIContext` object. It holds no database credentials, no query tool, and
   no access to raw events. This is enforced by process/network isolation and by a validating gate with
   automated tests — not by prompt wording.
3. **Absence of data is never evidence of behaviour.** Every minute of the day is classified into one of
   `TRACKED | IDLE | UNOBSERVED | DEVICE_OFFLINE`. A powered-off laptop produces `DEVICE_OFFLINE`, never
   "3 hours wasted".
4. **Collection never depends on the network.** Each collector writes to a local durable store and syncs
   opportunistically with idempotent, batched, ACK-driven sync.
5. **The system is fully useful with the LLM switched off.** Losing the AI provider degrades
   interpretation only; every metric, chart and timeline keeps working.

Deployment target for V1 is a **single small VPS running Docker Compose** (FastAPI + PostgreSQL +
Next.js + Caddy, Redis only when a real need appears). Expected steady-state cost is **$7–13/month**
including LLM usage, because AI runs once per day and once per week, not per event.

The build order is deliberately **Android-first**: the phone carries the majority of a personal day's
screen time, has the most restrictive platform constraints, and is therefore the component most likely
to invalidate assumptions. The browser extension follows once the Android→backend→analytics→dashboard
pipeline is proven end-to-end on real data. **The Linux desktop collector is explicitly deferred out of
V1** (§4.5): the target laptop runs GNOME on Wayland, which provides no portable active-window API, and
no part of V1 will depend on solving that.

---

## 2. Product Vision

TimeOS answers, from real evidence and with explicit uncertainty:

| Question | Produced by |
|---|---|
| Where did my time go? | Deterministic category/app aggregation |
| How much was actually productive? | Activity intelligence + user-defined taxonomy |
| How much was deep work? | Focus Engine (continuity + interruption rules) |
| How much was distraction? | Distraction Engine (behavioural patterns, not app blacklists) |
| How fragmented was my day? | Fragmentation index from context-switch rate |
| When am I most focused? | Time-of-day histogram over ≥14 days |
| What consumes my attention? | App/domain ranking with trend deltas |
| What patterns are emerging? | Historical intelligence over 7/30/90-day baselines |
| What aligns with my goals? | Goal Alignment Engine (with declared uncertainty) |
| What should I change tomorrow? | LLM analyst over sanitized context |

Non-goals for V1: multi-user SaaS, iOS, screenshots, content capture, keystroke logging, real-time
interventions/blocking, social comparison.

---

## 3. Core Principles

1. **Deterministic first, AI last.** If a number can be computed, it is computed — never inferred.
2. **Privacy by construction.** Data that must not reach the LLM is structurally unable to reach it.
3. **Honest absence.** `UNOBSERVED` is a first-class value. Never interpolate, never invent activity.
4. **Offline-first.** The network is an optimisation, never a precondition for collection.
5. **Idempotent everything.** Every write path is safe to retry; every event has a stable client-side ID.
6. **Fact / Inference / Hypothesis are labelled distinctly** everywhere they surface.
7. **Calibrated confidence.** `Unknown` is a valid classification; forcing a label is a bug.
8. **Correctable.** Every classification can be overridden by the user, and overrides become training data.
9. **Minimum viable telemetry.** Collect the least data that answers the question.
10. **Observable.** The system reports on its own trustworthiness (coverage, sync lag, unknown %).
11. **Boring infrastructure.** One monolith, one database, one VPS. No Kubernetes, no microservices.
12. **Reversible.** Full export and hard delete are supported from day one.

---

## 4. Existing Repository Audit

### 4.1 Method
`/home/rishab-chhetri/Desktop/jarvis` was inspected directly: full recursive listing, hidden files,
VCS state, and host toolchain probing.

### 4.2 Findings

| Audit item | Finding |
|---|---|
| Repository contents | **Completely empty.** No files, no subdirectories, no hidden files. |
| Git | **Not a git repository.** `git init` required in Phase 0. |
| Existing applications/services | None. |
| Frontend / backend architecture | None. Greenfield. |
| Databases | None in-repo. PostgreSQL 16 *client* present on host. |
| Authentication | None. Must be designed from scratch. |
| Deployment infrastructure | None in-repo. |
| Docker configuration | None in-repo. Docker 29.8.0 + Compose v5.5.1 available on host. |
| Environment/config management | None. |
| AI/LLM integrations | None. |
| Reusable components | **None.** Zero reuse opportunity. |
| Technical debt | **None inherited** — the single genuine advantage of this audit. |
| Conflicts with proposed architecture | **None.** No prior technology choices constrain us. |

### 4.3 Host toolchain (verified, affects Phase sequencing)

| Tool | Version | Implication |
|---|---|---|
| git | 2.43.0 | OK |
| Python | 3.12.3 | Matches backend target; use 3.12 in Docker for parity |
| Node | 24.19.0 | Next.js 15 OK |
| npm | 11.17.0 | OK |
| Docker | 29.8.0 | OK |
| Docker Compose | v5.5.1 (plugin) | Use `docker compose`, never `docker-compose` |
| psql | 16.15 | Pin server to **PostgreSQL 16** for client/server parity |
| JDK | OpenJDK 17.0.20 | Matches AGP 8.x requirement (JDK 17) |
| Android SDK | build-tools 36.0.0, platform android-37.0 | **compileSdk 36** is the safe target; android-37 platform present but 36 build-tools means `compileSdk 36` |
| adb | present, **0 devices attached** | Physical device pairing is a Phase 1 prerequisite |
| OS | Ubuntu, GNOME, **Wayland** session (`XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=ubuntu:GNOME`) | No portable active-window API → desktop collector **deferred out of V1**, see §4.5 and §10 |
| Test phone | **Samsung Galaxy S24 FE (SM-S721B/DS)**, One UI | Android 14+; One UI background-usage limits are the dominant collector risk — see Phase 1B |

### 4.4 Audit conclusions

- Greenfield: the proposed stack can be adopted wholesale; no "do not replace existing tech" tension.
- **Missing infrastructure to build:** git repo, monorepo layout, Docker Compose stack, migrations,
  secret management, CI, device auth, backup tooling — all are Phase 0/3 work items.
- **Sequencing risk:** no Android device was attached to adb at audit time. The target device is a
  **Samsung Galaxy S24 FE**; Phase 1 cannot be *manually verified* until it is connected with USB
  debugging enabled. The emulator can validate code paths but **cannot validate real usage-statistics
  behaviour** (an emulator has no real usage history and no One UI battery-killer behaviour).
  Critically, **Usage Access cannot be validated before an APK exists on the device** — this dictates
  the Phase 1A/1B split (§38).
- **compileSdk decision:** build-tools 36.0.0 is installed while the only platform is android-37.0.
  Phase 0 must run `sdkmanager "platforms;android-36" "build-tools;36.0.0"` and target
  `compileSdk = 36`, `targetSdk = 36`, `minSdk = 29`. Do not target an SDK whose build-tools are absent.

### 4.5 Verified environment decisions (authoritative — these override any conflicting guidance above)

| Decision | Ruling |
|---|---|
| Primary test phone | Samsung Galaxy S24 FE (SM-S721B/DS), One UI |
| Laptop session | Ubuntu / GNOME / **Wayland** — **do not switch the session to X11 for TimeOS** |
| Linux desktop collector | **Deferred out of V1** (moved to Phase 12). No V1 deliverable may depend on it |
| Desktop collector, when built | **Degraded / coverage-only** unless reliable Wayland attribution exists. It must never claim to know the active application when it cannot reliably determine it |
| First Android milestone | A **minimal installable APK** that explains and requests Usage Access. Usage Access configuration is **not** a prerequisite for anything before that APK exists |
| Phone identity | A generated TimeOS device ID (UUIDv4). **Never** IMEI, serial, `ANDROID_ID`, phone number, or any hardware/network identifier |
| Never collected | IMEI, phone number, serial, contacts, notification contents, SMS, passwords, arbitrary private content |
| Browsers | **Brave, Chromium and Firefox — all three**, run concurrently. Two engine targets (Chromium + Gecko) from one source tree; each install enrolls as its own TimeOS device (§11) |

**V1 scope (in order):** Android collector → Android local storage → offline-first sync → backend
ingestion → deterministic behavioural analytics → web dashboard → browser extension → privacy gate →
AI analysis.

**Deferred out of V1:** full Linux active-window attribution; screenshot collection; raw page-content
collection; any LLM access to raw telemetry.

---

## 5. Proposed Architecture

### 5.1 Monorepo layout

```
jarvis/
├── docs/
│   ├── TIMEOS_ENGINEERING_SPEC.md      # this file
│   └── adr/                            # ADRs extracted from §41 as they evolve
├── android/                            # Kotlin / Compose collector (PRIMARY)
│   ├── app/
│   └── core/{collector,db,sync,ui}/
├── backend/                            # FastAPI monolith
│   └── timeos/
│       ├── api/                        # HTTP layer only
│       ├── ingest/                     # idempotent batch ingestion
│       ├── analytics/                  # sessionization, focus, distraction, goals
│       ├── privacy/                    # PrivacyGate + AIContextBuilder  ← isolated
│       ├── ai/                         # provider-agnostic LLM client    ← isolated
│       ├── models/                     # SQLAlchemy ORM
│       ├── schemas/                    # Pydantic v2 contracts
│       └── jobs/                       # scheduled pipeline runs
├── dashboard/                          # Next.js 15 App Router + TS + Tailwind
├── extension/                          # WebExtension: Brave/Chromium + Firefox builds (Phase 9)
├── desktop/                            # Python agent (Phase 12 — POST-V1, deferred)
├── deploy/                             # compose files, Caddyfile, backup scripts
└── tools/                              # dev scripts, fixture generators
```

**Why a monorepo:** one owner, one release cadence, shared event-schema definitions across four
languages. The event contract is the single most-coupled artifact in the system; splitting repos would
guarantee schema drift.

### 5.2 Layered pipeline

```
L1  Device Collectors        Android | Desktop | Browser
L2  Local Event Store        Room (Android) | SQLite (desktop) | IndexedDB (extension)
L3  Sync Layer               batched, idempotent, ACK-driven, offline queue
L4  Raw Event Store          Postgres raw_events (append-only, never leaves the server)
L5  Sessionization Engine    events → app_sessions / browser_sessions / device_coverage
L6  Activity Intelligence    sessions → activities (category, intent, confidence, evidence)
L7  Personal Context         goals, projects, hours, taxonomies, corrections
L8  Behavioural Analytics    daily_metrics, weekly_metrics, behavioral_patterns
L9  PRIVACY GATE             allowlist + schema validation + audit log   ◄── hard boundary
L10 AI Context Builder       aggregate-only, sanitized, versioned payload
L11 LLM Analyst              interpretation only, structured output
L12 Structured Insight Store ai_analysis, ai_insights (claim/evidence/confidence)
L13 Dashboard                Next.js read-only views over L8 + L12
```

Everything **below** L9 is private server-side data. Everything **above** L9 is aggregate and safe to
transmit. The gate is the only legal crossing.

---

## 6. Architecture Diagram

```
┌────────────────┐  ┌────────────────┐  ┌──────────────────┐
│ Android (Kt)   │  │ Desktop (Py)   │  │ Browsers ×3      │
│ UsageStats     │  │ psutil + WM    │  │ Brave·Chromium·FF│
│ WorkManager    │  │ idle detect    │  │ alarms           │
│ Room (local)   │  │ SQLite (local) │  │ IndexedDB        │
└───────┬────────┘  └───────┬────────┘  └────────┬─────────┘
        │  batched HTTPS, idempotent, ACK        │
        └──────────────┬────────────────┬────────┘
                       ▼                ▼
             ┌───────────────────────────────────┐
             │ FastAPI monolith (VPS, Docker)    │
             │  /v1/ingest  device-token auth    │
             ├───────────────────────────────────┤
             │ raw_events (append-only)          │
             │   ↓ Sessionization                │
             │ app_sessions | device_coverage    │
             │   ↓ Activity Intelligence         │
             │ activities (+confidence+evidence) │
             │   ↓ Behavioural Analytics         │
             │ daily_metrics | patterns          │
             └──────────────┬────────────────────┘
                            │
              ╔═════════════▼═════════════╗
              ║  PRIVACY GATE (L9)        ║  allowlist · schema · audit
              ║  no raw rows may pass     ║  no DB handle beyond here
              ╚═════════════┬═════════════╝
                            ▼
                 AIContext (aggregates only)
                            ▼
              ┌───────────────────────────┐
              │ LLM Analyst (pluggable)   │  cloud | local | none
              │ structured JSON out       │
              └─────────────┬─────────────┘
                            ▼
              ai_analysis / ai_insights  ──►  Next.js Dashboard
```

---

## 7. Component Responsibilities

| Component | Owns | Explicitly does NOT |
|---|---|---|
| Android collector | Foreground app events, screen/lock state, device on/off markers, local buffering, sync | Read notification content, window titles, or message bodies |
| Desktop agent | Active app/window class, idle duration, session/online state | Screenshots, keystrokes, clipboard, file paths |
| Browser extension (×3: Brave, Chromium, Firefox) | Registrable domain, timestamps, duration, tab focus, own-browser focus state | Full URLs, query strings, page content, form data, cross-browser coordination |
| Ingest API | Auth, idempotency, validation, append to `raw_events` | Any analytics or mutation of event payloads |
| Sessionization | Events → sessions + coverage intervals | Judgement about value of time |
| Activity Intelligence | Sessions → categorised activities with confidence | Hard-coded moral judgement of apps |
| Personal Context | Goals, hours, taxonomy, corrections | Storing anything the user has not declared |
| Analytics | All numeric metrics and trends | Natural-language narrative |
| PrivacyGate | Allowlist enforcement, schema validation, audit | Being bypassable by any caller |
| AIContextBuilder | Sanitized aggregate assembly | Reading raw tables (has no access) |
| LLM Analyst | Interpretation, diagnosis, recommendations | Arithmetic, DB access, tool calls |
| Insight Store | Validated AI output with provenance | Accepting unvalidated output |
| Dashboard | Visualisation, correction UI, goal management | Direct SQL, business logic |

---

## 8. Android Architecture

Android is the **primary** collector and the component with the hardest platform constraints.

### 8.1 Data source decision: `UsageStatsManager.queryEvents()`

`queryEvents(begin, end)` returns a chronological `UsageEvents` stream. TimeOS consumes exactly these
event types and ignores the rest:

| `UsageEvents.Event` type | Const | Use |
|---|---|---|
| `ACTIVITY_RESUMED` (`MOVE_TO_FOREGROUND`) | 1 | App session start |
| `ACTIVITY_PAUSED` (`MOVE_TO_BACKGROUND`) | 2 | App session end |
| `ACTIVITY_STOPPED` | 23 | Session end fallback |
| `SCREEN_INTERACTIVE` | 15 | Screen on |
| `SCREEN_NON_INTERACTIVE` | 16 | Screen off → ends all sessions |
| `KEYGUARD_SHOWN` | 17 | Locked |
| `KEYGUARD_HIDDEN` | 18 | Unlock (unlock-count proxy) |
| `DEVICE_SHUTDOWN` | 26 | Emit `DEVICE_OFFLINE` coverage start |
| `DEVICE_STARTUP` | 27 | Emit `DEVICE_OFFLINE` coverage end |
| `USER_INTERACTION` | 7 | Liveness signal for idle discrimination |

**Rejected sources and why:**
- `queryUsageStats()` — pre-bucketed totals, no ordering, cannot reconstruct a timeline. Rejected.
- `AccessibilityService` — would expose window titles and text content. Violates §20 privacy model and
  Play policy. **Prohibited in V1.**
- `NotificationListenerService` — reads notification *content*. Off by default; see §8.6.
- `ActivityManager.getRunningTasks()` — deprecated/neutered since API 21. Rejected.

### 8.2 Permission model

| Permission | Type | How obtained | Consequence if denied |
|---|---|---|---|
| `android.permission.PACKAGE_USAGE_STATS` | **appops special** | User toggles in `Settings.ACTION_USAGE_ACCESS_SETTINGS`; cannot be requested via a runtime dialog | **Total collection failure.** App must detect via `AppOpsManager.unsafeCheckOpNoThrow("android:get_usage_stats")` and show a blocking onboarding screen |
| `RECEIVE_BOOT_COMPLETED` | normal | manifest | Collection resumes only on next app open |
| `POST_NOTIFICATIONS` (API 33+) | runtime | dialog | Cannot show the persistent status notification; collection unaffected |
| `QUERY_ALL_PACKAGES` | normal-but-policy-restricted | manifest | Cannot resolve package → human label. Acceptable for a sideloaded personal build; see §8.7 |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | special | user prompt | Higher risk of missed polls on aggressive OEMs |
| `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_DATA_SYNC` | normal | manifest | Only needed if §8.4 fallback is used |

**Critical:** `PACKAGE_USAGE_STATS` is silently revocable by the user at any time. The collector must
re-check it on every worker run and record a `PERMISSION_LOST` health event rather than failing quietly.

### 8.3 Execution model — polling, not a foreground service

The decisive insight: **`queryEvents` is a historical query.** The OS records events regardless of
whether TimeOS is running. Therefore TimeOS does not need to observe in real time — it needs only to
*drain the OS buffer before it expires*.

- `PeriodicWorkRequest` every **15 minutes** (WorkManager's floor), `ExistingPeriodicWorkPolicy.KEEP`,
  backoff `EXPONENTIAL, 30s`, no network constraint (collection must never wait on connectivity).
- Each run queries `[last_cursor - 5min, now]` (overlap window absorbs clock jitter), dedupes by
  event fingerprint, writes to Room, advances the cursor.
- A separate `OneTimeWorkRequest` chain handles sync, constrained on `NetworkType.CONNECTED`.
- `BOOT_COMPLETED` receiver re-enqueues work and emits the `DEVICE_STARTUP` coverage marker.

**This is the single most important battery decision in the system.** A foreground service polling
continuously would cost multiple percent per day; 96 short WorkManager runs cost well under 1%.

### 8.4 The 7-day retention hazard (hard platform limit)

The OS retains *event-level* usage data for a **limited window (approximately 7–10 days**, with only
aggregated daily buckets beyond that; the exact figure is AOSP/OEM-dependent and must be treated as
"about a week, do not rely on more"). If TimeOS does not run for longer than that window, **that data
is permanently unrecoverable** — not delayed, gone.

Mitigations, all required:
1. Poll every 15 minutes (≈672× margin against a 7-day window).
2. On every app launch, run an immediate catch-up drain from `last_cursor`.
3. If `now - last_cursor > 48h`, raise a **user-visible** warning: "TimeOS was not running; up to N
   hours may be missing." Never silently backfill.
4. If `now - last_cursor > 6 days`, escalate the warning and record a `RETENTION_RISK` health event.
5. Emit an explicit `UNOBSERVED` coverage interval for any gap — never zero-fill.

### 8.5 Version compatibility matrix

| API | Version | Impact on TimeOS |
|---|---|---|
| 29 | 10 | **minSdk.** Non-resettable identifiers restricted → device ID must be app-generated UUID, never IMEI/serial |
| 30 | 11 | Package visibility filtering → `<queries>` or `QUERY_ALL_PACKAGES` needed for labels |
| 31 | 12 | Exact alarms restricted (we use none); splash screen API |
| 33 | 13 | `POST_NOTIFICATIONS` runtime permission required |
| 34 | 14 | **Foreground service types mandatory**; `dataSync` FGS capped (~6h/24h) — reinforces §8.3 no-FGS design |
| 35 | 15 | Edge-to-edge enforced; further FGS tightening |
| 36 | 16 | **compileSdk/targetSdk target.** Stricter background limits |

OEM reality: Xiaomi/Oppo/Vivo/Samsung aggressive killers can suppress WorkManager. Onboarding must
link to the device's autostart settings and the app must surface *observed* poll cadence in-app so the
user can see if the OEM is killing it.

### 8.6 Notification metadata — deliberately deferred

`NotificationListenerService` exposes package, timestamp, **title and text**. Title/text routinely
contain message bodies and contact names — precisely the §20 forbidden classes. Decision: **not in V1.**
If enabled later it must be a separate opt-in with content stripped at the source (package + timestamp
only, never text), and it must remain excluded from the AI allowlist regardless.

### 8.7 What Android cannot reliably track (must be documented in-product)

- **Per-website activity in mobile browsers.** No API. Mobile browsing appears as `com.android.chrome`
  only. Mobile web is a structural blind spot; do not fake it.
- **In-app content.** YouTube-the-app is one package; educational vs entertainment viewing is
  indistinguishable without content access. This is why classification must be probabilistic.
- **Active attention vs. screen-on idle.** A screen-on, untouched device looks identical to reading.
  Mitigated with `USER_INTERACTION` heuristics, never solved.
- **Usage while powered off.** Structurally unobservable → `DEVICE_OFFLINE`.
- **Split-screen / PiP.** Two apps may be simultaneously foreground; the model must tolerate
  overlapping sessions rather than assuming exclusivity.
- **Pre-install history.** Nothing before first run, plus the retention window at best.

### 8.8 Android module structure

```
android/
├── app/                       # Compose UI, onboarding, permission flows, health screen
└── core/
    ├── collector/             # UsageEventReader, EventMapper, CoverageTracker
    ├── db/                    # Room: EventEntity, SyncStateEntity, DAOs, migrations
    ├── sync/                  # BatchBuilder, SyncWorker, Retrofit/OkHttp client
    └── model/                 # shared event contract (mirrors backend Pydantic)
```

Room schema (local): `events(id TEXT PK, ts_utc INTEGER, type TEXT, package TEXT, payload TEXT,
seq INTEGER, batch_id TEXT NULL, synced INTEGER DEFAULT 0)`, index on `(synced, seq)`.
Retention: rows deleted 7 days after `synced = 1`. Unsynced rows are never deleted; if the local DB
exceeds 50 MB, oldest *synced* rows are pruned first and a health event is raised.

Encryption: the Room DB is app-private storage. V1 uses `EncryptedSharedPreferences` (AndroidKeystore)
for the **device token** — the highest-value secret. Full SQLCipher on the event DB is a Phase 12+
option; the threat it defends against (physical device + unlocked bootloader) is better addressed by
the device's own FDE.

---

## 9. Event Model

### 9.1 Canonical envelope (identical across all collectors)

```jsonc
{
  "event_id":    "uuidv7",           // client-generated, STABLE, the idempotency key
  "device_id":   "uuidv4",           // app-generated at install, never a hardware ID
  "seq":         182734,             // monotonic per-device counter, gap-detection
  "ts_utc":      1757740800123,      // epoch millis UTC — the ONLY stored time
  "tz_offset_min": 330,              // capture-time offset, for local rendering
  "tz_id":       "Asia/Kolkata",     // IANA zone at capture time
  "clock_flags": ["NTP_SYNCED"],     // or CLOCK_CHANGED, BOOT_RELATIVE
  "uptime_ms":   9482010,            // SystemClock.elapsedRealtime — drift correction
  "type":        "APP_FOREGROUND",
  "source":      "android",
  "payload":     { "package": "com.jetbrains.intellij" },
  "schema_v":    1
}
```

### 9.2 Event type registry

| Type | Sources | Payload |
|---|---|---|
| `APP_FOREGROUND` / `APP_BACKGROUND` | android, desktop | `package` \| `app_class` |
| `SCREEN_ON` / `SCREEN_OFF` | android | — |
| `DEVICE_LOCK` / `DEVICE_UNLOCK` | android, desktop | — |
| `USER_INTERACTION` | android | `package` |
| `DEVICE_STARTUP` / `DEVICE_SHUTDOWN` | all | — |
| `COLLECTOR_START` / `COLLECTOR_STOP` | all | `reason` |
| `IDLE_START` / `IDLE_END` | desktop, browser | `idle_ms` |
| `BROWSER_DOMAIN_FOCUS` / `BLUR` | browser | `domain` (registrable only) |
| `HEALTH` | all | `metric`, `value` |

`payload` is a strictly-typed discriminated union in Pydantic. **Unknown fields are rejected, not
ignored** (`model_config = ConfigDict(extra="forbid")`) — this is a privacy control: it prevents a
future collector version from silently smuggling new fields into the server.

### 9.3 Time model (normative)

- **Storage:** always `TIMESTAMPTZ` in UTC. Never store naive local time.
- **Rendering:** dashboard converts using the event's `tz_id`, not the viewer's browser zone.
- **Day boundaries:** a "day" is `[local 04:00, next local 04:00)` — configurable. Midnight boundaries
  split late-night sessions absurdly; 04:00 matches human sleep. Stored in `users.day_start_hour`.
- **DST:** because days are defined in local wall-clock terms over a UTC store, a 23h and a 25h day
  occur twice a year. Metrics are **rate-normalised** (per-waking-hour) wherever a total would mislead,
  and the day record stores its true `duration_seconds`.
- **Timezone change (travel):** events carry `tz_id` at capture. A day containing multiple zones is
  flagged `tz_transition = true`; day boundaries use the zone in effect at the day's start.
- **Clock drift:** every event carries `uptime_ms`. On ingest, if consecutive events from a device show
  wall-clock movement inconsistent with `uptime_ms` delta by >120 s, the server sets
  `clock_suspect = true` on the affected rows and the sessionizer prefers uptime-derived durations.
- **Ordering:** `seq` defines truth within a device. `ts_utc` may go backwards (clock change); `seq`
  never does. Sessionization sorts by `(seq)` within a device, not by timestamp.
- **Late arrival:** events arriving up to **7 days** late are accepted and trigger recomputation of the
  affected day(s). Beyond 7 days they are stored but flagged `late_beyond_window`, and the affected day
  is marked `revised = true` rather than silently rewritten.

---

## 10. Desktop Architecture (Phase 12 — DEFERRED, POST-V1)

> **Status: not in V1.** The target laptop runs GNOME on Wayland, which has no portable global
> active-window API. Per §4.5 the desktop collector is deferred, the user's session will **not** be
> switched to X11 for TimeOS, and no V1 component may depend on desktop data. This section is the
> design to be picked up later, not a V1 deliverable.

Python 3.12 agent, systemd **user** service (`~/.config/systemd/user/timeos-agent.service`,
`Restart=always`, `WantedBy=default.target`). Not root — it needs no privilege.

- Sampling: poll active window every **5 s**; emit an event only on *change* (edge-triggered, not
  level-triggered) — this keeps the event rate at roughly hundreds/day rather than 17k/day.
- Idle: X11 → `XScreenSaver` `XssQueryInfo`; threshold **180 s** → `IDLE_START`.
- Process metadata via `psutil` (process name and window class only — **never** command line, which
  routinely contains tokens and file paths).
- Local buffer: SQLite WAL at `~/.local/state/timeos/events.db`, same schema shape as Room.
- Clean shutdown: systemd `ExecStop` writes `DEVICE_SHUTDOWN`. Unclean crash leaves no marker → the
  server infers `UNOBSERVED` from the coverage gap (§14.3).

**⚠ Wayland constraint (this host is Wayland-class Ubuntu):** Wayland has **no portable global
active-window API** by design. `xdotool`/`python-xlib` work only under X11 or XWayland.
Options, in order of preference:
1. **GNOME Shell extension** exposing focused-window class over D-Bus, consumed by the agent. Reliable,
   but ties to GNOME and breaks on Shell major upgrades.
2. **X11 session** (log in with "Ubuntu on Xorg") — zero extra code, costs Wayland.
3. **Degraded mode:** no window data; still emit idle/lock/session events from `logind` D-Bus signals.
   The desktop becomes a *coverage* source without app attribution.

**Decision:** the desktop collector is deferred to Phase 12. When it is built, **(3) degraded /
coverage-only mode is the default and the guaranteed baseline**, with (1) as an optional add-on for
users who install the GNOME extension. Option (2) is **rejected outright** — the user's Ubuntu session
will not be switched to X11 for TimeOS.

**Non-negotiable honesty rule:** the agent must detect `XDG_SESSION_TYPE` and its actual attribution
capability at startup and report it in a `HEALTH` event, which populates `devices.capability_level`.
In degraded mode it emits `DEVICE_STARTUP`/`SHUTDOWN`, lock/unlock and idle events only, and the
dashboard states plainly that the laptop contributes *coverage* but not *application attribution*.
**It must never emit an app-attribution event it cannot reliably determine, and must never guess the
active application.** A fabricated attribution is worse than an honest `UNOBSERVED`.

Prohibited in the desktop agent, enforced by code review and a test asserting the event payload
allowlist: screenshots, keystrokes, clipboard, window *titles* (titles leak document names, message
content, and URLs — only window **class** is collected), file paths, process command lines.

---

## 11. Browser Extension Architecture (Phase 9)

**Target browsers: Brave, Chromium, and Firefox — all three, concurrently.** This is a verified
environment fact (§4.5), not an optional nicety, and it drives the decisions below.

### 11.1 Two engine targets, one source tree

| Target | Browsers | Background model | API namespace | Manifest |
|---|---|---|---|---|
| **Chromium** | Brave, Chromium (and Chrome/Edge if ever needed) | MV3 **service worker**, evicted after ~30 s idle | `chrome.*` (callbacks) | `manifest.chromium.json` |
| **Gecko** | Firefox | MV3 **event page** (`background.scripts`, `persistent: false`) — Firefox does **not** support `background.service_worker` | `browser.*` (promises) | `manifest.firefox.json` |

One TypeScript source tree, `webextension-polyfill` to normalise on the promise-based `browser.*`
API, and a build flag emitting two artifacts (`dist/chromium/`, `dist/firefox/`). Brave and Chromium
share a **byte-identical** build — Brave is Chromium with different defaults, not a different
extension platform, so it costs nothing extra.

**The key insight that makes this cheap:** the MV3 service-worker eviction problem (§11.3) already
forced a design where *all state lives in extension storage and every wake reconciles from
`last_seen_ts`*. That design is engine-agnostic. Firefox's event pages are strictly more forgiving
than Chromium's service workers, so code written correctly for Chromium works on Firefox unchanged.
Had the original design relied on in-memory background state, cross-browser support would have been
a rewrite; as specified, it is a build-target change.

### 11.2 Telemetry (unchanged across all three)

Permissions: `tabs`, `idle`, `storage`, `alarms`. **No `host_permissions`, no content scripts, no
`webNavigation`.** Without host permissions the extension *cannot* read page content in any engine —
the privacy guarantee is structural, not promised. A build-failing test asserts both manifests
contain neither.

- Every URL is reduced to its **registrable domain** using a bundled Public Suffix List snapshot, at
  the moment of capture, inside the background context. The full URL is never written to storage and
  never leaves the function scope. `mail.google.com/u/0/#inbox?q=...` → `google.com`.
- Attribution rule: a domain accrues time only when its tab is **active, in a focused window, and the
  browser is not idle** (`idle` API, 180 s).
- Private/incognito windows are excluded entirely, in all three browsers. The extension is not
  granted incognito access; Brave's Tor windows are covered by the same exclusion.
- Buffer in IndexedDB; flush every 5 min or 200 events.

### 11.3 Background-lifetime reconciliation (required on Chromium, harmless on Firefox)

All state lives in `storage.session`/`storage.local` — never in background globals. On every wake the
background context reconciles: if `last_seen_ts` is older than the alarm period, close the open
interval at `last_seen_ts` and open an `UNOBSERVED` gap. A 1-minute `alarms` heartbeat bounds gap
size. Firefox's event pages are evicted far less aggressively, but the same code path runs there and
correctly handles browser crashes and forced restarts.

### 11.4 Three browsers running at once — the real architectural question

Each browser install is enrolled as its **own TimeOS device** with its own `device_id` and its own
device token. Three browsers therefore produce three `devices` rows with
`platform = "browser"` and `browser_family ∈ {brave, chromium, firefox}`.

**Why this does not double-count:** only one window on the machine holds OS focus at any moment. Each
extension independently observes `windows.onFocusChanged → WINDOW_ID_NONE` when *its* browser loses
focus, and stops accruing. So when the user switches from Brave to Firefox, Brave closes its interval
and Firefox opens one. The existing §11.2 attribution rule handles the multi-browser case correctly
without any cross-browser coordination — which is fortunate, because no such coordination is possible
between sandboxed extensions.

**Where it can still overlap:** focus-change events are delivered asynchronously and the two browsers
have independent clocks-of-record, so adjacent intervals can overlap by a few hundred milliseconds,
and a browser killed without a focus-loss event can leave an interval open. The merge layer
(§14.3, Phase 10) therefore applies **browser arbitration**:

1. Sort all browser-sourced intervals by start time across all three devices.
2. Where intervals from different `browser_family` values overlap, the **later-starting interval
   wins** from its start instant and the earlier one is truncated — a focus gain is a more reliable
   signal than a focus loss, because the loss event may never have been delivered.
3. An interval left open with no close event is truncated at `last_seen_ts` (heartbeat bound) and
   marked `truncated = true`, exactly as §14.1 does for app sessions.
4. Total browser time is the **union** of the arbitrated intervals, never the sum. A property test
   asserts that total browser time on any day never exceeds total screen-on time.

**Reporting:** domain totals aggregate across all three browsers by default — `github.com` is
`github.com` regardless of where you opened it. `browser_family` is retained on
`browser_sessions` so per-browser breakdown is available, and so that a browser-specific collector
outage is diagnosable on the System Health page rather than appearing as a mysterious drop in web
time. **`browser_family` is not in the AI allowlist** (§20.3): which browser you use is not
behaviourally interesting and is mildly fingerprinting.

### 11.5 Distribution — the genuine operational cost

This is where three browsers actually hurt, and it must be planned for:

| Browser | Install path | Constraint |
|---|---|---|
| Chromium | `chrome://extensions` → Load unpacked | Unpacked extensions survive restarts; a dev-mode warning bubble may appear on each launch |
| Brave | `brave://extensions` → Load unpacked | Same as Chromium |
| Firefox | **Requires a signed `.xpi`** | `about:debugging` temporary install is wiped on every browser restart — unusable for continuous telemetry |

**Firefox decision:** submit the extension to AMO for **unlisted (self-distribution) signing**, which
returns a signed `.xpi` installable permanently without the add-on being publicly listed. This is
free but involves an automated review and a turnaround delay, so **start the signing process early in
Phase 9 rather than at the end of it.** The fallback — Firefox Developer Edition or ESR with
`xpinstall.signatures.required = false` — is documented but not recommended, since it means changing
the user's browser channel for a side project (cf. ADR-016's reasoning on not changing the
environment to suit the tool).

### 11.6 Optional local-only raw URLs

Raw URLs may be stored **in IndexedDB on-device only**, per browser, behind an explicit toggle. Never
synced, never in any AI path, default off, and the toggle state is independent per browser install.

---

## 12. Backend Architecture

**FastAPI monolith**, Python 3.12, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, uvicorn behind Caddy.

### 12.1 Process topology

| Process | Role |
|---|---|
| `api` | HTTP: ingest, dashboard reads, corrections, goals |
| `worker` | APScheduler in-process: sessionization, analytics, AI jobs |
| `db` | PostgreSQL 16 |
| `caddy` | TLS termination (automatic Let's Encrypt), reverse proxy |
| `dashboard` | Next.js 15 (standalone output) |

**Redis is deliberately excluded from V1.** Justification: a single user generates on the order of
10³–10⁴ events/day. There is no queue depth, no cache pressure, and no fan-out. APScheduler plus
Postgres advisory locks covers scheduling and mutual exclusion. Redis is added only when a measured
need appears (see ADR-011).

### 12.2 Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/v1/devices/enroll` | enrollment code (one-time, 10-min TTL) | Returns device token |
| `POST` | `/v1/devices/token/rotate` | device token | Rotation; old token valid 24 h |
| `POST` | `/v1/ingest/batch` | device token | **Idempotent.** ≤1000 events, ≤1 MB gzip |
| `GET`  | `/v1/sync/state` | device token | Server's last-seen `seq`, for gap detection |
| `GET`  | `/v1/days/{date}` | session | Metrics + timeline |
| `GET`  | `/v1/days/{date}/timeline` | session | Coverage-aware intervals |
| `GET`  | `/v1/trends?window=7\|30\|90` | session | Baselines |
| `GET`  | `/v1/insights/{date}` | session | AI analysis if present |
| `POST` | `/v1/feedback/classification` | session | User correction |
| `GET/POST/PATCH` | `/v1/goals` | session | Goal CRUD |
| `POST` | `/v1/ai/analyze/{date}` | session | Manual trigger (rate-limited 5/day) |
| `GET`  | `/v1/health` \| `/v1/health/collectors` | session | Observability |
| `POST` | `/v1/export` \| `DELETE /v1/data` | session + re-auth | Export / hard delete |

### 12.3 Ingestion contract (idempotency is non-negotiable)

```
POST /v1/ingest/batch
Authorization: Bearer <device_token>
Idempotency-Key: <batch_id uuidv7>

{ "batch_id": "...", "device_id": "...", "seq_from": 1000, "seq_to": 1249,
  "events": [ ...envelopes... ] }
```

Server algorithm:
1. `INSERT INTO sync_batches (batch_id, ...) ON CONFLICT (batch_id) DO NOTHING`.
   Zero rows affected → this batch was already processed → **return the stored prior response
   verbatim, 200.** (Replay must be indistinguishable from first delivery.)
2. Validate every envelope. **Any invalid event fails the whole batch, 422** with per-index errors.
   Partial acceptance is forbidden: it would desynchronise the client's `seq` cursor.
3. `INSERT ... ON CONFLICT (event_id) DO NOTHING` into `raw_events`.
4. Update `devices.last_seq`, detect gaps (`seq_from > last_seq + 1` → record `seq_gap`).
5. Mark the day(s) touched as `dirty` for recomputation.
6. Respond `{accepted, duplicates, batch_id, server_seq, next_expected_seq}`.

Two independent idempotency layers (`batch_id` **and** `event_id`) because the failure modes differ: a
retried batch is caught by the former, a client that regenerates batches after a crash by the latter.

---

## 13. Database Architecture

PostgreSQL 16. All timestamps `TIMESTAMPTZ`. All IDs UUID (v7 where ordering helps).
`users` exists from day one with a single row — retrofitting multi-tenancy is far more expensive than
carrying an unused foreign key.

```sql
-- identity & devices -------------------------------------------------
users(id PK, email, password_hash, timezone, day_start_hour DEFAULT 4,
      created_at, settings JSONB)

devices(id PK, user_id FK, name, platform,                 -- android|desktop|browser
        browser_family,                                    -- brave|chromium|firefox, NULL otherwise
        token_hash, token_created_at, token_rotated_at,
        last_seen_at, last_seq BIGINT DEFAULT 0,
        app_version, os_version, capability_level, revoked_at)

-- ingestion ----------------------------------------------------------
sync_batches(batch_id PK, device_id FK, received_at, event_count,
             seq_from, seq_to, response JSONB, status)      -- idempotency ledger

raw_events(id PK,                                           -- = client event_id
           device_id FK, user_id FK, seq BIGINT, ts_utc TIMESTAMPTZ,
           tz_offset_min SMALLINT, tz_id TEXT, uptime_ms BIGINT,
           type TEXT, payload JSONB, clock_suspect BOOL DEFAULT false,
           schema_v SMALLINT, ingested_at TIMESTAMPTZ)
  PARTITION BY RANGE (ts_utc);                              -- monthly partitions
  INDEX (user_id, ts_utc), (device_id, seq)

-- sessionization -----------------------------------------------------
device_coverage(id PK, device_id FK, start_ts, end_ts,
                state TEXT)      -- TRACKED | IDLE | UNOBSERVED | DEVICE_OFFLINE
  EXCLUDE USING gist (device_id WITH =, tstzrange(start_ts,end_ts) WITH &&)

app_sessions(id PK, user_id, device_id, app_key, app_label,
             start_ts, end_ts, duration_s, interaction_count,
             screen_state, source_event_ids UUID[])

browser_sessions(id PK, user_id, device_id, domain, browser_family,   -- brave|chromium|firefox
                 start_ts, end_ts, duration_s, truncated BOOL DEFAULT false,
                 source_event_ids UUID[])

-- intelligence -------------------------------------------------------
activity_categories(id PK, user_id, key, label, parent_id FK, is_system,
                    default_valence NUMERIC)                -- soft prior, NOT good/bad

activities(id PK, user_id, start_ts, end_ts, duration_s,
           category_id FK, intent TEXT, confidence NUMERIC,
           classification_source TEXT,        -- rule|history|user|ai_assist
           evidence JSONB,                    -- {sessions:[], signals:{}, rules:[]}
           devices TEXT[], goal_id FK NULL, goal_confidence NUMERIC,
           superseded_by UUID NULL)           -- corrections create a new row

app_classifications(user_id, app_key, category_id, confidence,
                    source, sample_count, updated_at, PRIMARY KEY(user_id,app_key))

-- personal context ---------------------------------------------------
goals(id PK, user_id, name, priority SMALLINT, target_minutes_per_week,
      target_behavior TEXT, active_from, active_to, archived_at)
goal_activity_mapping(goal_id FK, category_id FK NULL, app_key TEXT NULL,
                      weight NUMERIC)
working_hours(user_id, weekday SMALLINT, start_local TIME, end_local TIME)
user_feedback(id PK, user_id, target_type, target_id, correction JSONB,
              created_at, applied_at)

-- analytics ----------------------------------------------------------
daily_metrics(user_id, local_date, PRIMARY KEY(user_id, local_date),
              day_start_utc, day_end_utc, duration_seconds,
              observed_s, tracked_s, idle_s, unobserved_s, offline_s,
              coverage_ratio NUMERIC,          -- ← gates every other metric
              screen_time_s, active_time_s,
              deep_work_s, focused_work_s, shallow_work_s,
              communication_s, learning_s, entertainment_s, social_s,
              distraction_s, unknown_s, unknown_ratio,
              context_switches INT, switches_per_hour NUMERIC,
              interruptions INT, fragmentation_index NUMERIC,
              longest_focus_s, avg_focus_s, focus_session_count,
              unlock_count INT, tz_transition BOOL, revised BOOL,
              computed_at, pipeline_version)

weekly_metrics(user_id, iso_year, iso_week, PRIMARY KEY(...), <aggregates>, deltas JSONB)

behavioral_patterns(id PK, user_id, pattern_type, first_seen, last_seen,
                    occurrences INT, strength NUMERIC, support JSONB,
                    status TEXT)               -- candidate|confirmed|dismissed

-- AI -----------------------------------------------------------------
ai_analysis(id PK, user_id, scope, scope_key,               -- day|week|month
            context_hash, context_version, provider, model,
            prompt_version, day_score SMALLINT, summary TEXT,
            raw_output JSONB, validation_status, token_in, token_out,
            cost_usd NUMERIC, latency_ms, created_at)

ai_insights(id PK, analysis_id FK, kind,                    -- win|problem|pattern|recommendation
            claim TEXT, evidence JSONB, confidence NUMERIC,
            evidence_verified BOOL, epistemic_status TEXT,  -- FACT|INFERENCE|HYPOTHESIS
            user_reaction TEXT NULL)

privacy_audit_events(id PK, user_id, occurred_at, actor, action,
                     context_hash, field_count, allowlist_version,
                     rejected_fields TEXT[], outcome, payload_digest)
```

**Relationships:** `users 1─N devices 1─N raw_events`; `raw_events N─1 app_sessions` (via
`source_event_ids`, preserving provenance); `app_sessions N─1 activities`; `activities N─1 goals`
(weak, confidence-weighted); `daily_metrics` derived from `activities` + `device_coverage`;
`ai_analysis 1─N ai_insights`; `privacy_audit_events` references nothing personal (digests only).

**Retention defaults (configurable):** `raw_events` 180 days (partition drop), sessions 2 years,
`activities`/`daily_metrics` indefinite, `ai_analysis` indefinite, `privacy_audit_events` 2 years.
Rationale: raw events are the highest-risk, lowest-long-term-value asset. Aggregates carry the insight.

**Migrations:** Alembic, one head, forward-only in production. Every migration must be tested against a
restored production snapshot before deploy. Never edit an applied migration.

---

## 14. Sessionization Model

Runs per device, ordered by `seq`, idempotent and re-runnable: the sessionizer is a **pure function**
of `(events, config)` and always deletes-then-rewrites the affected window. Re-running must produce
byte-identical output (this is a property test).

### 14.1 App session construction

1. `APP_FOREGROUND(pkg)` opens a session.
2. Session closes on: `APP_BACKGROUND(pkg)`, `APP_STOPPED(pkg)`, `SCREEN_OFF`, `DEVICE_LOCK`,
   `DEVICE_SHUTDOWN`, another app's `APP_FOREGROUND`, or `COLLECTOR_STOP`.
3. **Unterminated sessions** (crash, kill, retention loss) close at `min(last_known_event,
   start + MAX_SESSION)` where `MAX_SESSION = 4 h`, and are marked `truncated = true`.
   They are *never* extended to the present.
4. Sessions shorter than **3 s** are dropped as transitions (launcher flicks, notification shade).
5. Sessions of the same app separated by a gap `< 30 s` merge (app-switcher bounce) — but the switch
   still counts toward context-switch metrics, because the attention *did* move.
6. Split-screen produces overlapping sessions; duration is **not** divided. Wall-clock day totals use
   `device_coverage`, not the sum of session durations. (Summing overlapping sessions is the classic
   bug that yields 27-hour days.)

### 14.2 Idle discrimination
Screen on + zero `USER_INTERACTION` for `IDLE_THRESHOLD` (default 5 min on mobile, 3 min desktop)
→ `IDLE`. Video/media packages are exempt via a user-editable allowlist, because passive watching is
genuine consumption. Idle time is excluded from `active_time_s` and from focus-session continuity, but
**does not break** a focus session shorter than 5 minutes (a bathroom break is not a context switch).

### 14.3 Coverage reconstruction (the honesty engine)

For each device, build a gapless interval cover of the day:

| Condition | State |
|---|---|
| Events present, screen on, interaction | `TRACKED` |
| Screen on, no interaction past threshold | `IDLE` |
| Screen off / locked, collector alive | `TRACKED` (as screen-off) |
| `DEVICE_SHUTDOWN` → `DEVICE_STARTUP` | `DEVICE_OFFLINE` |
| Gap ≥ 2× poll interval with no shutdown marker | `UNOBSERVED` |
| Permission revoked / collector stopped | `UNOBSERVED` |

`coverage_ratio = (tracked + idle) / day_duration`. **Every derived metric is annotated with the
coverage ratio of its window, and any metric computed on `coverage_ratio < 0.6` is rendered as a
range, not a point value, and is excluded from trend baselines.** This single rule is what prevents the
entire system from lying on days when a device was off.

Cross-device merge: the phone and laptop can be simultaneously `TRACKED`. Day totals use the **union**
of tracked intervals for "observed time" and keep per-device totals separately. Simultaneous phone +
laptop use is itself a signal and is recorded as `dual_device_s`.

---

## 15. Activity Intelligence

Sessions → `activities`. Classification is **contextual, probabilistic, and correctable**. No app is
intrinsically good or bad.

### 15.1 Signal set
`app_key/domain`, session duration, time of day, day of week, preceding and following activity,
switch density in the surrounding window, whether within declared working hours, co-occurring device
activity, historical user corrections for this app in this context, declared goals active now.

### 15.2 Layered classifier (cheap → expensive, first confident wins)

| Layer | Mechanism | Typical confidence |
|---|---|---|
| L0 User rule | Explicit user mapping (`app X in context Y = Z`) | 1.00 (terminal) |
| L1 Learned prior | Empirical distribution from this user's corrections, ≥5 samples | 0.75–0.95 |
| L2 Seed catalogue | Curated package→category priors shipped with the app | 0.55–0.80 |
| L3 Context modifier | Adjusts L1/L2 using neighbours, time, duration | ±0.25 |
| L4 Unknown | Nothing exceeds `CONFIDENCE_FLOOR = 0.55` | → `Unknown` |

L3 examples (all evidence-logged):
- `IDE → Terminal → Browser(github.com) → IDE` within 20 min → collapses to one `Development`
  activity, confidence **boosted**, because the cluster is coherent.
- `YouTube` for 45 min *followed within 15 min by* ≥30 min of Development → `Learning`, confidence
  0.68, evidence `["followed_by_development"]`.
- The same `YouTube` at 23:40 with no subsequent work → `Entertainment`, confidence 0.72.
- Social app, 8 opens in 30 min, ≤90 s each → `Distraction` (habitual checking), confidence 0.8.
- Social app, one 25-min session at 20:00 → `Social`, confidence 0.7 — *not* distraction.

**`Unknown` is a success state, not a failure.** `unknown_ratio` is reported on the dashboard; the
correct response is to ask the user, not to guess. Target: `unknown_ratio < 0.15` after 30 days of
corrections; it will legitimately be higher in week one.

### 15.3 Taxonomy
Two-level, user-extensible, stored in `activity_categories` (not in code):
`Work{DeepWork, FocusedWork, Development, Research, Writing, Meetings, Admin}`,
`Growth{Learning, Reading, Practice}`, `Connection{Communication, Social}`,
`Life{Personal, Exercise, Health, Errands}`, `Consumption{Entertainment, Browsing}`,
`System{Idle, Unobserved, Offline, Unknown}`.
System categories are immutable; everything else can be renamed, merged, or added.

### 15.4 Correction loop
A user correction writes `user_feedback`, inserts a **new** `activities` row and sets `superseded_by`
on the old one (history is never destroyed), updates `app_classifications` (Bayesian update with a
recency half-life of 60 days), and schedules recomputation of the affected day. Corrections apply
retroactively only when the user explicitly opts in per correction — silently rewriting history would
make trend lines untrustworthy.

---

## 16. Focus Engine

Explicit definitions (all thresholds are config, not literals):

- **Context switch** — attention moves to a different `app_key`/`domain` with a *different category*.
  Same-category switches (IDE↔terminal) are **tool switches**, counted separately and do not break focus.
- **Interruption** — an out-of-category session of `< 120 s` embedded in a focus candidate, or an
  incoming-communication session. Counted; breaks focus only if longer than `INTERRUPT_TOLERANCE = 90 s`
  or if two occur within 5 minutes.
- **Focus session** — ≥ **15 min** of continuous same-category work-type activity, with
  ≤ 1 tolerated interruption per 15 min, and ≥ 80 % of wall time attributed (not idle).
- **Deep work session** — ≥ **45 min**, **zero** tolerated interruptions beyond one, switch rate
  ≤ 2/hour, entirely within a category the user classifies as deep-capable, and ≥ 90 % attributed.
- **Fragmented work** — work-category time not contained in any focus session.

**Focus quality score** (0–1), per session:
```
q = 0.35·min(duration/60min, 1)
  + 0.25·(1 − interruptions/max(1, duration_min/15))
  + 0.20·(1 − min(switches_per_hour/6, 1))
  + 0.20·goal_alignment_weight
```
**Daily fragmentation index** (0–1, higher = worse):
```
F = 0.5·min(switches_per_hour/12, 1)
  + 0.3·(1 − focused_time/max(work_time, 1))
  + 0.2·(1 − median_work_block_min/30 clamped to [0,1])
```
Both are computed **only on windows with `coverage_ratio ≥ 0.6`**, and both are recorded with their
formula version so historical values remain interpretable after tuning.

---

## 17. Distraction Engine

Distraction is a **pattern in the sequence**, never a property of an app.

Detectors (each emits a `behavioral_patterns` row with `strength` and `support`):

| Pattern | Rule (v1) |
|---|---|
| `DISTRACTION_BURST` | ≥3 non-work sessions within 15 min, total ≥5 min |
| `HABITUAL_CHECKING` | Same app opened ≥5× in 30 min, median session ≤90 s |
| `POST_TASK_AVOIDANCE` | Work session ≥20 min ends → non-work ≥10 min begins within 3 min, **and** the work category does not resume within 30 min |
| `TASK_START_AVOIDANCE` | Working hours begin → ≥10 min non-work before first work session, on ≥4 of 7 days |
| `TIME_OF_DAY_SINK` | A 30-min local slot shows non-work share ≥2σ above that slot's 30-day mean |
| `SWITCH_STORM` | ≥20 context switches in 20 min |
| `LATE_NIGHT_DRIFT` | ≥30 min consumption after the user's declared wind-down hour, ≥3×/week |

**Epistemic discipline — enforced in the schema:**

| Level | Meaning | Example |
|---|---|---|
| `FACT` | Directly measured | "47 context switches; longest focus 22 min." |
| `INFERENCE` | Deterministic rule over facts | "Fragmentation index 0.71 — above your 30-day mean of 0.48." |
| `HYPOTHESIS` | Interpretive, requires user confirmation | "This pattern *may* indicate avoidance of the API refactor." |

Every surfaced statement carries its level. Hypotheses render with distinct styling and an explicit
"Does this match your experience?" control whose answer updates `behavioral_patterns.status`.
A pattern stays `candidate` until it has ≥3 occurrences across ≥3 distinct days; only `confirmed`
patterns enter the AI context. This prevents one bad Tuesday from becoming a "behavioural pattern".

---

## 18. Goal Alignment Engine

Goals: `name`, `priority` (1–5), `target_minutes_per_week`, `target_behavior` (free text, used only for
AI interpretation), `active_from/to`. Mapped to categories and/or apps with `weight ∈ [0,1]`.

```
aligned_minutes(goal) = Σ over activities:
    duration_min × mapping_weight × activity.confidence × time_window_factor
```
`time_window_factor = 1.0` inside declared working hours for work-type goals, `0.85` outside
(uncertainty penalty, not a moral one).

Reported per goal: `target`, `aligned` (point estimate), `range` (±, derived from the confidence
distribution and coverage), `attainment %`, `trend vs 4-week mean`.

**Mandatory honesty:** alignment is an **estimate**, always rendered with its uncertainty band and its
coverage ratio, and always labelled `INFERENCE`. When `unknown_ratio > 0.25`, the UI states explicitly:
"X % of your time is unclassified; alignment figures are lower bounds." Unmapped time is reported as
`unallocated`, never silently redistributed across goals.

---

## 19. Personal Context Engine

Stores everything the user declares: goals, active projects, priorities, working hours per weekday,
wind-down hour, focus-capable categories, deep-work-capable apps, custom taxonomy, per-app rules,
correction history, and habits ("gym Tue/Thu 07:00").

Consumed by: the context modifier layer (L3), the focus engine (working hours), the distraction engine
(wind-down hour), goal alignment, and the AI context (as declarative text the user themselves wrote).

Bootstrapping: a 10-question onboarding sets timezone, day start, working hours, 1–3 goals, and
deep-work apps. Everything else is learned from corrections. **The system must be useful on day one
with zero context** — all context fields have safe defaults, and the classifier degrades to L2 priors
with honest `Unknown` output rather than refusing to run.

---

## 20. Privacy Architecture

### 20.1 The boundary

```
raw_events ─► analytics ─► aggregates ─╫═► PrivacyGate ═► AIContext ─► LLM
                                       ▲
                            no path around this
```

### 20.2 Three independent enforcement mechanisms (defence in depth)

**1. Structural isolation.** `timeos/ai/` may import **only** from `timeos/schemas/ai_context.py` and
`timeos/privacy/`. It has no SQLAlchemy session, no engine, no DSN, no `models` import. Enforced by an
`import-linter` contract in CI:

```ini
[importlinter:contract:ai-isolation]
name = AI layer may not touch data layer
type = forbidden
source_modules = timeos.ai
forbidden_modules = timeos.models, timeos.db, sqlalchemy, psycopg
```
A build that violates this **fails**. This is the primary control; the others are backstops.

**2. Allowlist + schema validation.** The `AIContext` Pydantic model uses `extra="forbid"`. The gate
additionally walks the serialized payload and asserts every leaf key against a versioned explicit
allowlist. Anything unlisted → `PrivacyViolation` raised, request aborted, audit row written. A new
field cannot reach the LLM without a deliberate allowlist edit, which is a reviewable diff.

**3. Content scanning.** Before egress the gate scans all string values for: URLs/schemes, `@`
(email-shaped), long digit runs (phone/card-shaped), high-entropy tokens (≥32 chars, entropy > 3.5),
file-path separators, and any string longer than `MAX_FREE_TEXT = 500` chars. Detection → abort.
Free-text is permitted **only** from fields the user authored themselves (goal names, category labels),
and even those are length-capped and scanned.

### 20.3 Allowlist (v1, normative)

**ALLOWED:** date/week identifiers; day duration and coverage figures; category durations and
percentages; focus statistics (counts, longest, average, quality); context-switch and interruption
counts; fragmentation index; `unknown_ratio`; app/domain entries as **`{rank, category, duration_bucket,
session_count, label_type}`** where the label is either a user-declared alias or the generic category —
**never a raw package name or domain by default** (see 20.4); goal name (user-authored, ≤60 chars),
priority, target, aligned estimate, uncertainty; confirmed `behavioral_patterns` as
`{pattern_type, occurrences, strength}`; historical baselines and deltas; device *types* and their
coverage ratios; user-declared working hours and wind-down hour.

**FORBIDDEN — never, under any configuration:** raw events or any row from `raw_events`; message,
notification, or clipboard content; contact names; passwords, tokens, credentials, DSNs; file paths;
document names; window titles; screenshots or any image; raw URLs, paths, or query strings;
device identifiers, IPs, MAC addresses; the user's email or account identifiers; free text the user did
not author; any database identifier (UUIDs) — the context is keyed by rank and label only.

### 20.4 App/domain identity decision
Even a package list is disclosive (a dating app, a health app, a job-search site). **Default:** the AI
sees category + rank + duration bucket only (`"#1 Development, 2–3 h, 41 sessions"`). An explicit
opt-in setting, `ai_share_app_names`, allows sending package names for better interpretation. Off by
default. The setting's state is recorded in every `privacy_audit_events` row so past analyses remain
attributable to the policy in force.

### 20.5 Audit
Every gate invocation writes `privacy_audit_events`: timestamp, actor, allowlist version, field count,
rejected fields, outcome, and a SHA-256 digest of the outbound payload. The digest allows proving after
the fact exactly what was sent **without storing it again**. The audit table is queryable from the
dashboard's Privacy page, which also renders the exact last payload sent (reconstructable from the
context hash + stored aggregates).

### 20.6 Prompt-injection containment
The LLM's input contains user-authored strings (goal names). It returns JSON that is schema-validated
and **evidence-verified** (§23.3) before storage. The LLM has **no tools, no function calling, no
network, no DB** — so the worst achievable outcome of injection is a misleading insight shown to the
user, which is bounded and recoverable. No AI output is ever executed, rendered as HTML, or used to
parameterise a query.

---

## 21. AI Context Builder

Deterministic, versioned, hash-addressed. Same inputs → same context → same `context_hash` → cached
analysis reused instead of a new LLM call (a direct cost control).

```jsonc
{
  "context_version": "1.0",
  "scope": "day", "date": "2026-09-13", "weekday": "Saturday",
  "data_quality": {
    "coverage_ratio": 0.87, "unknown_ratio": 0.12,
    "devices_reporting": ["android","desktop"],
    "unobserved_minutes": 95, "offline_minutes": 0,
    "caveats": ["laptop unobserved 13:10–14:45"]
  },
  "totals": { "day_minutes": 1440, "observed_minutes": 1252,
              "screen_minutes": 431, "active_minutes": 388 },
  "categories": [ {"category":"Development","minutes":186,"share":0.43,"sessions":22,
                   "avg_confidence":0.88} ],
  "focus": { "sessions":4, "deep_sessions":1, "longest_minutes":52,
             "average_minutes":24, "total_focus_minutes":96,
             "avg_quality":0.61, "fragmentation_index":0.58,
             "context_switches":47, "switches_per_hour":6.1, "interruptions":13 },
  "time_of_day": [ {"slot":"09:00-12:00","focus_minutes":62,"distraction_minutes":18} ],
  "top_attention": [ {"rank":1,"category":"Development","bucket":"2-3h","sessions":22} ],
  "goals": [ {"name":"Build","priority":1,"target_weekly_minutes":1200,
              "aligned_minutes_today":186,"uncertainty":28,"week_attainment":0.41} ],
  "patterns": [ {"type":"POST_TASK_AVOIDANCE","occurrences":3,"strength":0.66,
                 "status":"confirmed"} ],
  "baselines": { "window_days":30, "valid_days":26,
                 "screen_minutes_mean":452, "deep_work_minutes_mean":61,
                 "fragmentation_mean":0.48, "today_vs_mean":{"fragmentation":"+0.10"} }
}
```

Rules: no UUIDs, no raw names, no free text beyond user-authored labels, all durations in whole
minutes, all shares rounded to 2 dp, arrays capped (categories ≤15, patterns ≤10, goals ≤10) to bound
token cost. The builder is a pure function with a golden-file test.

---

## 22. LLM Safety Rules

1. The LLM receives **only** a validated `AIContext`. No tools, no functions, no retrieval, no DB.
2. The LLM **must not compute**. If a number is not in the context, it may not appear in the output —
   enforced post-hoc by §23.3, not by asking nicely.
3. Output must be valid JSON against `AIAnalysisOutput`. Invalid → one repair attempt with the
   validation errors appended → second failure → **discard, mark `validation_status = failed`, show the
   deterministic dashboard without AI narrative.** Never store unvalidated output.
4. Every insight must carry `claim`, `evidence` (referencing context fields by name), `confidence`,
   and `epistemic_status`.
5. Behavioural interpretations must be `HYPOTHESIS`, never `FACT`.
6. When `coverage_ratio < 0.6` or `unknown_ratio > 0.3`, the model is instructed to state the data
   limitation first and lower all confidences; a validator rejects output whose max confidence exceeds
   `0.7` under those conditions.
7. No medical, psychiatric, or diagnostic language. A rejection list is applied to output strings.
8. No moralising. Tone: an analyst reporting findings, not a coach issuing verdicts.
9. Rate limit: 1 automatic daily call, 1 weekly, 1 monthly; manual triggers capped at 5/day.
10. Provider abstraction (`LLMProvider` protocol: `complete(messages, schema) -> StructuredResult`)
    with `AnthropicProvider`, `OpenAIProvider`, `OllamaProvider`, and `NullProvider`. `NullProvider`
    is used in all tests and whenever no key is configured — the system must run with **zero** AI
    configuration.
11. Prompt and schema versions are stored on every `ai_analysis` row so results remain interpretable
    after prompt changes.

---

## 23. AI Output Schema

### 23.1 Shape
```jsonc
{
  "day_score": 68,                       // 0-100, must be justified by cited fields
  "score_rationale": "…",
  "summary": "…",                        // ≤ 600 chars
  "data_caveats": ["laptop unobserved 13:10–14:45"],
  "wins":            [Insight],          // ≤ 4
  "problems":        [Insight],          // ≤ 4
  "patterns":        [Insight],          // ≤ 4
  "distractions":    [Insight],          // ≤ 4
  "goal_alignment":  [Insight],          // ≤ 5
  "recommendations": [Recommendation],   // ≤ 3
  "tomorrow_priorities": ["…"],          // ≤ 3
  "overall_confidence": 0.0-1.0
}

Insight { claim, evidence: {fields: [ctx paths], values: {…}, narrative},
          confidence, epistemic_status: FACT|INFERENCE|HYPOTHESIS }

Recommendation { action, rationale, expected_effect, effort: low|med|high,
                 measurable_check, confidence }
```

### 23.2 Example
```
claim:      "Your biggest issue today was fragmentation."
evidence:   fields ["focus.context_switches","focus.average_minutes",
                    "baselines.fragmentation_mean"]
            values {context_switches: 51, average_minutes: 18, baseline: 0.48}
confidence: 0.91
status:     INFERENCE
```

### 23.3 Anti-fabrication validator (mandatory, automated)
After schema validation and before persistence:
1. Every `evidence.fields` path **must resolve** in the source `AIContext`. Unresolvable → reject.
2. Every numeric literal appearing in `claim`/`narrative` is extracted by regex and must match a value
   present in the context within 2 % tolerance. Unmatched number → reject the insight (not the whole
   analysis) and mark `evidence_verified = false`.
3. `day_score` must be within ±15 of a deterministic reference score computed by the analytics engine;
   outside that band → reject the score, keep the narrative.
4. Any insight with `epistemic_status = FACT` whose evidence is not a directly measured field is
   downgraded to `INFERENCE` automatically.
5. Confidence ceiling enforcement per §22.6.

Insights failing (1) are dropped; the analysis is stored with the survivors and a
`validation_status = partial` marker shown in the UI.

---

## 24. Historical Intelligence

- **Baselines** over rolling 7/30/90-day windows, computed **only from days with
  `coverage_ratio ≥ 0.7`** (`valid_days` is reported alongside every baseline so the user knows how
  much history supports it).
- Robust statistics: median and MAD, not mean and σ, because a single 14-hour travel day would
  otherwise wreck the baseline. (Mean is additionally reported for familiarity.)
- Metrics tracked: screen time, active time, deep-work minutes, focus-session count and length,
  fragmentation, context switches/hour, distraction minutes, unknown ratio, per-category minutes,
  best focus window (30-min slot with max focus minutes), worst distraction window, goal attainment.
- **Change detection:** a metric is flagged as a trend change when the last 7 days' median differs from
  the preceding 21 days' median by > 1.5 MAD **and** ≥5 valid days exist in the recent window.
  Trends are never declared from fewer than 14 valid days total.
- **Day-of-week normalisation:** Saturday is compared with Saturdays, not with the all-days mean.
- The daily AI prompt always includes baselines so that judgement is *relative*, not absolute.
- Weekly analysis runs Monday 06:00 local; monthly on the 1st. Both reuse the same gate and validator.

---

## 25. Dashboard Architecture

Next.js 15 (App Router), TypeScript, Tailwind, server components for data fetching, Recharts for
visualisation, TanStack Query for client mutations. Session-cookie auth (httpOnly, SameSite=Strict) —
**the dashboard never holds a device token**.

Views:
1. **Today** — Time Quality Score, screen time, deep work, productive time, distraction, fragmentation,
   each with its 30-day baseline delta and a coverage badge.
2. **Timeline** — horizontal band per device plus a merged band; `UNOBSERVED` rendered as hatched grey
   and `DEVICE_OFFLINE` as solid grey, both explicitly labelled. Never white space, never zero.
3. **Where Time Went** — category treemap + app/domain table with correction affordance inline.
4. **Focus** — session list, longest session, best focus window, interruption timeline.
5. **Distractions** — detected patterns with `FACT/INFERENCE/HYPOTHESIS` badges and confirm/dismiss.
6. **Goals** — target vs aligned with uncertainty bands and unallocated time shown honestly.
7. **AI Diagnosis** — narrative with every claim expandable to its evidence; a visible "AI unavailable"
   state that still shows all deterministic content.
8. **Recommendations** — actions with measurable checks; each can be accepted and tracked.
9. **Historical** — 7/30/90-day charts, trend-change callouts, day-of-week heatmap.
10. **System Health** — collector uptime, sync lag, coverage per device, unknown ratio, AI cost.
11. **Privacy** — the exact last AI payload, audit log, allowlist version, export and delete controls.

**Universal UI rule:** every metric renders its coverage context. A number without a coverage badge is
a bug. Low-coverage metrics render as ranges in a muted style.

---

## 26. Offline-First Synchronization

```
Collect → Local durable store → Pending queue → Batch → POST → 2xx ACK → mark synced → prune
```

- **Batching:** ≤1000 events or ≤1 MB gzipped, whichever first. Flush when the queue exceeds 200
  events or 15 minutes have elapsed, on unmetered network only by default (`sync_on_metered` setting).
- **Ordering:** batches are sent strictly in `seq` order; a failed batch blocks later ones. Out-of-order
  delivery is therefore impossible in the happy path, and tolerated by the server regardless.
- **Retry:** exponential backoff 30 s → 1 m → 5 m → 15 m → 1 h, capped, with ±20 % jitter.
- **ACK semantics:** only `2xx` marks events synced. `4xx` (except 429) means *do not retry this
  payload* — the batch is quarantined into a `failed_batches` local table and surfaced in-app; retrying
  a permanently-invalid batch forever is a classic stuck-queue bug. `5xx`/timeout → retry.
- **Gap detection:** client sends `seq_from`; server compares to `devices.last_seq` and returns
  `next_expected_seq`. A gap means data was lost on the device (pruned or DB corruption) and is
  recorded as `UNOBSERVED`, not silently ignored.
- **Backpressure:** if unsynced local rows exceed 200 000, the collector keeps collecting but raises a
  health warning; it never stops collecting to protect sync.
- **Clock:** the server records `ingested_at` independently of the client's `ts_utc` so drift is always
  measurable after the fact.

---

## 27. Failure Recovery

| # | Scenario | Behaviour |
|---|---|---|
| 1 | Phone loses internet | Collection continues; events queue in Room; sync resumes on connectivity. No data loss until the 7-day OS retention window is threatened. |
| 2 | Phone battery dies | Events up to the last poll are in Room. Gap between last poll and shutdown → `UNOBSERVED` (≤15 min). On boot, `DEVICE_STARTUP` closes the interval. |
| 3 | Phone restarts | `BOOT_COMPLETED` re-enqueues WorkManager; catch-up drain covers the OS-buffered period; the off period is `DEVICE_OFFLINE` via startup/shutdown events. |
| 4 | Laptop loses internet | Identical to (1) with SQLite. |
| 5 | Laptop shuts down | `ExecStop` writes `DEVICE_SHUTDOWN` → period recorded `DEVICE_OFFLINE`. **Never counted as distraction or idle.** |
| 6 | Laptop crashes | No shutdown marker; gap ≥2× poll → `UNOBSERVED`. On restart, the agent emits `DEVICE_STARTUP` and a `COLLECTOR_START(reason=unclean)`. |
| 7 | Browser extension crashes | SW restart reconciles from `chrome.storage`; the open interval closes at `last_seen_ts`; the gap becomes `UNOBSERVED`. Buffered IndexedDB events survive. |
| 8 | Backend offline | All collectors queue. Dashboard unavailable. Zero collection impact. On recovery, queued batches drain in order; touched days are recomputed. |
| 9 | PostgreSQL offline | API returns 503 on ingest (never 200 — a false ACK would destroy client data). Clients retry. Health check fails; Docker restart policy recovers. |
| 10 | Redis offline | Not deployed in V1. If added later, it must be cache-only: its loss degrades latency, never correctness. |
| 11 | Duplicate batch | `sync_batches` PK conflict → prior stored response replayed, 200. Zero duplicate events. |
| 12 | Partial batch | Rejected atomically with 422 and per-index errors. Client quarantines, drops the invalid events, resends the remainder with a new `batch_id`. |
| 13 | Out-of-order event | Accepted; sessionization orders by `seq`; the affected day is marked dirty and recomputed. |
| 14 | Clock change | `uptime_ms` cross-check flags `clock_suspect`; durations derive from uptime deltas; affected day flagged in the UI. |
| 15 | Timezone change | `tz_id` on each event; day boundaries use the start-of-day zone; day flagged `tz_transition`; the UI explains the short/long day. |
| 16 | Device replaced | New `device_id` via enrollment; old device revoked (`revoked_at`); its history is retained and attributed to the old device. History is never merged automatically. |
| 17 | User deletes data | `DELETE /v1/data` with re-auth and a typed confirmation: hard delete with cascade, partition drop for `raw_events`, a tombstone written to `privacy_audit_events`, devices revoked, local stores wiped on next check-in. |
| 18 | AI provider unavailable | Job marked `failed`, retried at 1 h/6 h/24 h, then abandoned. Dashboard shows all deterministic content with "AI analysis unavailable". **No degradation of metrics.** |
| 19 | LLM invalid output | One repair round-trip; second failure → discarded, `validation_status = failed`, logged with cost. |
| 20 | LLM unsupported claims | §23.3 validator drops unverifiable insights; `validation_status = partial`; repeated offences raise a prompt-quality alert on the Health page. |

---

## 28. Security

**Device authentication:** enrollment via a one-time 8-character code generated in the dashboard,
10-minute TTL, single use. Returns a 256-bit random device token; only its Argon2id hash is stored.
The token lives in Android `EncryptedSharedPreferences` (Keystore-backed) / `~/.config/timeos/token`
(mode 0600) / `chrome.storage.local`.

**Token rotation:** every 30 days automatically, and on demand. Old token is honoured for 24 h to
survive a failed rotation. Rotation is initiated by the *client* and requires proof of the current
token. Any device can be revoked from the dashboard instantly.

**Scope separation:** device tokens can **only** call `/v1/ingest/*` and `/v1/sync/*`. They cannot read
any data back. A stolen device token allows writing junk telemetry — never reading history. This
asymmetry is the single highest-value security property in the design.

**Transport:** TLS 1.2+ only, HSTS with preload, automatic certificates via Caddy, certificate pinning
on Android (with a backup pin and a documented rotation runbook — pinning without a backup pin bricks
the app).

**At rest:** full-disk encryption on the VPS; PostgreSQL in a Docker volume; `pgcrypto` not used for
column encryption in V1 because the application needs to read everything it stores (column encryption
with an application-held key protects only against direct disk theft, which FDE already covers).
Backups are encrypted with `age` using a key held **off** the VPS.

**Database access control:** the `api` role has DML only, no DDL (migrations run as a separate
`migrator` role). No superuser in the application path. Postgres is **not** published on a host port —
it is reachable only on the internal Compose network.

**Secrets:** environment variables via a `.env` file (mode 0600, git-ignored) or Docker secrets.
`.env.example` is committed with placeholder values only. A `gitleaks` pre-commit hook and CI scan are
mandatory. Zero secrets in source, ever.

**API authorization:** dashboard sessions are httpOnly/Secure/SameSite=Strict cookies, 30-day sliding
expiry, CSRF token on all mutations. Rate limits: ingest 60 req/min/device, auth 5/min/IP,
AI trigger 5/day/user.

**Audit logging:** authentication events, token issuance/rotation/revocation, data export, data
deletion, privacy-gate invocations, and AI calls. Append-only, retained 2 years.

**Retention & deletion:** as §13. Export produces a signed ZIP of JSON + CSV. Delete is a genuine hard
delete, not a soft flag.

### 28.1 Compromise analysis

| Event | Exposure | Mitigation | Residual risk |
|---|---|---|---|
| **Database leaks** | Complete behavioural history: every app, every domain, every timestamp. This is the worst case in the system. | FDE; Postgres not port-published; `raw_events` retention 180 days limits the blast radius; encrypted off-site backups | **High.** Accepted consciously: a personal VPS is not a hardened environment. Mitigate by keeping the retention window short and considering self-hosting on a home machine behind Tailscale for maximum sensitivity. |
| **API/device token leaks** | Attacker can **write** fake telemetry. Cannot read anything. | Scope separation; per-device revocation; anomaly detection on implausible event rates; 30-day rotation | Low — data pollution, detectable and correctable by revoking the device and deleting its events. |
| **LLM provider receives an AI context** | Aggregate minutes per category, focus statistics, user-authored goal names. No apps (default), no URLs, no content, no identifiers. | Allowlist, forbidden-field scan, opt-out app names, per-payload audit digest | Low, and *quantified* — the Privacy page shows exactly what was sent. Use a provider with a zero-retention/no-training agreement, or `OllamaProvider` for zero egress. |
| **Laptop stolen** | Local SQLite buffer (≤7 days of synced+unsynced events) and the device token. | FDE (mandatory, documented in setup); token file 0600; remote revoke from the dashboard | Low if FDE is on. **Runbook: revoke the device first, then rotate the dashboard password.** |
| **Phone stolen** | Room DB and device token, both in app-private storage. | Android FDE + screen lock; Keystore-backed token; remote revoke | Low with a screen lock; high on an unlocked, rooted device. |
| **VPS compromised** | Everything in the database, plus the LLM API key, plus the ability to forge insights. | Minimal attack surface (Caddy + API only exposed), automatic security updates, SSH keys only with password auth disabled, fail2ban, no Docker socket exposure, off-site encrypted backups the attacker cannot reach or destroy | **High impact, low likelihood.** Off-site immutable backups are the real control: they guarantee recovery even from a destructive compromise. |

**Explicitly assumed:** backend compromise is possible. Therefore (a) raw event retention is bounded,
(b) backups live off the VPS, (c) the device-token scope cannot read, and (d) no third-party secrets
beyond one LLM key ever reside on the box.

---

## 29. Deployment

Single VPS (2 vCPU / 4 GB / 60 GB NVMe is ample — realistically 2 GB suffices), Ubuntu LTS,
Docker + Compose v5.

```yaml
services:
  caddy:      # 80/443, automatic HTTPS, reverse proxy, security headers
  api:        # FastAPI, depends_on db healthy, restart: unless-stopped
  worker:     # scheduled pipeline jobs, same image, different command
  dashboard:  # Next.js standalone
  db:         # postgres:16-alpine, named volume, healthcheck pg_isready
  backup:     # pg_dump + age encrypt + off-site push, daily cron
```

- Domain: `timeos.<user-domain>`; Caddy obtains certificates automatically; HSTS, X-Frame-Options DENY,
  strict CSP on the dashboard.
- Health checks: `/v1/health/live` (process) and `/v1/health/ready` (DB reachable + migrations current).
  Compose `healthcheck` on every service; `restart: unless-stopped` everywhere.
- Logging: JSON to stdout, `json-file` driver with `max-size=10m, max-file=5`. No event payloads or
  tokens in logs, ever — a log-redaction filter is part of the logging config and is unit-tested.
- Migrations: `alembic upgrade head` runs in an init container **before** `api` starts; `api` refuses
  to serve if the schema is behind (checked in `/ready`).
- Deploy: `git pull && docker compose build && docker compose up -d`. A pre-deploy `pg_dump` is
  mandatory and is part of the deploy script, not a manual step.
- No Kubernetes. No service mesh. No horizontal scaling. One user, one box. (ADR-010.)

---

## 30. Backup / Restore

- **Daily** `pg_dump -Fc` at 03:30 local, `age`-encrypted, pushed to off-site object storage
  (B2/R2, ~$0.15/mo at this volume). Retention: 7 daily, 4 weekly, 6 monthly.
- **Pre-deploy** dump retained 7 days locally.
- **Restore drill is mandatory quarterly** and the runbook lives in `deploy/RESTORE.md`. An untested
  backup is not a backup; the drill restores into a scratch container and asserts row counts and the
  latest `daily_metrics` row.
- RPO 24 h, RTO ~30 min (provision box, restore dump, `compose up`).
- Device-side buffers provide an additional recovery layer: up to 7 days of events can be re-synced
  from devices after a restore, since `event_id` idempotency makes re-ingestion safe. This is a real
  and valuable property of the offline-first design — **re-sync after restore is a documented step.**

---

## 31. Observability

Metrics exposed at `/v1/health/metrics` (Prometheus text format; scraping optional) and rendered on the
dashboard's System Health page:

`events_collected_total{device}`, `events_synced_total{device}`, `events_rejected_total{reason}`,
`events_duplicate_total`, `sync_latency_seconds{p50,p95}` (ingested_at − ts_utc),
`collector_last_seen_seconds{device}`, `collector_uptime_ratio_24h{device}`,
`coverage_ratio{device,day}`, `unknown_activity_ratio{day}`, `classification_confidence{p50,p10}`,
`db_size_bytes`, `partition_count`, `pipeline_run_duration_seconds{stage}`,
`ai_requests_total{provider,status}`, `ai_failures_total{reason}`, `ai_cost_usd_total`,
`privacy_gate_rejections_total{field}`, `seq_gaps_total{device}`.

**Trustworthiness rules surfaced to the user:** a device unseen for >2 h is flagged; coverage below
70 % on any day is flagged; `unknown_ratio` above 25 % prompts a correction session; any privacy-gate
rejection is a **critical** alert (it means a code path attempted to leak a forbidden field).

Alerting in V1 is a daily digest email plus dashboard banners. No PagerDuty for a personal system.

---

## 32. Cost Model

| Item | Monthly |
|---|---|
| VPS (2 vCPU / 4 GB, Hetzner/Contabo class) | $5–7 |
| Domain (amortised) | ~$1 |
| Off-site encrypted backups (~1 GB) | ~$0.15 |
| Bandwidth (≈50–200 MB/mo of telemetry) | included |
| LLM: 30 daily (~4k in / 1.5k out) + 4 weekly + 1 monthly | **$0.60–2.50** |
| **Total** | **≈ $7–11/month** |

Storage growth: ≈10–30k events/day ≈ 3–8 MB/day raw ≈ 100–240 MB/month, bounded by the 180-day
partition drop to ~1.5 GB steady state; aggregates add <50 MB/year.

**Cost controls, by design:** deterministic analytics do 100 % of computation; AI runs 35 times a month,
not per event; identical `context_hash` reuses the cached analysis; context arrays are capped to bound
tokens; a monthly spend cap (`AI_MONTHLY_BUDGET_USD`, default $5) halts AI calls and shows a banner
rather than surprising the user. Switching to `OllamaProvider` on the same box reduces LLM cost to $0
at the price of RAM and quality — this is why the provider abstraction exists.

---

## 33. Testing Strategy

**Unit (pytest, ≥90 % on `analytics/` and `privacy/`):**
sessionization (overlaps, unterminated sessions, split-screen, sub-3s drops, merge-on-bounce);
duration arithmetic across DST transitions and timezone changes; coverage reconstruction for all six
state cases; focus detection at every threshold boundary; interruption tolerance; distraction pattern
detectors against hand-built sequences; goal alignment with confidence weighting; classification layer
precedence and the `Unknown` floor; privacy sanitization.

**Property-based (Hypothesis):** for any event stream, (a) session durations never exceed the covering
window, (b) coverage intervals are gapless and non-overlapping, (c) re-running sessionization is
idempotent and byte-identical, (d) day totals never exceed day duration.

**Integration (testcontainers + real Postgres):** Android→API with recorded fixture batches;
duplicate batch replay returns the identical response; partial/invalid batch atomic rejection;
out-of-order and late-arriving events trigger correct recomputation; offline→recovery drain;
full pipeline raw→metrics→context.

**Security tests (these must exist and must fail the build if broken):**
```
test_raw_event_cannot_reach_llm          # inject a raw row → PrivacyViolation
test_ai_module_has_no_db_import          # import-linter contract
test_ai_module_cannot_open_connection    # patch engine; assert never called
test_forbidden_field_rejected            # every §20.3 forbidden class, parametrised
test_extra_field_forbidden               # AIContext extra="forbid"
test_url_email_token_scan                # content scanner against a leak corpus
test_malformed_ai_output_not_persisted   # invalid JSON → no ai_insights rows
test_fabricated_number_rejected          # unverifiable figure → insight dropped
test_device_token_cannot_read            # ingest token → 403 on every read endpoint
test_no_secrets_in_repo                  # gitleaks
```
The privacy suite runs on every commit and is a required status check. A leak that reaches production
is unrecoverable (the data is already at the provider), so this is the one area where test cost is
unquestioned.

**Android (JUnit + Robolectric + instrumented):** UsageEvents mapping from recorded fixtures, Room
migrations, sync retry/backoff state machine, permission-loss detection, boot-recovery path.

**Manual/device:** a documented checklist per phase (§39), executed on a real phone — the emulator
cannot validate usage statistics, Doze, or OEM battery behaviour.

---

## 34. Performance Requirements

| Component | Requirement |
|---|---|
| Android poll | < 500 ms CPU per run; < 1 % battery/day; < 30 MB RSS |
| Android local DB | < 50 MB steady state |
| Desktop agent | < 1 % CPU average; < 60 MB RSS |
| Extension background (each of 3) | < 20 MB; no measurable tab-switch latency; three concurrent installs < 60 MB total |
| Ingest endpoint | p95 < 300 ms for a 1000-event batch |
| Sessionization | full day, all devices, < 5 s |
| Daily pipeline | < 30 s end-to-end |
| Dashboard | LCP < 1.5 s; timeline render < 200 ms for a full day |
| AI daily analysis | < 30 s including validation |
| 90-day trend query | < 500 ms (served from `daily_metrics`, never from `raw_events`) |

**Rule:** no dashboard query ever touches `raw_events`. All reads are served from pre-computed
aggregates. This is what keeps the dashboard fast as history grows.

---

## 35. Android Limitations (consolidated, must be shown in-product)

1. `PACKAGE_USAGE_STATS` cannot be requested by dialog and can be silently revoked → collection stops.
2. Event-level usage history is retained by the OS for only ~7 days → prolonged downtime loses data
   permanently.
3. Mobile browsing is not attributable to websites — Chrome is a single opaque package.
4. In-app content is invisible; YouTube-as-learning vs YouTube-as-entertainment is inferred, never known.
5. Screen-on-but-idle is indistinguishable from attentive reading beyond `USER_INTERACTION` heuristics.
6. OEM battery managers (Xiaomi, Oppo, Vivo, Samsung, Huawei) may kill WorkManager regardless of
   configuration; observed cadence must be surfaced so the user can detect it.
7. Doze and App Standby buckets delay work; 15-minute periods become "at least 15 minutes".
8. Split-screen/PiP produces concurrent foreground apps.
9. Nothing before install exists; there is no history import.
9b. **Samsung One UI specifically (the target device):** *Battery → Background usage limits* with its
    "Sleeping apps" / "Deep sleeping apps" lists and the "Put unused apps to sleep" toggle will
    suppress WorkManager regardless of correct configuration. TimeOS must be added to **Never sleeping
    apps** with an *Unrestricted* battery profile during onboarding, and the app must display its
    **observed** poll cadence so suppression is visible rather than silent. Usage Access on One UI
    lives at *Settings → Security and privacy → More privacy settings → Usage data access*, and the
    generic intent may land on the list rather than TimeOS's row — the copy must say "find TimeOS in
    this list".
10. Notification content is deliberately excluded (§8.6); notification-derived interruption counts are
    therefore unavailable in V1.
11. `QUERY_ALL_PACKAGES` is a Play-policy-restricted permission. **Play Store implication:** this app,
    with usage-access plus broad package visibility, would face a difficult review and would need a
    prominent-disclosure flow and a privacy policy. **Decision: distribute by sideload/internal track
    only.** Play distribution is out of scope for V1 and would require revisiting §8.2 and §8.6.
12. iOS is **not** equivalent: Screen Time data has no public API. An iOS collector would be limited to
    DeviceActivity/FamilyControls with an entitlement and would provide a fundamentally weaker dataset.
    Do not assume parity; out of scope.

---

## 36. Known Risks

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| R1 | OEM kills the collector → silent data loss | High | Observed-cadence display, battery-optimisation exemption prompt, `UNOBSERVED` honesty, 48 h staleness warning |
| R2 | Usage-access revoked unnoticed | High | Re-check every run, persistent notification, dashboard alert |
| R3 | 7-day OS retention exceeded during downtime | Med | 15-min polling, catch-up on launch, escalating warnings |
| R4 | Classification accuracy too low to be useful | High | `Unknown` is honest; correction loop; success measured by `unknown_ratio` trending down, not by faked precision |
| R5 | Privacy leak into the AI context | **Critical** | Three independent controls (§20.2), CI-enforced import contract, audit trail, parametrised leak tests |
| R6 | AI fabricates numbers | Med | Evidence-path resolution + numeric cross-check (§23.3) |
| R7 | The system becomes a surveillance anxiety source | Med | Non-judgemental tone, no streaks, no gamification, easy pause, honest uncertainty |
| R8 | Wayland blocks desktop window attribution | Low (V1) | **Removed from V1 entirely** (§4.5). When built in Phase 12, degraded coverage-only mode is the default and the session is never switched to X11 |
| R14 | Samsung One UI sleeps the collector, silently losing a day | **High** | Onboarding adds TimeOS to *Never sleeping apps* + Unrestricted battery; observed poll cadence is displayed; 48 h staleness warning; `UNOBSERVED` honesty |
| R9 | Scope creep (screenshots, content, real-time blocking) | Med | Explicit non-goals; any change requires a new ADR |
| R10 | VPS compromise exposes full behavioural history | High | Bounded retention, off-site encrypted backups, minimal surface; consider home-hosting behind Tailscale |
| R11 | Double counting across devices | Med | Coverage-union totals, extension/desktop attribution arbitration, property test asserting ≤24 h days |
| R15 | Three concurrent browsers double-count web time, or one browser's collector dies unnoticed | Med | §11.4 cross-browser arbitration (union, never sum); per-`browser_family` health on the System Health page so a single-browser outage is visible; property test: browser time ≤ screen-on time |
| R16 | Firefox AMO signing delays or blocks the Firefox build | Med | Start unlisted self-distribution signing at the **start** of Phase 9; Brave + Chromium ship independently of it |
| R12 | Metric definitions drift, breaking history | Med | `pipeline_version` on every computed row; recompute-on-change is explicit and versioned |
| R13 | Abandonment after two weeks | Med | Day-one usefulness with zero configuration; ≤5 min setup; the dashboard must be worth opening before any AI exists |

---

## 37. Engineering Trade-offs

- **Polling vs real-time:** polling every 15 min loses sub-15-minute freshness and gains an order of
  magnitude in battery life. Freshness is worthless for daily reflection. **Polling wins decisively.**
- **Monolith vs microservices:** one user, one deploy, shared schemas. A monolith removes distributed
  failure modes entirely. Modularity is enforced by package boundaries and import contracts, which
  deliver the real benefit (isolation) without the operational cost.
- **Postgres-only vs Postgres+Redis+TimescaleDB:** native partitioning handles this volume comfortably.
  Every additional datastore is a backup, upgrade, and failure surface for zero measured benefit.
- **Rules vs ML classification:** rules are explainable, debuggable, and correctable; a personal model
  would train on a handful of labels. Rules plus a per-user learned prior is strictly better here, and
  the evidence trail is what makes corrections meaningful.
- **Confidence vs decisiveness:** showing `Unknown` costs perceived polish and buys trust. Trust is the
  product; a system that confidently mislabels is worse than useless.
- **Server-side vs on-device analytics:** server-side enables cross-device merging and cheap
  recomputation when definitions change. Cost: the raw store exists, which is the main security
  exposure — bounded by retention.
- **Category-only vs app-named AI context:** category-only loses interpretive richness and gains a much
  stronger privacy guarantee. Default to privacy; make richness an explicit, logged opt-in.
- **Android-first vs all-collectors-at-once:** building three collectors in parallel triples the
  unknowns before a single insight has been validated. Sequencing costs calendar time and buys the
  ability to kill or redesign the approach cheaply.

---

## 38. Implementation Phases

Ordering reflects §4.5 and two deliberate changes from the original brief:

1. **Phase 1 is split into 1A (minimal installable APK + permission flow) and 1B (collection +
   diagnostic)**, because Usage Access cannot be validated before an APK exists on the device.
2. **The desktop collector moves from Phase 9 to Phase 12, out of V1** (Wayland, ADR-016), and the
   browser extension moves up to Phase 9. V1 is therefore **Android + browser**.

**Phase 5 (Dashboard) remains the go/no-go gate**: a working dashboard over real phone data is the
earliest point at which the whole design can be falsified. Everything after Phase 5 is enhancement.

V1 ends at Phase 11. Phase 12 is explicitly post-V1.

Each phase is independently shippable and independently testable.

---

### Phase 0 — Architecture & Repository Preparation

- **Objective:** a working, reproducible skeleton: repo, monorepo layout, Docker stack, CI, secrets
  hygiene, migrations — with zero product logic.
- **Inputs:** this specification; the host toolchain verified in §4.3.
- **Outputs:** `git init` done; the §5.1 tree exists; `docker compose up` brings up Postgres 16, a
  FastAPI stub answering `/v1/health/live` and `/ready`, and a Next.js stub; Alembic initialised with an
  empty head; `.env.example`; `gitleaks` pre-commit; CI running lint, type-check, tests, and the
  import-linter contract.
- **Files/components:** `backend/`, `dashboard/`, `deploy/compose.yml`, `deploy/Caddyfile`,
  `.github/workflows/ci.yml`, `pyproject.toml`, `.gitignore`, `.env.example`, `docs/adr/`.
- **Database changes:** Alembic baseline only.
- **APIs:** `/v1/health/live`, `/v1/health/ready`.
- **Algorithms:** none.
- **Security:** `.env` git-ignored and 0600; no secrets committed; Postgres not port-published;
  import-linter contract present and failing-closed from day one.
- **Tests:** CI green; health endpoints return 200; `alembic upgrade head` idempotent; gitleaks clean.
- **Manual verification:** `docker compose up -d` on the laptop; `curl localhost:8000/v1/health/ready`
  returns `{"status":"ready"}`; dashboard stub loads.
- **Failure cases:** port conflicts; Compose v5 syntax differences (use `docker compose`, no `version:`
  key); Android SDK platform 36 missing → run `sdkmanager "platforms;android-36"`.
- **Definition of Done:** a fresh clone reaches a green CI and a running stack in under 10 minutes with
  one documented command.

---

### Phase 1 — Android Collector (split: 1A installable app, then 1B collection)

**Ordering rule (normative):** Usage Access **cannot** be validated before an APK exists on the
device. Phase 1 therefore produces a *minimal but real installable application first*, and only then
enables collection. **No step in this specification may require Usage Access to be configured before
the first APK is installed.**

#### Phase 1A — Minimal installable app + permission flow

- **Objective:** an APK that launches on the Samsung Galaxy S24 FE, explains and requests Usage
  Access, and correctly detects whether it has been granted. No collection, no storage, no network.
- **Inputs:** Phase 0; the physical S24 FE with Developer Options and USB debugging enabled.
- **Outputs:** a debuggable APK installed via `adb install`; a Compose onboarding screen explaining
  *why* Usage Access is needed and exactly what is and is not collected; a button launching
  `Settings.ACTION_USAGE_ACCESS_SETTINGS`; a live permission-state indicator that updates on
  `onResume`; a generated TimeOS device ID persisted locally.
- **Files/components:** `android/app/` (`MainActivity`, `OnboardingScreen`, `PermissionStateScreen`),
  `android/core/collector/UsageAccess.kt` (permission check only), `android/core/model/DeviceId.kt`.
- **Database changes:** none.
- **APIs:** none. The app must not declare `INTERNET` yet — absence of the permission is the
  strongest possible proof that nothing leaves the device in this milestone.
- **Algorithms:** permission detection via
  `AppOpsManager.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, uid, packageName)`,
  re-evaluated on every `onResume` — Android provides **no callback** when the user revokes it.
  Device ID is `UUID.randomUUID()` generated on first launch and stored in
  `EncryptedSharedPreferences`. **Never** `getDeviceId()`, `Build.getSerial()`, `TelephonyManager`,
  `ANDROID_ID`, the phone number, or any other hardware or network identifier.
- **Security/privacy:** manifest declares **only** `PACKAGE_USAGE_STATS` (and later
  `RECEIVE_BOOT_COMPLETED`, `POST_NOTIFICATIONS`). It must declare **none** of: `READ_CONTACTS`,
  `READ_SMS`, `READ_PHONE_STATE`, `READ_PHONE_NUMBERS`, `BIND_NOTIFICATION_LISTENER_SERVICE`,
  `BIND_ACCESSIBILITY_SERVICE`, `INTERNET` (1A only). A CI test parses `AndroidManifest.xml` and
  **fails the build** if any forbidden permission appears — this is the Android mirror of the §20
  privacy gate, and it must exist from the very first milestone.
- **Tests:** manifest-permission allowlist test (build-failing); permission-detection unit test for
  granted, denied, and revoked-after-grant states; Compose UI test for the three onboarding states.
- **Manual verification (on the S24 FE):** `adb install` succeeds; the app launches; the screen
  states "Usage Access not granted"; the button opens Samsung's Usage Access list; granting it and
  returning shows "granted" without an app restart; revoking it in Settings and returning shows
  "not granted" again.
- **Failure cases:** Samsung's One UI presents Usage Access under *Settings → Security and privacy →
  More privacy settings → Usage data access* and the generic intent may land on a list rather than
  TimeOS's own row — the onboarding copy must therefore tell the user to **find "TimeOS" in the
  list**, not assume a direct deep link. If the intent fails to resolve at all (rare, OEM-dependent),
  catch `ActivityNotFoundException` and show manual navigation instructions.
- **Definition of Done:** the APK is installed on the physical S24 FE, Usage Access can be granted
  through the in-app flow, and the app reflects grant *and* revocation correctly. **Nothing is
  collected and nothing is stored yet.**

#### Phase 1B — Usage collection + local diagnostic

- **Objective:** prove that `UsageStatsManager` actually returns real, correct data on this device,
  and that it survives restarts.
- **Inputs:** Phase 1A with Usage Access granted on the real device.
- **Outputs:** `UsageEventReader` draining `queryEvents`; `EventMapper` producing §9.1 envelopes;
  15-minute `PeriodicWorkRequest`; a **diagnostic screen** listing the most recent mapped events
  (package, type, timestamp, derived session duration) and a health panel showing last poll time,
  observed poll cadence, event count, and permission state.
- **Files/components:** `android/core/collector/{UsageEventReader,EventMapper,CoverageTracker}.kt`,
  `android/core/model/` (event envelope), `android/app/DiagnosticScreen.kt`, `BootReceiver`.
- **Database changes:** none server-side. Local persistence lands in Phase 2; 1B may hold events in
  a bounded in-memory ring buffer **plus** a simple durable append so the restart criterion below is
  testable — the full Room schema and sync queue remain Phase 2 work.
- **APIs:** none. `INTERNET` is still not declared.
- **Algorithms:** §8.1 event-type filtering; drain `[last_cursor − 5 min, now]` with fingerprint
  dedupe; cursor advance; §14.1 session-boundary rules applied locally for display only;
  `BOOT_COMPLETED` re-enqueues work and emits the `DEVICE_STARTUP` marker.
- **Security/privacy:** the manifest allowlist test from 1A continues to gate the build. Mapped
  events carry package names only — never labels derived from notification or accessibility data.
- **Tests:** `EventMapper` unit tests over recorded `UsageEvents` fixtures; overlap-dedupe and
  cursor-advance tests; permission-loss mid-run raises `PERMISSION_LOST` rather than crashing;
  boot-recovery re-enqueue test.
- **Manual verification (the First Validation Loop, executed in order on the S24 FE):**
  1. APK installed.
  2. Usage Access granted through the in-app flow.
  3. `UsageStatsManager` query succeeds — the diagnostic screen is non-empty.
  4. Open three known apps in a known order; **real usage appears** on the diagnostic screen with
     the correct packages, order, and plausible durations.
  5. Events are stored locally.
  6. Force-stop and relaunch the app — **previously collected events are still present.**
  7. Enable airplane mode for an hour — collection continues unaffected and nothing is lost.
- **Failure cases:** **Samsung-specific.** One UI's aggressive power management is the dominant risk
  on this exact device: *Settings → Battery → Background usage limits* (Sleeping / Deep sleeping
  apps) and the "Put unused apps to sleep" toggle will suppress WorkManager. Onboarding must
  instruct the user to add TimeOS to **Never sleeping apps** and set its battery profile to
  *Unrestricted*. Because the app must not lie about this, the health panel displays the **observed**
  poll cadence, so a suppressed worker is visible rather than silent. Other cases: permission
  revoked mid-day; device rebooted; emulator returning an empty event stream (expected — the
  emulator cannot validate this milestone).
- **Definition of Done:** all seven First Validation Loop steps pass on the physical S24 FE, and over
  24 hours the app records ≥95 % of the foreground transitions that Samsung's own Digital Wellbeing
  screen reports, with battery impact under 1 %.

**Gate:** do not begin Phase 2 until the First Validation Loop has passed on real hardware. The
entire product rests on this loop being genuinely reliable on this specific device.

---

### Phase 2 — Android Local Storage & Offline Sync Client

- **Objective:** durable local persistence and a complete sync state machine — still with no server.
- **Inputs:** Phase 1.
- **Outputs:** Room DB with migrations; pending queue; batch builder; retry/backoff; quarantine table;
  sync status UI; token storage in `EncryptedSharedPreferences`.
- **Files/components:** `android/core/db/`, `android/core/sync/`.
- **Database changes:** Room schema v1 (§8.8).
- **APIs:** client-side contract for `/v1/ingest/batch` (server stubbed with a local mock).
- **Algorithms:** §26 batching, ordering, backoff with jitter, ACK semantics, gap detection, pruning.
- **Security:** token in Keystore-backed storage; TLS-only client config; no logging of payloads.
- **Tests:** Room migration tests; batch-size boundary tests; backoff state machine; 4xx quarantine vs
  5xx retry; prune-only-synced invariant; 200k-row backpressure behaviour.
- **Manual verification:** airplane mode for 6 h → events accumulate, none lost; re-enable → queue drains
  in order; force-stop mid-batch → no duplicates on resume.
- **Failure cases:** DB corruption (recreate + emit `UNOBSERVED`); disk full; stuck queue on a
  permanently invalid batch (must quarantine, not loop).
- **Definition of Done:** 48 h offline followed by reconnection yields zero lost and zero duplicated
  events against a mock server.

---

### Phase 3 — Backend Ingestion

- **Objective:** authenticated, idempotent, validated ingestion into `raw_events`.
- **Inputs:** Phases 0–2.
- **Outputs:** enrollment, token rotation, `/v1/ingest/batch`, `sync_batches` ledger, partitioned
  `raw_events`, gap detection, ingest metrics.
- **Files/components:** `backend/timeos/api/{devices,ingest}.py`, `ingest/service.py`,
  `models/{user,device,raw_event,sync_batch}.py`, `schemas/events.py`.
- **Database changes:** `users`, `devices`, `sync_batches`, `raw_events` (+ monthly partitions and a
  partition-maintenance job).
- **APIs:** `/v1/devices/enroll`, `/v1/devices/token/rotate`, `/v1/ingest/batch`, `/v1/sync/state`.
- **Algorithms:** §12.3 ingestion algorithm; clock-drift detection via `uptime_ms`; dirty-day marking.
- **Security:** Argon2id token hashes; scope separation (ingest tokens cannot read); rate limits;
  payload size caps; `extra="forbid"` on every event schema.
- **Tests:** duplicate batch → identical stored response; invalid event → atomic 422; `seq` gap
  recorded; ingest token rejected (403) on every read endpoint; 1000-event batch p95 < 300 ms.
- **Manual verification:** enroll the real phone with a dashboard code; confirm rows land in Postgres
  with correct UTC timestamps and `tz_id`.
- **Failure cases:** DB down → 503 never 200; clock-skewed device; oversized batch; replayed batch.
- **Definition of Done:** the Phase 2 app syncs a full real day to the server with zero duplicates and
  a verified `seq` sequence with no gaps.

---

### Phase 4 — Sessionization & Deterministic Analytics

- **Objective:** turn raw events into sessions, coverage, activities and `daily_metrics`. **This is the
  analytical heart of the system.**
- **Inputs:** Phase 3 with ≥3 days of real data.
- **Outputs:** sessionizer, coverage reconstruction, activity classifier (L0–L4), focus engine,
  distraction detectors, `daily_metrics`, scheduled pipeline, recompute-on-dirty.
- **Files/components:** `backend/timeos/analytics/{sessionize,coverage,classify,focus,distraction,
  metrics}.py`, `jobs/pipeline.py`, seed catalogue `analytics/data/app_priors.yaml`.
- **Database changes:** `device_coverage`, `app_sessions`, `activities`, `activity_categories`,
  `app_classifications`, `daily_metrics`, `behavioral_patterns`.
- **APIs:** `/v1/days/{date}`, `/v1/days/{date}/timeline`.
- **Algorithms:** §14 (all rules), §15 (layered classifier), §16 (focus/fragmentation formulas),
  §17 (pattern detectors).
- **Security:** none new; all data stays server-side.
- **Tests:** the full §33 unit and property suites; golden-file tests over a recorded real day;
  idempotent recomputation; DST and timezone-change days; overlapping-session day never exceeds 24 h.
- **Manual verification:** compare a computed day against the phone's own Digital Wellbeing totals
  (within ~5 %) and against personal recollection of the timeline.
- **Failure cases:** unterminated sessions; concurrent split-screen; clock jumps; a day with 0 events
  (must produce a valid all-`UNOBSERVED` day, not a crash).
- **Definition of Done:** `daily_metrics` for 7 consecutive real days are computed, deterministic under
  re-run, coverage-annotated, and within 5 % of the OS's own screen-time figure.

---

### Phase 5 — Dashboard

- **Objective:** make the data legible and prove the design is worth continuing. **The go/no-go gate.**
- **Inputs:** Phase 4.
- **Outputs:** Today, Timeline, Where Time Went, Focus, System Health; session auth; coverage badges;
  correction affordance wired to Phase 6's feedback endpoint stub.
- **Files/components:** `dashboard/app/**`, `dashboard/components/{Timeline,MetricCard,CoverageBadge}`.
- **Database changes:** `user_feedback` (table created here, consumed in Phase 6).
- **APIs:** the read endpoints above plus `/v1/health/collectors`.
- **Algorithms:** interval→pixel timeline layout with explicit `UNOBSERVED`/`OFFLINE` rendering.
- **Security:** httpOnly session cookies; CSRF on mutations; strict CSP; no device tokens in the browser.
- **Tests:** component tests for timeline rendering of all four coverage states; a test asserting every
  metric card renders a coverage badge; E2E smoke.
- **Manual verification:** open yesterday; the timeline matches lived experience; a powered-off period
  is visibly grey and labelled, not counted as anything.
- **Failure cases:** days with no data; very long days (DST); >200 sessions in a day (virtualise).
- **Definition of Done:** the owner can reconstruct yesterday from the dashboard alone and finds it
  accurate enough to trust. **If this fails, stop and fix Phase 4 rather than proceeding.**

---

### Phase 6 — Personal Goals & Context

- **Objective:** capture user intent and close the correction loop.
- **Inputs:** Phase 5.
- **Outputs:** goal CRUD, working hours, custom taxonomy, per-app rules, correction UI, retroactive
  recompute (opt-in), goal-alignment computation.
- **Files/components:** `backend/timeos/analytics/goals.py`, `api/{goals,feedback}.py`,
  `dashboard/app/goals/`, correction components.
- **Database changes:** `goals`, `goal_activity_mapping`, `working_hours`, `user_feedback` (consumed),
  `activities.superseded_by` usage.
- **APIs:** `/v1/goals` CRUD, `/v1/feedback/classification`.
- **Algorithms:** §18 alignment with uncertainty; Bayesian update of `app_classifications` with a
  60-day recency half-life.
- **Security:** goal names are user-authored free text — length-capped at 60 chars and scanned by the
  privacy gate before ever entering an AI context.
- **Tests:** alignment arithmetic with confidence weighting; unallocated time never redistributed;
  correction creates a new activity row and preserves history; learned prior converges after 5 samples.
- **Manual verification:** correct 10 misclassifications; confirm subsequent days classify correctly
  without further correction.
- **Failure cases:** contradictory corrections; overlapping goal mappings (weights must not exceed 1
  per activity); archived goals in historical windows.
- **Definition of Done:** `unknown_ratio` drops measurably after a correction session, and goal
  attainment is displayed with an honest uncertainty band.

---

### Phase 7 — Privacy Gate & AI Context Builder

- **Objective:** build the boundary **before** any LLM code exists. Non-negotiable ordering.
- **Inputs:** Phases 4–6.
- **Outputs:** `PrivacyGate`, `AIContextBuilder`, `AIContext` Pydantic model, allowlist v1, content
  scanner, `privacy_audit_events`, the Privacy dashboard page, import-linter contract enforced.
- **Files/components:** `backend/timeos/privacy/{gate,allowlist,scanner,audit}.py`,
  `schemas/ai_context.py`, `dashboard/app/privacy/`.
- **Database changes:** `privacy_audit_events`.
- **APIs:** `GET /v1/privacy/audit`, `GET /v1/privacy/preview/{date}` (shows exactly what *would* be sent).
- **Algorithms:** §20.2 three-layer enforcement; §21 deterministic context assembly with `context_hash`.
- **Security:** this phase *is* the security work. Every §33 security test must pass.
- **Tests:** the complete privacy suite, parametrised over every forbidden class; golden-file context
  test; `extra="forbid"` enforcement; import contract failing the build when violated.
- **Manual verification:** open `/privacy/preview/yesterday` and read the exact payload; confirm no
  package name, URL, identifier, or free text you did not author appears.
- **Failure cases:** a new metric added later without an allowlist entry (must be rejected, not passed);
  a user-authored goal name containing a URL (must be scrubbed/rejected).
- **Definition of Done:** every privacy test passes; the preview endpoint shows a payload the owner is
  comfortable sending to a third party; no code path can reach an LLM without traversing the gate.

---

### Phase 8 — Daily AI Analyst

- **Objective:** interpretation over the sanitized context, with anti-fabrication enforcement.
- **Inputs:** Phase 7; ≥14 days of data so baselines exist.
- **Outputs:** `LLMProvider` protocol with Anthropic/OpenAI/Ollama/Null implementations; daily job;
  structured output validation; evidence verification; insight storage; AI Diagnosis and
  Recommendations pages; budget cap.
- **Files/components:** `backend/timeos/ai/{provider,client,prompts,validate}.py`,
  `schemas/ai_output.py`, `jobs/daily_analysis.py`, `dashboard/app/insights/`.
- **Database changes:** `ai_analysis`, `ai_insights`.
- **APIs:** `GET /v1/insights/{date}`, `POST /v1/ai/analyze/{date}` (rate-limited).
- **Algorithms:** §23.3 validator (evidence-path resolution, numeric cross-check, score band, status
  downgrade, confidence ceiling); context-hash caching.
- **Security:** the AI module has no DB imports (CI-enforced); API key from env only; no tools; no
  function calling; output never rendered as HTML.
- **Tests:** invalid JSON → nothing persisted; fabricated number → insight dropped; `FACT` with
  non-measured evidence → downgraded; provider outage → job fails cleanly and the dashboard degrades;
  `NullProvider` path works with zero configuration; budget cap halts calls.
- **Manual verification:** read a day's diagnosis; every number in it must be findable in the context
  preview; disable the API key and confirm the dashboard remains fully functional.
- **Failure cases:** provider outage, rate limits, truncated output, hallucinated fields, cost spikes.
- **Definition of Done:** 7 consecutive daily analyses stored, each with fully verified evidence, zero
  fabricated figures, and total cost under $0.50.

---

### Phase 9 — Browser Extension

- **Objective:** domain-level web attribution across **Brave, Chromium and Firefox**, with
  structurally enforced minimal telemetry.
- **Inputs:** Phase 3 (ingest is stable). Note: there is no desktop agent in V1, so no
  attribution arbitration is required yet — the arbitration rule is specified here but only
  becomes active in Phase 12.
- **Outputs:** one source tree building **two artifacts** (`dist/chromium/` for Brave + Chromium,
  `dist/firefox/` for Gecko); domain reduction at capture; IndexedDB buffer; background-eviction
  reconciliation; per-browser enrollment (three devices, three tokens); a **signed `.xpi` from AMO
  unlisted self-distribution** for Firefox; optional local-only raw-URL mode (default off).
- **Files/components:** `extension/{src/background.ts,src/store.ts,src/sync.ts,src/psl.ts,
  src/attribution.ts}`, `extension/manifest.chromium.json`, `extension/manifest.firefox.json`,
  `extension/build.ts` (dual-target build), `webextension-polyfill` dependency.
- **Database changes:** `browser_sessions` (with `browser_family`, `truncated`);
  `devices.browser_family`.
- **APIs:** existing ingest.
- **Algorithms:** §11.2 focus attribution (active tab + focused window + not idle), PSL reduction,
  §11.3 heartbeat reconciliation, §11.4 cross-browser arbitration (later-starting interval wins;
  union not sum), desktop double-count suppression (inert until Phase 12).
- **Security:** **no `host_permissions`, no content scripts** — content access is structurally
  impossible in every engine. A build-failing test asserts **both** manifests contain neither.
  Private/incognito windows (including Brave's Tor windows) are excluded; the extension is never
  granted incognito access. Each browser holds its own device token, so one compromised browser
  profile is revocable independently.
- **Tests:** URL→registrable-domain reduction table (including multi-level TLDs such as
  `co.uk`, `github.io`); background-context restart reconciliation; background tabs accrue zero;
  manifest permission assertion on both manifests; **cross-browser arbitration unit tests** over
  synthetic overlapping interval sets from three devices; property test asserting browser time never
  exceeds screen-on time.
- **Manual verification:** install on all three browsers and enroll each separately. Browse 10 sites
  in each; confirm only domains and durations sync. Inspect the network payload and confirm no path or
  query string appears anywhere. **Then the multi-browser test:** with Brave, Chromium and Firefox all
  open, switch focus between them every ~30 s for 10 minutes and confirm total attributed browser time
  matches wall-clock elapsed time within 5 % — not 2–3× it. Restart Firefox and confirm the signed
  `.xpi` persists and resumes collection.
- **Failure cases:** service-worker eviction mid-session (Chromium); event-page eviction (Firefox);
  private windows; multiple windows of the same browser; a browser killed with no focus-loss event
  (leaves an open interval → truncated at `last_seen_ts`); two browsers both believing they have
  focus during a switch; clock change mid-session; **AMO signing delay blocking the Firefox build**
  (start signing at the beginning of the phase, not the end); Brave's shields or Chromium dev-mode
  warnings confusing the install flow.
- **Definition of Done:** a browsing day across all three browsers is attributed by domain; total
  browser time never exceeds screen-on time and matches wall clock within 5 % under rapid
  browser-switching; each browser is independently enrolled and independently revocable; the Firefox
  build is permanently installed via a signed `.xpi` and survives restarts; and no full URL, path, or
  query string exists anywhere server-side.

---

### Phase 10 — Unified Cross-Device Timeline

- **Objective:** one coherent day across phone, laptop and browser.
- **Inputs:** Phase 9. (Two collectors in V1: Android and browser. The merge logic is written to
  accept a third source so Phase 12 needs no rework.)
- **Outputs:** merged timeline, `dual_device_s`, cross-device activity clustering (phone + laptop as
  one work block), per-device and unified metrics, conflict resolution rules.
- **Files/components:** `backend/timeos/analytics/merge.py`; dashboard timeline multi-band view.
- **Database changes:** `daily_metrics.dual_device_s`; `activities.devices[]` populated.
- **APIs:** `/v1/days/{date}/timeline?view=unified|per_device`.
- **Algorithms:** coverage-union totals; simultaneity handling (never sum overlapping time); primary-
  device selection per interval (the device with interaction wins); cross-device activity clustering.
- **Security:** none new.
- **Tests:** property test — unified observed time never exceeds day duration; simultaneous use produces
  one interval plus a `dual_device` marker, not double time.
- **Manual verification:** a day of working on the laptop while the phone is used intermittently shows a
  sensible unified narrative.
- **Failure cases:** clock skew between devices; one device far behind on sync (day must be recomputed
  on late arrival and marked `revised`).
- **Definition of Done:** unified days never exceed 24 h of observed time and match lived experience.

---

### Phase 11 — Historical Behavioural Intelligence

- **Objective:** baselines, trend detection, weekly/monthly analysis, pattern confirmation.
- **Inputs:** ≥30 days of Phase 10 data.
- **Outputs:** `weekly_metrics`, rolling baselines, MAD-based change detection, day-of-week
  normalisation, pattern lifecycle (candidate→confirmed→dismissed), weekly and monthly AI analyses,
  Historical dashboard views.
- **Files/components:** `backend/timeos/analytics/{baselines,trends,patterns}.py`,
  `jobs/{weekly,monthly}_analysis.py`, `dashboard/app/history/`.
- **Database changes:** `weekly_metrics`; `behavioral_patterns.status` lifecycle.
- **APIs:** `/v1/trends`, `/v1/patterns`, `POST /v1/patterns/{id}/confirm|dismiss`.
- **Algorithms:** §24 in full — robust statistics, ≥1.5 MAD change detection, minimum valid-day
  thresholds, day-of-week comparison.
- **Security:** only confirmed patterns enter the AI context.
- **Tests:** baseline excludes low-coverage days; trend not declared below 14 valid days; MAD
  computation; pattern promotion requires ≥3 occurrences across ≥3 days.
- **Manual verification:** 30-day view shows a trend the owner recognises as real.
- **Failure cases:** sparse history; a long data gap (holiday); a genuine life change that should reset
  baselines (support an explicit "baseline reset" action).
- **Definition of Done:** 30- and 90-day views render, trend changes are flagged only with sufficient
  valid days, and weekly AI analysis compares against baselines rather than judging in isolation.

---

### Phase 12 — Desktop Collector (POST-V1, DEFERRED)

- **Objective:** add laptop coverage, with honest capability reporting under Wayland. **Post-V1.**
- **Status:** deferred out of V1 per §4.5. Do not start this before Phase 11 is complete and the V1
  Definition of Done (§39) is met. Ships in **degraded / coverage-only mode by default**.
- **Inputs:** Phases 3 and 10 (ingest and the cross-device merge are stable).
- **Outputs:** Python agent, systemd user unit, SQLite buffer, idle detection, capability detection,
  optional GNOME extension for window class, degraded coverage-only mode as default.
- **Files/components:** `desktop/timeos_agent/{collector,idle,store,sync,capability}.py`,
  `desktop/systemd/timeos-agent.service`, optional `desktop/gnome-extension/`.
- **Database changes:** none (reuses the event model); `devices.capability_level` populated.
- **APIs:** existing ingest.
- **Algorithms:** §10 edge-triggered sampling; `XDG_SESSION_TYPE` capability detection; `logind` D-Bus
  lock/unlock/shutdown signals; cross-device coverage union; extension-vs-agent attribution arbitration.
- **Security:** runs as the user, never root; no window titles, no command lines, no clipboard, no
  screenshots — asserted by a payload-allowlist test.
- **Tests:** payload allowlist test (forbidden fields absent); idle threshold; clean vs unclean shutdown
  marker handling; capability downgrade path.
- **Manual verification:** work for a day; confirm laptop coverage appears alongside the phone, shutdown
  periods show as `DEVICE_OFFLINE`, and a crash shows as `UNOBSERVED`.
- **Failure cases:** Wayland with no extension (degraded mode must still be useful); suspend/resume;
  multiple X displays; the agent not restarting after logout.
- **Definition of Done:** a full day shows correct laptop coverage with no double counting against the
  phone, and the dashboard states honestly what the desktop can and cannot see.

---

## 39. Definition of Done (system-level)

V1 comprises Phases 0–11 (Android + browser). The desktop collector is **not** part of this.
The system is complete for V1 when, sustained over 30 consecutive days:

0. The First Validation Loop (§38 Phase 1B) passed on the physical Samsung Galaxy S24 FE.
1. Android coverage ≥95 % of screen-on time on days the phone was used.
2. `daily_metrics` are within 5 % of the OS's own screen-time figure.
3. Every day is fully accounted for as `TRACKED | IDLE | UNOBSERVED | DEVICE_OFFLINE`, summing to the
   day's true duration — no gaps, no overlaps, no invented activity.
3b. All three browsers are enrolled and reporting; total browser time never exceeds screen-on time,
    and no browser has been silently absent for more than 24 h without a health alert.
4. `unknown_ratio` < 0.15 after the correction loop has been used.
5. Zero duplicated events and zero unexplained `seq` gaps.
6. Every privacy test passes; `privacy_gate_rejections_total` is 0 in production; the Privacy page
   shows exactly what was sent for every AI call.
7. Every stored AI insight has resolvable evidence and a verified numeric cross-check; zero fabricated
   figures.
8. Disabling the AI provider leaves every metric, chart and timeline fully functional.
9. A restore drill has been executed successfully from an off-site encrypted backup.
9b. No forbidden Android permission appears in the manifest (build-enforced), and the device is
    identified only by its generated TimeOS device ID.
10. Monthly cost is under $15.
11. The owner opens the dashboard voluntarily and has changed at least one behaviour because of it.

Criterion 11 is the real one. The rest are necessary conditions for it.

---

## 40. Future Extensions

Deliberately out of V1, each requiring its own ADR and privacy review:
calendar correlation (meeting vs focus time); Git/commit correlation as a ground-truth signal for
Development; local LLM by default via Ollama; on-device classification to shrink the server raw store;
screenshot-based context under a separate, local-only, opt-in architecture with OCR never leaving the
device; real-time nudges; iOS via DeviceActivity (weaker dataset, §35.12); wearable/sleep correlation;
multi-user with strict per-user isolation; natural-language querying over **aggregates only** (never
raw); voice daily review; encrypted E2E sync where the server stores only ciphertext (this would be the
definitive answer to §28.1's database-leak risk, at the cost of server-side analytics).

---

## 41. Architecture Decision Records

### ADR-001 — Android native Kotlin, not cross-platform
**Decision.** Native Kotlin + Jetpack Compose for the Android collector.
**Why.** `UsageStatsManager`, `WorkManager`, appops permission checks, Doze, and boot receivers are all
platform APIs with no meaningful cross-platform abstraction. The collector *is* platform integration.
**Alternatives.** Flutter or React Native with a native plugin; KMP.
**Rejected because.** A plugin wrapper would contain all the difficulty and add a runtime, a bridge, and
a second build system for a single-platform app with no shared UI requirement.
**Trade-offs.** iOS reuse is zero — acceptable, since iOS cannot provide equivalent data anyway (§35.12).

### ADR-002 — Room/SQLite as the local event store
**Decision.** Room with typed DAOs and migrations on Android; SQLite (WAL) on desktop; IndexedDB in the
extension.
**Why.** Durable across crashes and reboots, transactional, queryable for the pending-sync queue, and
first-class on the platform.
**Alternatives.** SharedPreferences, append-only JSON files, in-memory with periodic flush, DataStore.
**Rejected because.** None survive a mid-write process kill with both durability and queryability.
**Trade-offs.** Migration discipline is required; ~50 MB of device storage.

### ADR-003 — Offline-first sync with dual idempotency
**Decision.** Collect locally always; sync opportunistically; idempotency at both `batch_id` and
`event_id`; ACK-driven; strict `seq` ordering; quarantine on 4xx.
**Why.** Collection must never depend on connectivity, and retries must be provably safe.
**Alternatives.** Direct streaming upload; server-generated IDs; at-most-once delivery.
**Rejected because.** Streaming loses data offline; server IDs make client retries unsafe; at-most-once
silently loses events, which corrupts exactly the metrics the system exists to produce.
**Trade-offs.** More client complexity and a batch ledger table; worth it — duplicate or missing events
destroy trust irrecoverably.

### ADR-004 — PostgreSQL as the sole datastore
**Decision.** PostgreSQL 16 with native monthly range partitioning on `raw_events`. No Redis, no
Timescale, no separate time-series store in V1.
**Why.** The workload is 10³–10⁴ events/day for one user. Postgres handles relational modelling, JSONB
payloads, time-range queries, and partition pruning in one engine with one backup story.
**Alternatives.** TimescaleDB; ClickHouse; SQLite server-side; Postgres + Redis.
**Rejected because.** All add operational surface for benefits that appear at volumes 3–4 orders of
magnitude higher. Redis specifically has no job to do: there is no queue depth and no cache pressure.
**Trade-offs.** If the system ever becomes multi-user, Timescale or a column store may be revisited —
the partitioned schema makes that migration tractable.

### ADR-005 — Deterministic analytics; the LLM never computes
**Decision.** All metrics are computed by tested Python. The LLM only interprets.
**Why.** LLMs are unreliable at arithmetic, non-reproducible, expensive per token, and unable to be
unit-tested. Metrics must be identical on re-run, cheap, and verifiable.
**Alternatives.** LLM-computed analytics; hybrid with LLM verification.
**Rejected because.** A time-tracking system whose numbers change between runs is not a measurement
system. The hybrid keeps every cost of the LLM path while adding a second source of truth.
**Trade-offs.** More code to write, and new metrics require code rather than a prompt change. This is
the correct direction of effort.

### ADR-006 — Privacy Gate as a structural boundary
**Decision.** A mandatory gate with an allowlist, `extra="forbid"` schemas, a content scanner, an audit
log, and a CI-enforced import contract isolating the AI module from the data layer.
**Why.** Prompt-level instructions are not a control. The requirement is that a leak be *impossible by
construction*, and that violations fail the build rather than reaching production.
**Alternatives.** Prompt instructions; denylist filtering; manual review; trusting developers.
**Rejected because.** Denylists fail on unanticipated fields; prompts fail on any code path that bypasses
them; manual review fails on the day someone is in a hurry. An allowlist plus an import contract fails
*closed* on all three.
**Trade-offs.** Every new AI-visible metric requires an allowlist edit and a test. That friction is the
feature: it forces a deliberate, reviewable decision every time.

### ADR-007 — Model-agnostic LLM abstraction
**Decision.** A narrow `LLMProvider` protocol (`complete(messages, schema) -> StructuredResult`) with
Anthropic, OpenAI, Ollama and Null implementations; prompt and schema versions stored per analysis.
**Why.** Provider economics, quality and availability change fast, and a local model must remain viable
for maximum privacy. The intelligence layer must not know which provider is behind it.
**Alternatives.** Direct SDK calls; LangChain-style frameworks.
**Rejected because.** Direct calls couple the domain to one vendor; heavyweight frameworks add large
dependency surface and indirection for a single call site.
**Trade-offs.** Provider-specific features (extended thinking, native structured outputs) must be
accessed through capability flags rather than directly.

### ADR-008 — No raw data access for the LLM
**Decision.** The LLM receives only an `AIContext` of aggregates. No DB credentials, no query tool, no
function calling, no retrieval.
**Why.** Raw telemetry is the most sensitive asset in the system; any query capability makes the
exposure unbounded and non-auditable.
**Alternatives.** Read-only SQL access; a scoped query tool; RAG over events.
**Rejected because.** A read-only replica still exposes everything to prompt injection and to the
provider; a scoped tool becomes an allowlist with extra steps and worse auditability. An aggregate
payload is bounded, hashable, previewable, and auditable.
**Trade-offs.** The model cannot "dig deeper" into an anomaly. Acceptable: deterministic drill-down is
the dashboard's job.

### ADR-009 — No screenshots in V1
**Decision.** No screen capture, no OCR, no content capture of any kind.
**Why.** Screenshots capture passwords, messages, medical and financial information indiscriminately.
They would invert the system's entire risk profile and require encrypted local-only processing to be
defensible at all.
**Alternatives.** Periodic screenshots with local OCR; on-demand capture.
**Rejected because.** Even local-only capture creates a high-value artifact on disk; the incremental
classification accuracy does not justify it while `Unknown` plus the correction loop remains available.
**Trade-offs.** Lower classification precision for content-ambiguous apps. Mitigated by §15 context
signals and user corrections.

### ADR-010 — Single VPS with Docker Compose
**Decision.** One small VPS, Docker Compose, Caddy for TLS. No Kubernetes, no managed services, no
autoscaling.
**Why.** One user, one deployment, single-digit requests per minute. Compose is reproducible, trivially
debuggable, and cheap.
**Alternatives.** Kubernetes/k3s; serverless; managed Postgres; home server.
**Rejected because.** K8s adds enormous operational complexity for a single-replica workload; serverless
conflicts with a stateful scheduled pipeline; managed Postgres triples cost. A home server is a genuine
alternative for maximum privacy and is recommended as a future option behind Tailscale (§40).
**Trade-offs.** Single point of failure and manual ops. Mitigated by restart policies, health checks,
off-site encrypted backups, and the fact that collectors keep working through any backend outage.

### ADR-011 — Modular monolith, not microservices
**Decision.** One FastAPI application with enforced internal package boundaries (`api`, `ingest`,
`analytics`, `privacy`, `ai`), plus one worker process from the same image.
**Why.** The isolation benefit people want from microservices is achieved here by import contracts,
without network partitions, distributed tracing, or multi-service deployment.
**Alternatives.** Separate ingest/analytics/AI services; an event-bus architecture.
**Rejected because.** They add failure modes and deployment complexity with no scaling need. Notably,
the strongest isolation requirement in the whole system — the AI module's separation from data — is
satisfied *better* by a CI-enforced import contract than by a network boundary, because the contract
fails the build rather than failing at runtime.
**Trade-offs.** Package discipline must be actively maintained; the import-linter contract is what
prevents erosion.

### ADR-012 — 04:00 local day boundary, UTC storage
**Decision.** Store all timestamps in UTC; define a "day" as `[local 04:00, next local 04:00)`,
configurable per user.
**Why.** UTC storage is the only sane basis for ordering and arithmetic across DST and travel. A
midnight boundary splits normal late-night sessions across two days and corrupts both.
**Alternatives.** Midnight boundaries; local-time storage; per-event zone-naive timestamps.
**Rejected because.** Local-time storage makes DST arithmetic ambiguous (one hour occurs twice); naive
timestamps lose the information needed to render correctly after travel.
**Trade-offs.** Day-boundary logic is more complex, and two days a year have non-24-hour durations —
handled explicitly by `duration_seconds` on every day record and by rate-normalised metrics.

### ADR-013 — Polling over continuous foreground service (Android)
**Decision.** 15-minute `PeriodicWorkRequest` draining the OS event buffer; no persistent foreground
service.
**Why.** `queryEvents` is historical: the OS records events whether or not TimeOS runs. Real-time
observation buys nothing for daily reflection and costs multiple percent of battery per day.
**Alternatives.** Foreground service with a persistent notification; JobScheduler; AlarmManager.
**Rejected because.** Android 14+ caps `dataSync` foreground services (~6 h/24 h), so a persistent
service is not even reliably available; the battery cost would also jeopardise long-term adoption,
which is the system's primary risk (R13).
**Trade-offs.** Up to 15 minutes of staleness, and a hard dependency on the ~7-day OS retention window
(mitigated in §8.4 with 672× margin).

### ADR-014 — `Unknown` is a first-class classification
**Decision.** Activities below a 0.55 confidence floor are labelled `Unknown`, and `unknown_ratio` is
displayed prominently rather than hidden.
**Why.** Forced classification produces confidently wrong metrics, which is strictly worse than an
honest gap — a user who catches one wrong label stops trusting every number.
**Alternatives.** Always assign the most likely category; hide low-confidence items.
**Rejected because.** Both trade a visible, correctable gap for an invisible, uncorrectable error.
**Trade-offs.** Early days will show substantial `Unknown`. This is a feature: it drives the correction
loop, which is the system's personalisation mechanism.

### ADR-015 — Coverage states over implicit zero
**Decision.** Every minute is explicitly `TRACKED`, `IDLE`, `UNOBSERVED`, or `DEVICE_OFFLINE`, and every
metric carries its coverage ratio.
**Why.** Absence of data is not evidence of absence of activity. Treating an unobserved period as zero
productive time is the single most common and most damaging error in time-tracking software.
**Alternatives.** Implicit zero-fill; interpolation from surrounding activity.
**Rejected because.** Both invent data. Interpolation is worse than zero-fill because it is plausible.
**Trade-offs.** Every UI surface must handle and display four states, and low-coverage days must render
ranges rather than point values. This complexity is the price of a system that can be trusted.

### ADR-016 — Linux desktop collector deferred out of V1; Wayland never worked around by changing the session
**Decision.** The Linux desktop collector moves from Phase 9 to Phase 12, after the V1 Definition of
Done. V1 collects from Android and the browser only. When the desktop collector is eventually built it
defaults to degraded, coverage-only mode and never guesses the active application.
**Why.** The target laptop runs GNOME on Wayland, which by design exposes no portable global
active-window API. Solving this properly means shipping and maintaining a GNOME Shell extension — a
second distribution channel, a second security surface, and a component that breaks on every Shell
major upgrade. Spending that effort before the Android→analytics→dashboard loop has proven the product
is worth continuing inverts the risk ordering.
**Alternatives.** Switch the user's session to X11; ship a best-effort attribution that guesses;
build the GNOME extension up front as a V1 blocker.
**Rejected because.** Switching the session degrades the user's daily-driver desktop for a side
project and was explicitly ruled out. Guessing attribution is the worst option available: it produces
confidently wrong data in a system whose entire value proposition is trustworthy measurement, and it
would poison the very baselines (§24) that later analysis depends on. Making the extension a V1
blocker delays every validated deliverable behind the least certain one.
**Trade-offs.** V1 has a laptop-shaped blind spot. This is mitigated honestly rather than hidden: the
day simply shows `UNOBSERVED` for laptop-only periods, exactly as §14.3 requires, and the dashboard
says so. Phone plus browser already covers the large majority of the questions in §2.

### ADR-017 — Minimal installable APK before any collection (Phase 1A/1B split)
**Decision.** The first Android milestone is a real, installable app whose only job is to explain and
request Usage Access and correctly detect its state. Collection, storage and sync follow only after
that APK is on the device and the permission has been granted through it.
**Why.** Usage Access is an appops special permission that cannot be requested by dialog and cannot be
granted or tested without an installed app to grant it *to*. It is therefore physically impossible to
validate the permission flow before an APK exists, and any plan that treats permission configuration
as a prerequisite is unexecutable. Splitting the milestone also isolates the single most
device-specific risk — One UI's permission UI and background-usage limits — into a milestone small
enough to iterate on in minutes.
**Alternatives.** One large Phase 1 delivering permission flow and collection together; developing
against the emulator first.
**Rejected because.** A combined phase cannot distinguish "the permission flow is wrong" from "the
event mapping is wrong" when the diagnostic screen is empty on a real device. The emulator has no real
usage history and no One UI power management, so it cannot validate either of the things that actually
matter here.
**Trade-offs.** One extra build/install cycle. Trivially worth it: Phase 1A ships in hours and
de-risks the foundation everything else sits on.

### ADR-018 — Support Brave, Chromium and Firefox via two engine targets from one source tree
**Decision.** The browser extension targets all three of the user's daily browsers. Brave and
Chromium share one byte-identical MV3 service-worker build; Firefox gets a second build using event
pages and the promise-based `browser.*` API via `webextension-polyfill`. Each browser install is
enrolled as its own TimeOS device, and overlapping intervals are arbitrated in the merge layer rather
than coordinated between extensions.
**Why.** The user genuinely runs all three concurrently, so a single-browser extension would silently
lose the majority of web time and — worse — would lose it *invisibly*, producing a plausible but wrong
picture. Brave costs nothing to add because it is Chromium. Firefox costs one extra build target
because Gecko does not implement `background.service_worker`.
**Alternatives.** Chromium-only and ask the user to consolidate browsers; three separate codebases;
a native messaging host coordinating the browsers; inferring browser time from the desktop agent.
**Rejected because.** Asking the user to change their browsing habits to suit the telemetry tool is
the same error ADR-016 rejects for the desktop session. Three codebases triples the privacy surface
that must be audited — and the §11.2 no-host-permissions guarantee has to hold in *every* build, so
divergence is actively dangerous. A native messaging host would require host permissions and a
per-browser native manifest, adding a privileged local component for a problem that focus arbitration
already solves. The desktop agent is deferred out of V1 (ADR-016) and could not attribute domains in
any case.
**Trade-offs.** Firefox requires a **signed `.xpi`** (AMO unlisted self-distribution) because
temporary installs are wiped on restart — an external dependency with a review turnaround that must
be started early in Phase 9. Cross-browser overlap cannot be prevented at the source and must be
resolved server-side by arbitration, which means browser time is a union rather than a sum and
requires a property test to stay honest. Accepted: the alternative is under-counting web time or
double-counting it, and both destroy the metric.

---

*End of specification. No implementation has been performed.*
