# TimeOS Android Collector

Target: Samsung Galaxy S24 FE (One UI), compileSdk/targetSdk 36, minSdk 29, Kotlin 2.1 + Compose.

**Status: Phase 1B complete** (see `docs/TIMEOS_ENGINEERING_SPEC.md` §38). The app collects real
`UsageStatsManager` events via a 15-minute `WorkManager` poll, persists them locally, and shows a
diagnostic screen with reconstructed sessions and collector health. The full First Validation Loop
(install → grant → query succeeds → real usage appears → survives force-stop → survives no
network) has passed end-to-end on the physical S24 FE. Zero network calls — no `INTERNET`
permission is declared.

**Not yet done:** the 24-hour, ≥95%-coverage / <1%-battery Definition of Done criterion needs
longer unattended observation than a single session provides — let the app run normally for a day
and check the diagnostic screen's health panel.

**Next: Phase 2** — Room-backed local storage with a real pending-sync queue, replacing the
Phase 1B `PersistentEventStore` (SharedPreferences + JSON, intentionally temporary).

## Modules

- `app/` — Compose UI, onboarding, `WorkManager` scheduling, `BootReceiver`, Application class.
- `core/` — pure, unit-testable collection logic (`UsageEventReader`, `EventMapper`,
  `CollectionRunner`, `CoverageTracker`, `PersistentEventStore`). `app` depends on `core`.

## Build & run

```bash
cd android
export ANDROID_HOME=~/Android/Sdk   # or wherever your SDK lives
echo "sdk.dir=$ANDROID_HOME" > local.properties   # git-ignored, machine-specific

./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.timeos.app/.MainActivity
```

## Tests

```bash
./gradlew :app:testDebugUnitTest :core:testDebugUnitTest   # 23 pure JVM unit tests
./gradlew :app:connectedDebugAndroidTest                    # 8 instrumented tests — needs a
                                                             # connected device or emulator
```
