package com.timeos.app

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * Schedules [CollectionWorker]. Per docs/TIMEOS_ENGINEERING_SPEC.md §8.3: polling, not a
 * foreground service — UsageStatsManager.queryEvents is a historical query, so TimeOS only needs
 * to drain the OS buffer before it expires (§8.4), not observe in real time.
 */
object CollectionScheduler {
    private const val PERIODIC_WORK_NAME = "timeos-usage-collection-periodic"
    private const val CATCHUP_WORK_NAME = "timeos-usage-collection-catchup"
    private const val POLL_INTERVAL_MINUTES = 15L

    /** Idempotent: safe to call on every process start (Application.onCreate, boot, etc.). */
    fun ensureScheduled(context: Context) {
        val request = PeriodicWorkRequestBuilder<CollectionWorker>(POLL_INTERVAL_MINUTES, TimeUnit.MINUTES)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    /**
     * Immediate catch-up drain: run on app launch and right after boot (§8.4 mitigation #2) so
     * the diagnostic screen reflects fresh data without waiting for the next periodic tick.
     */
    fun runCatchUpNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<CollectionWorker>().build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            CATCHUP_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}
