package com.timeos.core.sync

import com.timeos.core.collector.SystemTimeSource
import com.timeos.core.collector.TimeSource
import com.timeos.core.db.EventDao
import com.timeos.core.db.SyncBatchDao
import com.timeos.core.db.SyncBatchEntity
import com.timeos.core.db.SyncBatchStatus
import com.timeos.core.db.SyncMetaDao
import com.timeos.core.db.SyncMetaEntity
import com.timeos.core.db.toModel
import com.timeos.core.model.TimeOSEvent
import java.util.UUID

sealed interface SyncRunResult {
    data object NothingToSync : SyncRunResult
    data class Synced(val batchId: String, val eventCount: Int) : SyncRunResult
    data class Retrying(val batchId: String, val attempt: Int, val nextAttemptAtMillis: Long) : SyncRunResult
    data class Quarantined(val batchId: String, val code: Int) : SyncRunResult
    data object WaitingForBackoff : SyncRunResult
}

/**
 * One sync cycle. Per docs/TIMEOS_ENGINEERING_SPEC.md §26: batches are attempted strictly in seq
 * order — only the single oldest PENDING batch is ever touched per cycle, so a retryable failure
 * blocks later batches from being attempted until it clears. A QUARANTINED batch (permanent 4xx)
 * is excluded from "oldest pending" and does NOT block later batches — per §27#12, retrying a
 * permanently-invalid batch forever is the bug this design avoids.
 *
 * Depends directly on [EventDao]/[SyncBatchDao] rather than a separate repository abstraction:
 * Room DAO interfaces are plain Kotlin interfaces, so hand-written fakes make this fully
 * unit-testable without Robolectric or a real database (see SyncRunnerTest).
 */
class SyncRunner(
    private val eventDao: EventDao,
    private val batchDao: SyncBatchDao,
    private val syncMetaDao: SyncMetaDao,
    private val apiClient: IngestApiClient,
    private val deviceId: String,
    private val estimateGzipSize: (List<TimeOSEvent>) -> Long,
    private val runInTransaction: suspend (suspend () -> Unit) -> Unit = { it() },
    private val timeSource: TimeSource = SystemTimeSource(),
    private val batchIdGenerator: () -> String = { UUID.randomUUID().toString() },
    private val maxEventsToConsider: Int = BatchBuilder.MAX_EVENTS_PER_BATCH,
) {
    suspend fun runOnce(): SyncRunResult {
        val now = timeSource.wallClockMillis()

        val pending = batchDao.oldestPending()
        if (pending != null) {
            if (pending.attemptCount > 0) {
                val dueAt = (pending.lastAttemptAtMillis ?: 0L) +
                    BackoffPolicy.delayMillis(pending.attemptCount - 1)
                if (now < dueAt) return SyncRunResult.WaitingForBackoff
            }
            return attempt(pending, now)
        }

        val unbatched = eventDao.getUnbatchedOrderedBySeq(maxEventsToConsider)
        if (unbatched.isEmpty()) return SyncRunResult.NothingToSync

        val models = unbatched.map { it.toModel() }
        val request = BatchBuilder.buildBatches(models, deviceId, batchIdGenerator, estimateGzipSize).first()
        val entity = SyncBatchEntity(
            batchId = request.batchId,
            createdAtMillis = now,
            seqFrom = request.seqFrom,
            seqTo = request.seqTo,
            eventCount = request.events.size,
            status = SyncBatchStatus.PENDING,
        )
        // Atomic: a crash between these two writes must never leave a batch row with no events
        // assigned to it, or events assigned to a batch row that doesn't exist.
        runInTransaction {
            batchDao.insert(entity)
            eventDao.assignBatch(request.events.map { it.eventId }, request.batchId)
        }
        return attempt(entity, now, request)
    }

    private suspend fun attempt(
        batch: SyncBatchEntity,
        now: Long,
        prebuiltRequest: IngestBatchRequest? = null,
    ): SyncRunResult {
        val request = prebuiltRequest ?: IngestBatchRequest(
            batchId = batch.batchId,
            deviceId = deviceId,
            seqFrom = batch.seqFrom,
            seqTo = batch.seqTo,
            events = eventDao.getByBatchId(batch.batchId).map { it.toModel().toPayload() },
        )

        val outcome = apiClient.postBatch(request)
        val (result, resultSummary) = when (outcome) {
            is IngestOutcome.Success -> {
                eventDao.markBatchSynced(batch.batchId, now)
                batchDao.update(batch.copy(status = SyncBatchStatus.ACKED, lastAttemptAtMillis = now))
                SyncRunResult.Synced(batch.batchId, request.events.size) to "SUCCESS"
            }

            is IngestOutcome.ClientError -> {
                // Permanent: never retried. Events stay assigned to this batchId (excluded from
                // future batch-building) so the failure is durable and surfaced, not silently
                // retried forever — §27#12's explicit warning against a stuck-queue loop.
                batchDao.update(
                    batch.copy(
                        status = SyncBatchStatus.QUARANTINED,
                        attemptCount = batch.attemptCount + 1,
                        lastAttemptAtMillis = now,
                        lastErrorCode = outcome.code,
                        lastErrorMessage = outcome.body,
                    ),
                )
                SyncRunResult.Quarantined(batch.batchId, outcome.code) to "QUARANTINED:${outcome.code}"
            }

            is IngestOutcome.RateLimited, is IngestOutcome.ServerError, is IngestOutcome.NetworkFailure -> {
                val code = when (outcome) {
                    is IngestOutcome.RateLimited -> 429
                    is IngestOutcome.ServerError -> outcome.code
                    else -> null
                }
                val nextAttempt = batch.attemptCount + 1
                batchDao.update(
                    batch.copy(
                        attemptCount = nextAttempt,
                        lastAttemptAtMillis = now,
                        lastErrorCode = code,
                        lastErrorMessage = (outcome as? IngestOutcome.NetworkFailure)?.message,
                    ),
                )
                SyncRunResult.Retrying(
                    batch.batchId,
                    nextAttempt,
                    now + BackoffPolicy.delayMillis(nextAttempt - 1),
                ) to when (outcome) {
                    is IngestOutcome.NetworkFailure -> "NETWORK_FAILURE:${outcome.message}".take(200)
                    else -> "RETRYING:${code}"
                }
            }
        }

        val meta = syncMetaDao.get() ?: SyncMetaEntity()
        syncMetaDao.upsert(meta.copy(lastSyncAttemptAtMillis = now, lastSyncResult = resultSummary))
        return result
    }
}
