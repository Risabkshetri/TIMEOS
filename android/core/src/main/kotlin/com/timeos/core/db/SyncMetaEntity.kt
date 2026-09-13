package com.timeos.core.db

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Single-row table (id is always 0) holding the collector/sync singleton state: the collection
 * cursor and seq counter (moved here from Phase 1B's SharedPreferences so they commit atomically
 * with event inserts in one Room transaction — a real correctness improvement, not just a
 * storage-engine swap: a crash between "insert events" and "advance cursor" can no longer leave
 * them inconsistent), plus small collector/sync health fields surfaced on the diagnostic screen.
 */
@Entity(tableName = "sync_meta")
data class SyncMetaEntity(
    @PrimaryKey val id: Int = SINGLETON_ID,
    val cursorTsUtcMillis: Long? = null,
    val nextSeq: Long = 0,
    val lastPollAtMillis: Long? = null,
    val pollTimestampsCsv: String = "",
    val lastPermissionLostAtMillis: Long? = null,
    val lastSyncAttemptAtMillis: Long? = null,
    val lastSyncResult: String? = null,
) {
    companion object {
        const val SINGLETON_ID = 0
    }
}
