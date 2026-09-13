// Root build file. Per-module configuration lives in app/build.gradle.kts.
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("com.android.library") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0" apply false
    // KSP version must match the Kotlin version above (2.1.0-<ksp-release>).
    id("com.google.devtools.ksp") version "2.1.0-1.0.29" apply false
}
