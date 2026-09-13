package com.timeos.core.collector

import com.timeos.core.model.TimeOSEvent

data class CollectionHealth(
    val lastPollAtMillis: Long?,
    val recentPollTimestamps: List<Long>,
    val totalEventCount: Int,
    val lastPermissionLostAtMillis: Long?,
)

/**
 * Local persistence contract for collected events. [com.timeos.core.db.RoomEventStore] is the
 * production implementation as of Phase 2 (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 2, §8.8),
 * replacing Phase 1B's SharedPreferences-backed PersistentEventStore.
 *
 * All methods are suspend: Room's generated DAO implementations dispatch onto Room's own query
 * executor, so callers (CollectionWorker's coroutine, DiagnosticScreen's LaunchedEffect) never
 * block their own thread — notably the Compose main thread, which a synchronous call here would
 * have blocked.
 */
interface EventStore {
    suspend fun contains(eventId: String): Boolean
    suspend fun appendIfNew(events: List<TimeOSEvent>): Int
    suspend fun getRecent(limit: Int): List<TimeOSEvent>
    suspend fun getCursor(): Long?
    suspend fun setCursor(tsUtcMillis: Long)
    suspend fun nextSeq(): Long
    suspend fun recordPoll(atMillis: Long, appendedCount: Int)
    suspend fun recordPermissionLost(atMillis: Long)
    suspend fun health(): CollectionHealth
}
