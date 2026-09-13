plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.timeos.app"
    // Per docs/TIMEOS_ENGINEERING_SPEC.md §4.3: build-tools 36.0.0 is the installed toolchain,
    // so compileSdk/targetSdk target 36 rather than the android-37 platform whose build-tools
    // are absent.
    compileSdk = 36

    defaultConfig {
        applicationId = "com.timeos.app"
        // minSdk 29 (Android 10): the floor below which non-resettable identifiers become
        // available, which TimeOS must never rely on regardless (see DeviceId.kt).
        minSdk = 29
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.0-phase2"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

dependencies {
    implementation(project(":core"))

    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    // EncryptedSharedPreferences (AndroidKeystore-backed) for the device ID — see DeviceId.kt.
    implementation("androidx.security:security-crypto:1.1.0-alpha06")

    // Referenced directly (TimeOSDatabase.getInstance, withTransaction), not just transitively
    // via :core, which declares Room as `implementation` rather than `api`.
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")

    // OkHttpIngestApiClient's default `client: OkHttpClient = OkHttpClient()` parameter compiles
    // into every call site, so this needs to be on :app's own classpath, not just :core's.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14")
    testImplementation("androidx.test:core:1.6.1")

    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.work:work-testing:2.10.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
