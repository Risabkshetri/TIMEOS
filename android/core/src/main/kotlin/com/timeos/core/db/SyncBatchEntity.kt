package com.timeos.core.db

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * The "failed_batches" / batch ledger table from docs/TIMEOS_ENGINEERING_SPEC.md §26, §27#12:
 * one row per batch this device has ever attempted to build and send. `status` is one of
 * PENDING (not yet ACKed), ACKED (server confirmed, its events are marked synced), or
 * QUARANTINED (a permanent 4xx — never retried; surfaced in-app per §27#12).
 */
@Entity(
    tableName = "sync_batches_local",
    indices = [Index(value = ["status"])],
)
data class SyncBatchEntity(
    @PrimaryKey val batchId: String,
    val createdAtMillis: Long,
    val seqFrom: Long,
    val seqTo: Long,
    val eventCount: Int,
    val status: String,
    val attemptCount: Int = 0,
    val lastAttemptAtMillis: Long? = null,
    val lastErrorCode: Int? = null,
    val lastErrorMessage: String? = null,
)

object SyncBatchStatus {
    const val PENDING = "PENDING"
    const val ACKED = "ACKED"
    const val QUARANTINED = "QUARANTINED"
}
