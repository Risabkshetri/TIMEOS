# TimeOS Android Collector

Target: Samsung Galaxy S24 FE (One UI), compileSdk/targetSdk 36, minSdk 29, Kotlin 2.1 + Compose.

**Status: Phase 3 complete** (see `docs/TIMEOS_ENGINEERING_SPEC.md` §38). The app collects real
`UsageStatsManager` events via a 15-minute `WorkManager` poll into a Room database, and syncs them
to a real FastAPI + PostgreSQL backend over HTTP with batching, gzip, retry/backoff, and
quarantine. Verified end-to-end on the physical S24 FE against the real Dockerized backend: enrolled
the device, synced real collected events, and confirmed in Postgres a contiguous `seq` range across
multiple accepted batches with zero duplicate event ids.

**Known artifact, not a bug:** 3 batches from early device testing (before the backend's
`GZipRequestMiddleware` fix landed) are permanently `QUARANTINED` — by design (§27#12), quarantined
batches are never auto-retried, so their events stay forever excluded from future sync attempts.
The diagnostic screen's "Unsynced events (total)" figure includes these dead events; "Eligible to
sync now" is the number that actually reflects what the next sync cycle will pick up.

**Not yet done:** the multi-day, zero-loss/zero-duplication Definition of Done criterion needs
longer unattended observation than a single session provides — the periodic `CollectionWorker` and
`SyncWorker` jobs are scheduled and running, so this accumulates passively going forward.

**Next: Phase 4** — sessionization and deterministic analytics (turning raw events into sessions,
coverage, activities, and `daily_metrics`).

## Modules

- `app/` — Compose UI, onboarding, `WorkManager` scheduling (`CollectionWorker`, `SyncWorker`),
  `BootReceiver`, Application class, dev-only sync config UI.
- `core/` — pure, unit-testable logic:
  - `collector/` — `UsageEventReader`, `EventMapper`, `CollectionRunner`, `CoverageTracker`.
  - `db/` — Room database (`EventEntity`/`EventDao`, `SyncBatchEntity`/`SyncBatchDao`,
    `SyncMetaEntity`/`SyncMetaDao`, `RoomEventStore`).
  - `sync/` — `BatchBuilder`, `BackoffPolicy`, `IngestApiClient`/`OkHttpIngestApiClient`,
    `SyncRunner`.

  `app` depends on `core`.

## Build & run

```bash
cd android
export ANDROID_HOME=~/Android/Sdk   # or wherever your SDK lives
echo "sdk.dir=$ANDROID_HOME" > local.properties   # git-ignored, machine-specific

./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.timeos.app/.MainActivity
```

### Testing sync against the local mock server

```bash
python3 ../tools/mock_ingest_server.py --port 8089
adb reverse tcp:8089 tcp:8089   # works over USB regardless of WiFi/cellular state
```

Then on the diagnostic screen's Sync panel, set Server URL to `http://127.0.0.1:8089` and enter
any device token (the mock server doesn't validate it), Save config, then Sync now.

## Tests

```bash
./gradlew :app:testDebugUnitTest :core:testDebugUnitTest   # 40 pure JVM unit tests
./gradlew :app:connectedDebugAndroidTest :core:connectedDebugAndroidTest
                                                             # 13 instrumented tests — needs a
                                                             # connected device or emulator
```
