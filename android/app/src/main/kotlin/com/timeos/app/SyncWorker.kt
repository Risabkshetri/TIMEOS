package com.timeos.app

import android.content.Context
import androidx.room.withTransaction
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.timeos.core.db.TimeOSDatabase
import com.timeos.core.sync.GzipUtil
import com.timeos.core.sync.IngestApiClient
import com.timeos.core.sync.IngestBatchRequest
import com.timeos.core.sync.IngestJson
import com.timeos.core.sync.OkHttpIngestApiClient
import com.timeos.core.sync.SyncRunResult
import com.timeos.core.sync.SyncRunner
import com.timeos.core.sync.toPayload

/**
 * WorkManager entry point for sync. Drains the queue by looping [SyncRunner.runOnce] while each
 * cycle resolves a batch (Synced or Quarantined) — the natural continuation cases — stopping on
 * NothingToSync, WaitingForBackoff, or a Retrying result (no point spinning immediately into the
 * same failure). [MAX_CYCLES_PER_RUN] bounds worst-case work per invocation.
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val baseUrl = SyncConfig.getBaseUrl(applicationContext)
        if (baseUrl.isNullOrBlank()) {
            // No server configured yet (default state, and Phase 3's real backend/enrollment
            // doesn't exist yet) — nothing to do, and this is not a failure.
            return Result.success()
        }

        val db = TimeOSDatabase.getInstance(applicationContext)
        val deviceId = DeviceId.get(applicationContext)
        val apiClient: IngestApiClient = OkHttpIngestApiClient(
            baseUrl = baseUrl,
            deviceToken = { DeviceToken.get(applicationContext) ?: "" },
        )

        val runner = SyncRunner(
            eventDao = db.eventDao(),
            batchDao = db.syncBatchDao(),
            syncMetaDao = db.syncMetaDao(),
            apiClient = apiClient,
            deviceId = deviceId,
            estimateGzipSize = { chunk -> estimateGzipBytes(deviceId, chunk) },
            runInTransaction = { block -> db.withTransaction { block() } },
        )

        repeat(MAX_CYCLES_PER_RUN) {
            when (runner.runOnce()) {
                is SyncRunResult.Synced, is SyncRunResult.Quarantined -> return@repeat
                is SyncRunResult.NothingToSync,
                is SyncRunResult.WaitingForBackoff,
                is SyncRunResult.Retrying,
                -> return Result.success()
            }
        }
        return Result.success()
    }

    private fun estimateGzipBytes(deviceId: String, chunk: List<com.timeos.core.model.TimeOSEvent>): Long {
        if (chunk.isEmpty()) return 0L
        val request = IngestBatchRequest(
            batchId = "estimate",
            deviceId = deviceId,
            seqFrom = chunk.first().seq,
            seqTo = chunk.last().seq,
            events = chunk.map { it.toPayload() },
        )
        return GzipUtil.gzip(IngestJson.serialize(request).toByteArray(Charsets.UTF_8)).size.toLong()
    }

    companion object {
        private const val MAX_CYCLES_PER_RUN = 50
    }
}
