# TimeOS Android Collector

Target: Samsung Galaxy S24 FE (One UI), compileSdk/targetSdk 36, minSdk 29, Kotlin 2.1 + Compose.

**Status: Phase 1A complete** (see `docs/TIMEOS_ENGINEERING_SPEC.md` §38). The app installs,
explains why Usage Access is needed, opens the OS settings screen for it, and correctly detects
granted/revoked state on every resume — with a generated device ID and zero collection, storage,
or network code. Verified end-to-end on the physical S24 FE.

**Next: Phase 1B** — `UsageStatsManager` collection, `EventMapper`, a 15-minute `WorkManager`
poll, and the collection diagnostic screen. Gated on 1A per the spec's explicit ordering rule.

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
./gradlew :app:testDebugUnitTest              # JVM unit tests (manifest privacy allowlist,
                                               # UsageAccess permission-state detection)
./gradlew :app:connectedDebugAndroidTest       # instrumented Compose UI tests — needs a
                                               # connected device or emulator
```
