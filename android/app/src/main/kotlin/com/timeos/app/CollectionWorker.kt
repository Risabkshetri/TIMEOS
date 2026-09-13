package com.timeos.app

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.timeos.core.collector.CollectionRunner
import com.timeos.core.collector.PersistentEventStore
import com.timeos.core.collector.UsageEventReader

/**
 * WorkManager entry point for one collection cycle. Thin by design — all the actual logic lives
 * in [CollectionRunner], which is unit-tested without any Worker/WorkManager test infrastructure.
 * Re-checks Usage Access on every run: Android delivers no callback when it is revoked (§8.2).
 */
class CollectionWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val deviceId = DeviceId.get(applicationContext)
        val store = PersistentEventStore(applicationContext)
        val source = UsageEventReader(applicationContext)

        val runner = CollectionRunner(
            source = source,
            store = store,
            deviceId = deviceId,
            isUsageAccessGranted = { UsageAccess.isGranted(applicationContext) },
        )
        runner.runOnce()

        return Result.success()
    }
}
