package com.timeos.core.collector

import com.timeos.core.model.TimeOSEvent

data class CollectionHealth(
    val lastPollAtMillis: Long?,
    val recentPollTimestamps: List<Long>,
    val totalEventCount: Int,
    val lastPermissionLostAtMillis: Long?,
)

/**
 * Phase 1B's minimal local persistence contract. [PersistentEventStore] is the production
 * implementation (SharedPreferences + JSON). This is deliberately superseded by a proper Room
 * schema with a real pending-sync queue in Phase 2 (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 2,
 * §8.8) — nothing here is meant to survive past validating the collection loop end to end.
 */
interface EventStore {
    fun contains(eventId: String): Boolean
    fun appendIfNew(events: List<TimeOSEvent>): Int
    fun getRecent(limit: Int): List<TimeOSEvent>
    fun getCursor(): Long?
    fun setCursor(tsUtcMillis: Long)
    fun nextSeq(): Long
    fun recordPoll(atMillis: Long, appendedCount: Int)
    fun recordPermissionLost(atMillis: Long)
    fun health(): CollectionHealth
}
