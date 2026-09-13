package com.timeos.core.db

import com.timeos.core.collector.CollectionHealth
import com.timeos.core.collector.EventStore
import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent

private const val MAX_POLL_HISTORY = 20

/** Room-backed [EventStore] — the Phase 2 production implementation. */
class RoomEventStore(private val db: TimeOSDatabase) : EventStore {

    override suspend fun contains(eventId: String): Boolean = db.eventDao().contains(eventId)

    override suspend fun appendIfNew(events: List<TimeOSEvent>): Int {
        if (events.isEmpty()) return 0
        // insertAll (OnConflictStrategy.IGNORE) returns -1 for each row skipped as a duplicate
        // and the real rowId for each row actually inserted — counting non-(-1) entries is exact
        // and race-free, unlike diffing countAll() before/after.
        val rowIds = db.eventDao().insertAll(events.map { it.toEntity() })
        return rowIds.count { it != -1L }
    }

    override suspend fun getRecent(limit: Int): List<TimeOSEvent> =
        db.eventDao().getRecent(limit).map { it.toModel() }

    override suspend fun getCursor(): Long? = db.syncMetaDao().get()?.cursorTsUtcMillis

    override suspend fun setCursor(tsUtcMillis: Long) {
        val meta = db.syncMetaDao().get() ?: SyncMetaEntity()
        db.syncMetaDao().upsert(meta.copy(cursorTsUtcMillis = tsUtcMillis))
    }

    override suspend fun nextSeq(): Long {
        val meta = db.syncMetaDao().get() ?: SyncMetaEntity()
        val seq = meta.nextSeq
        db.syncMetaDao().upsert(meta.copy(nextSeq = seq + 1))
        return seq
    }

    override suspend fun recordPoll(atMillis: Long, appendedCount: Int) {
        val meta = db.syncMetaDao().get() ?: SyncMetaEntity()
        val timestamps = (parseCsv(meta.pollTimestampsCsv) + atMillis).takeLast(MAX_POLL_HISTORY)
        db.syncMetaDao().upsert(
            meta.copy(lastPollAtMillis = atMillis, pollTimestampsCsv = timestamps.joinToString(",")),
        )
    }

    override suspend fun recordPermissionLost(atMillis: Long) {
        val meta = db.syncMetaDao().get() ?: SyncMetaEntity()
        db.syncMetaDao().upsert(meta.copy(lastPermissionLostAtMillis = atMillis))
    }

    override suspend fun health(): CollectionHealth {
        val meta = db.syncMetaDao().get()
        return CollectionHealth(
            lastPollAtMillis = meta?.lastPollAtMillis,
            recentPollTimestamps = parseCsv(meta?.pollTimestampsCsv ?: ""),
            totalEventCount = db.eventDao().countAll(),
            lastPermissionLostAtMillis = meta?.lastPermissionLostAtMillis,
        )
    }

    private fun parseCsv(csv: String): List<Long> =
        if (csv.isEmpty()) emptyList() else csv.split(",").map { it.toLong() }
}

fun TimeOSEvent.toEntity(): EventEntity = EventEntity(
    id = eventId,
    deviceId = deviceId,
    seq = seq,
    tsUtcMillis = tsUtcMillis,
    tzOffsetMinutes = tzOffsetMinutes,
    tzId = tzId,
    clockFlags = clockFlags,
    uptimeMillis = uptimeMillis,
    type = type.name,
    source = source,
    payload = payload,
    schemaVersion = schemaVersion,
)

fun EventEntity.toModel(): TimeOSEvent = TimeOSEvent(
    eventId = id,
    deviceId = deviceId,
    seq = seq,
    tsUtcMillis = tsUtcMillis,
    tzOffsetMinutes = tzOffsetMinutes,
    tzId = tzId,
    clockFlags = clockFlags,
    uptimeMillis = uptimeMillis,
    type = EventType.valueOf(type),
    source = source,
    payload = payload,
    schemaVersion = schemaVersion,
)
