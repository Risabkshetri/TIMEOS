package com.timeos.core.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface EventDao {

    /** IGNORE on conflict is the whole idempotency mechanism: draining an overlapping poll
     * window re-inserts already-seen ids, which this silently no-ops rather than erroring. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertAll(events: List<EventEntity>): List<Long>

    @Query("SELECT EXISTS(SELECT 1 FROM events WHERE id = :id)")
    suspend fun contains(id: String): Boolean

    @Query("SELECT * FROM events ORDER BY seq DESC LIMIT :limit")
    suspend fun getRecent(limit: Int): List<EventEntity>

    @Query("SELECT * FROM events WHERE synced = 0 AND batchId IS NULL ORDER BY seq ASC LIMIT :limit")
    suspend fun getUnbatchedOrderedBySeq(limit: Int): List<EventEntity>

    @Query("SELECT * FROM events WHERE batchId = :batchId ORDER BY seq ASC")
    suspend fun getByBatchId(batchId: String): List<EventEntity>

    @Query("UPDATE events SET batchId = :batchId WHERE id IN (:ids)")
    suspend fun assignBatch(ids: List<String>, batchId: String)

    /** Releases events back to the unbatched pool — used when a batch is quarantined or a batch
     * row is otherwise abandoned, so its events don't become permanently stuck. */
    @Query("UPDATE events SET batchId = NULL WHERE batchId = :batchId")
    suspend fun clearBatch(batchId: String)

    @Query("UPDATE events SET synced = 1, syncedAtMillis = :syncedAtMillis WHERE batchId = :batchId")
    suspend fun markBatchSynced(batchId: String, syncedAtMillis: Long)

    @Query("SELECT COUNT(*) FROM events")
    suspend fun countAll(): Int

    @Query("SELECT COUNT(*) FROM events WHERE synced = 0")
    suspend fun countUnsynced(): Int

    /** Subset of [countUnsynced] that isn't tied up in a quarantined batch — i.e. events that
     * will actually be picked up by the next sync cycle. The difference between the two counts
     * is events permanently stuck in a quarantined batch (never auto-retried, see
     * [SyncRunner][com.timeos.core.sync.SyncRunner]'s doc comment on why), which "unsynced"
     * alone conflates with genuinely-pending work. */
    @Query("SELECT COUNT(*) FROM events WHERE synced = 0 AND batchId IS NULL")
    suspend fun countEligibleToSync(): Int

    /** §8.8 retention: unsynced rows are never deleted; synced rows are pruned 7 days after sync. */
    @Query("DELETE FROM events WHERE synced = 1 AND syncedAtMillis < :beforeMillis")
    suspend fun pruneSyncedOlderThan(beforeMillis: Long): Int

    /** Backpressure (§8.8): if the local store grows too large, prune oldest *synced* rows first.
     * Never touches unsynced rows — those must survive until they actually sync. */
    @Query(
        "DELETE FROM events WHERE id IN " +
            "(SELECT id FROM events WHERE synced = 1 ORDER BY seq ASC LIMIT :count)",
    )
    suspend fun deleteOldestSynced(count: Int): Int
}
