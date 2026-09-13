package com.timeos.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                TimeOSApp()
            }
        }
    }
}

/**
 * Root composable for Phase 1A. Re-checks [UsageAccess.isGranted] on every ON_RESUME lifecycle
 * event — required because Android delivers no callback when the user revokes Usage Access
 * from Settings and returns to the app (see docs/TIMEOS_ENGINEERING_SPEC.md §8.2).
 */
@Composable
fun TimeOSApp() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    var granted by remember { mutableStateOf(UsageAccess.isGranted(context)) }
    var settingsOpenFailed by remember { mutableStateOf(false) }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                granted = UsageAccess.isGranted(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    if (granted) {
        val deviceId = remember { DeviceId.get(context) }
        // Run an immediate catch-up drain on entering the granted state (§8.4 mitigation #2),
        // rather than waiting for the next periodic tick, so the diagnostic screen isn't empty.
        LaunchedEffect(Unit) { CollectionScheduler.runCatchUpNow(context) }
        DiagnosticScreen(deviceId = deviceId)
    } else {
        OnboardingScreen(
            onGrantClick = {
                settingsOpenFailed = !UsageAccess.openSettings(context)
            },
            settingsOpenFailed = settingsOpenFailed,
        )
    }
}
