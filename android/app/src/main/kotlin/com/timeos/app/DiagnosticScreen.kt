package com.timeos.app

import android.content.Context
import android.content.pm.PackageManager
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.timeos.core.collector.AppActivitySummary
import com.timeos.core.collector.CollectionHealth
import com.timeos.core.collector.CoverageTracker
import com.timeos.core.collector.LocalSession
import com.timeos.core.db.RoomEventStore
import com.timeos.core.db.TimeOSDatabase
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay

/**
 * Collection + sync diagnostic screen (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 1B, Phase 2).
 * Supersedes Phase 1A's PermissionGrantedScreen.
 */
@Composable
fun DiagnosticScreen(deviceId: String) {
    val context = LocalContext.current
    var health by remember { mutableStateOf<CollectionHealth?>(null) }
    var sessions by remember { mutableStateOf<List<LocalSession>>(emptyList()) }
    var appSummary by remember { mutableStateOf<List<AppActivitySummary>>(emptyList()) }
    var syncStatus by remember { mutableStateOf<SyncStatusUi?>(null) }
    var refreshTick by remember { mutableIntStateOf(0) }

    LaunchedEffect(refreshTick) {
        val db = TimeOSDatabase.getInstance(context)
        val store = RoomEventStore(db)
        health = store.health()
        val events = store.getRecent(500)
        val now = System.currentTimeMillis()
        sessions = CoverageTracker.buildSessions(events, now).take(30)
        appSummary = CoverageTracker.summarizeByPackage(events, now).take(15)

        val meta = db.syncMetaDao().get()
        syncStatus = SyncStatusUi(
            unsyncedCount = db.eventDao().countUnsynced(),
            pendingBatches = db.syncBatchDao().pendingCount(),
            quarantinedBatches = db.syncBatchDao().quarantinedCount(),
            lastSyncAttemptAtMillis = meta?.lastSyncAttemptAtMillis,
            lastSyncResult = meta?.lastSyncResult,
            baseUrl = SyncConfig.getBaseUrl(context),
        )
    }

    LaunchedEffect(Unit) {
        while (true) {
            delay(3_000)
            refreshTick++
        }
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
        ) {
            Text("TimeOS — Diagnostic", style = MaterialTheme.typography.headlineSmall)
            Text(
                text = "Device ID: $deviceId",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp),
            )

            Spacer(Modifier.height(16.dp))
            HealthPanel(health)

            Spacer(Modifier.height(12.dp))
            Row {
                Button(onClick = { CollectionScheduler.runCatchUpNow(context) }) {
                    Text("Collect now")
                }
                Spacer(Modifier.width(12.dp))
                OutlinedButton(onClick = { refreshTick++ }) {
                    Text("Refresh")
                }
            }

            Spacer(Modifier.height(20.dp))
            SyncPanel(syncStatus, onRefresh = { refreshTick++ })

            Spacer(Modifier.height(20.dp))
            Text("App activity (raw, last 500 events)", style = MaterialTheme.typography.titleMedium)
            Text(
                text = "Every recorded open, including brief ones under 3s that the session " +
                    "view below filters out as noise. If an app you used doesn't show up here, " +
                    "it genuinely wasn't observed — if it shows up here but not below, it was " +
                    "used only in quick bursts.",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
            )
            if (appSummary.isEmpty()) {
                Text("No app activity recorded yet.", style = MaterialTheme.typography.bodyMedium)
            } else {
                appSummary.forEach { summary -> AppSummaryRow(context, summary) }
            }

            Spacer(Modifier.height(20.dp))
            Text("Recent sessions (≥3s, filtered)", style = MaterialTheme.typography.titleMedium)
            if (sessions.isEmpty()) {
                Text(
                    text = "No usage sessions recorded yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 8.dp),
                )
            } else {
                sessions.forEach { session -> SessionRow(context, session) }
            }
        }
    }
}

private data class SyncStatusUi(
    val unsyncedCount: Int,
    val pendingBatches: Int,
    val quarantinedBatches: Int,
    val lastSyncAttemptAtMillis: Long?,
    val lastSyncResult: String?,
    val baseUrl: String?,
)

