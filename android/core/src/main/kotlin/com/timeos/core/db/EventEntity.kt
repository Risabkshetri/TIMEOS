package com.timeos.core.db

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Room-backed local event store. Replaces Phase 1B's PersistentEventStore (SharedPreferences +
 * JSON) — see docs/TIMEOS_ENGINEERING_SPEC.md §8.8, §38 Phase 2.
 *
 * `id` is the deterministic event_id from EventMapper.deriveEventId — inserts use
 * OnConflictStrategy.IGNORE, which is what makes draining an overlapping poll window idempotent.
 * Indexed on (synced, seq) per §8.8, matching the two access patterns that matter: "give me the
 * oldest unsynced events in order" (batch building) and "is this id already present" (dedupe).
 */
@Entity(
    tableName = "events",
    indices = [Index(value = ["synced", "seq"])],
)
data class EventEntity(
    @PrimaryKey val id: String,
    val deviceId: String,
    val seq: Long,
    val tsUtcMillis: Long,
    val tzOffsetMinutes: Int,
    val tzId: String,
    val clockFlags: List<String>,
    val uptimeMillis: Long,
    val type: String,
    val source: String,
    val payload: Map<String, String>,
    val schemaVersion: Int,
    val synced: Boolean = false,
    val batchId: String? = null,
    val syncedAtMillis: Long? = null,
)
