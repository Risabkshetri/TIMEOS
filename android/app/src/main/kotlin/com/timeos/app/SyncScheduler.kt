package com.timeos.app

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * Schedules [SyncWorker]. Unlike [CollectionScheduler], sync REQUIRES connectivity — the one
 * WorkManager constraint the collector deliberately never has (§8.3, §26).
 */
object SyncScheduler {
    private const val PERIODIC_WORK_NAME = "timeos-sync-periodic"
    private const val IMMEDIATE_WORK_NAME = "timeos-sync-immediate"
    private const val SYNC_INTERVAL_MINUTES = 15L

    fun ensureScheduled(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = PeriodicWorkRequestBuilder<SyncWorker>(SYNC_INTERVAL_MINUTES, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    /** Manual "Sync now" trigger — still requires connectivity; WorkManager holds it until
     * the constraint is satisfied rather than failing immediately when offline.
     *
     * Uses REPLACE, not KEEP: KEEP dedupes against the unique work name's PREVIOUS run even
     * after it reached a terminal SUCCEEDED state, so every tap after the first silently
     * short-circuited ("Status ... is SUCCEEDED ; not doing any work" in WM-WorkerWrapper logs)
     * instead of actually invoking SyncWorker again. REPLACE always schedules a fresh run. */
    fun runNow(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}