@Composable
private fun SyncPanel(status: SyncStatusUi?, onRefresh: () -> Unit) {
    val context = LocalContext.current
    val timeFormat = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    var urlField by remember(status?.baseUrl) { mutableStateOf(status?.baseUrl ?: "") }
    var tokenField by remember { mutableStateOf(DeviceToken.get(context) ?: "") }

    Text("Sync", style = MaterialTheme.typography.titleMedium)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
            .padding(16.dp),
    ) {
        Text("Unsynced events: ${status?.unsyncedCount ?: 0}")
        Text("Pending batches: ${status?.pendingBatches ?: 0}")
        Text("Quarantined batches: ${status?.quarantinedBatches ?: 0}")
        Text(
            "Last sync attempt: " +
                (status?.lastSyncAttemptAtMillis?.let { timeFormat.format(Date(it)) } ?: "never"),
        )
        Text("Last result: ${status?.lastSyncResult ?: "—"}")

        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = urlField,
            onValueChange = { urlField = it },
            label = { Text("Server URL (e.g. http://127.0.0.1:8089 via adb reverse)") },
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = tokenField,
            onValueChange = { tokenField = it },
            label = { Text("Device token (dev/testing only — real enrollment is Phase 3)") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Row {
            Button(onClick = {
                SyncConfig.setBaseUrl(context, urlField.trim())
                DeviceToken.set(context, tokenField.trim())
                onRefresh()
            }) {
                Text("Save config")
            }
            Spacer(Modifier.width(12.dp))
            Button(onClick = { SyncScheduler.runNow(context) }) {
                Text("Sync now")
            }
        }
    }
}

@Composable
private fun AppSummaryRow(context: Context, summary: AppActivitySummary) {
    val label = remember(summary.packageName) { appLabel(context, summary.packageName) }
    val durationText = remember(summary.totalMillis) { formatDuration(summary.totalMillis) }
    Text(
        text = "$label — $durationText total, ${summary.openCount}x opened",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(vertical = 3.dp),
    )
}

@Composable
private fun HealthPanel(health: CollectionHealth?) {
    val timeFormat = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
            .padding(16.dp),
    ) {
        Text("Usage Access: granted", style = MaterialTheme.typography.bodyMedium)
        Text("Last poll: ${health?.lastPollAtMillis?.let { timeFormat.format(Date(it)) } ?: "never"}")
        Text("Observed cadence: ${cadenceText(health)}")
        Text("Events stored: ${health?.totalEventCount ?: 0}")
        Text(
            "Permission lost detected: " +
                (health?.lastPermissionLostAtMillis?.let { timeFormat.format(Date(it)) } ?: "never"),
        )
    }
}

private fun cadenceText(health: CollectionHealth?): String {
    val timestamps = health?.recentPollTimestamps
    if (timestamps == null || timestamps.size < 2) return "not enough data yet"
    val sorted = timestamps.sorted()
    val deltasMinutes = sorted.zipWithNext { a, b -> (b - a) / 60_000.0 }
    val avg = deltasMinutes.average()
    return "~${"%.1f".format(avg)} min (n=${sorted.size} polls)"
}

@Composable
private fun SessionRow(context: Context, session: LocalSession) {
    val timeFormat = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }
    val label = remember(session.packageName) { appLabel(context, session.packageName) }
    val durationText = remember(session.durationMillis) { formatDuration(session.durationMillis) }

    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Text(
            text = "$label — $durationText" + if (session.truncated) " (truncated)" else "",
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            text = "${timeFormat.format(Date(session.startMillis))}–${timeFormat.format(Date(session.endMillis))}",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

/**
 * Falls back to the raw package name when the label can't be resolved — expected for most
 * third-party apps, since TimeOS deliberately does not declare QUERY_ALL_PACKAGES or broad
 * <queries> visibility (§8.7, §35.11). A raw package name is still identifiable and, if
 * anything, more privacy-conservative than requesting broad package visibility for this.
 */
private fun appLabel(context: Context, packageName: String): String = try {
    val pm = context.packageManager
    val info = pm.getApplicationInfo(packageName, 0)
    pm.getApplicationLabel(info).toString()
} catch (e: PackageManager.NameNotFoundException) {
    packageName
}

private fun formatDuration(ms: Long): String {
    val totalSeconds = ms / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return if (minutes > 0) "${minutes}m ${seconds}s" else "${seconds}s"
}
