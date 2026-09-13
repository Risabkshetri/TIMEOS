package com.timeos.core.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface SyncBatchDao {

    @Insert
    suspend fun insert(batch: SyncBatchEntity)

    @Update
    suspend fun update(batch: SyncBatchEntity)

    /** §26: "batches are sent strictly in seq order; a failed batch blocks later ones" — this is
     * the query that enforces it: there is always at most one batch in flight at a time. */
    @Query("SELECT * FROM sync_batches_local WHERE status = 'PENDING' ORDER BY seqFrom ASC LIMIT 1")
    suspend fun oldestPending(): SyncBatchEntity?

    @Query("SELECT COUNT(*) FROM sync_batches_local WHERE status = 'QUARANTINED'")
    suspend fun quarantinedCount(): Int

    @Query("SELECT COUNT(*) FROM sync_batches_local WHERE status = 'PENDING'")
    suspend fun pendingCount(): Int

    @Query("SELECT * FROM sync_batches_local ORDER BY createdAtMillis DESC LIMIT :limit")
    suspend fun recent(limit: Int): List<SyncBatchEntity>

    @Query("SELECT * FROM sync_batches_local WHERE batchId = :batchId")
    suspend fun get(batchId: String): SyncBatchEntity?
}
