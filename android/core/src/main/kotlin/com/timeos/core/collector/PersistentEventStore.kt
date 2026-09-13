package com.timeos.core.collector

import android.content.Context
import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent
import org.json.JSONArray
import org.json.JSONObject

/**
 * SharedPreferences + JSON backed [EventStore]. Bounded to [MAX_EVENTS] to keep the single JSON
 * blob this stores from growing unbounded during Phase 1B validation, and re-reads/rewrites the
 * whole blob on every append — adequate for the hundreds-of-events-per-day volume this phase
 * validates, not meant to scale further. Phase 2 replaces this entirely with Room and a real
 * pending-sync queue (§38 Phase 2, §8.8).
 */
class PersistentEventStore(context: Context) : EventStore {
    private val prefs =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun contains(eventId: String): Boolean = readEvents().any { it.eventId == eventId }

    override fun appendIfNew(events: List<TimeOSEvent>): Int {
        if (events.isEmpty()) return 0
        val existing = readEvents().toMutableList()
        val existingIds = existing.mapTo(mutableSetOf()) { it.eventId }
        var appended = 0
        for (e in events) {
            if (existingIds.add(e.eventId)) {
                existing.add(e)
                appended++
            }
        }
        val trimmed = if (existing.size > MAX_EVENTS) {
            existing.sortedBy { it.tsUtcMillis }.takeLast(MAX_EVENTS)
        } else {
            existing
        }
        writeEvents(trimmed)
        return appended
    }

    override fun getRecent(limit: Int): List<TimeOSEvent> =
        readEvents().sortedByDescending { it.tsUtcMillis }.take(limit)

    override fun getCursor(): Long? = prefs.getLong(KEY_CURSOR, -1L).takeIf { it >= 0 }

    override fun setCursor(tsUtcMillis: Long) {
        prefs.edit().putLong(KEY_CURSOR, tsUtcMillis).apply()
    }

    override fun nextSeq(): Long {
        val next = prefs.getLong(KEY_NEXT_SEQ, 0L)
        prefs.edit().putLong(KEY_NEXT_SEQ, next + 1).apply()
        return next
    }

    override fun recordPoll(atMillis: Long, appendedCount: Int) {
        val timestamps = readLongList(KEY_POLL_TIMESTAMPS).toMutableList()
        timestamps.add(atMillis)
        val trimmed = timestamps.takeLast(MAX_POLL_HISTORY)
        prefs.edit()
            .putLong(KEY_LAST_POLL_AT, atMillis)
            .putString(KEY_POLL_TIMESTAMPS, JSONArray(trimmed).toString())
            .apply()
    }

    override fun recordPermissionLost(atMillis: Long) {
        prefs.edit().putLong(KEY_LAST_PERMISSION_LOST_AT, atMillis).apply()
    }

    override fun health(): CollectionHealth = CollectionHealth(
        lastPollAtMillis = prefs.getLong(KEY_LAST_POLL_AT, -1L).takeIf { it >= 0 },
        recentPollTimestamps = readLongList(KEY_POLL_TIMESTAMPS),
        totalEventCount = readEvents().size,
        lastPermissionLostAtMillis = prefs.getLong(KEY_LAST_PERMISSION_LOST_AT, -1L).takeIf { it >= 0 },
    )

    private fun readLongList(key: String): List<Long> {
        val raw = prefs.getString(key, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).map { arr.getLong(it) }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun readEvents(): List<TimeOSEvent> {
        val raw = prefs.getString(KEY_EVENTS, null) ?: return emptyList()
        return try {
            val arr = JSONArray(raw)
            (0 until arr.length()).mapNotNull { i -> deserialize(arr.getJSONObject(i)) }
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun writeEvents(events: List<TimeOSEvent>) {
        val arr = JSONArray()
        events.forEach { arr.put(serialize(it)) }
        prefs.edit().putString(KEY_EVENTS, arr.toString()).apply()
    }

    private fun serialize(e: TimeOSEvent): JSONObject = JSONObject().apply {
        put("event_id", e.eventId)
        put("device_id", e.deviceId)
        put("seq", e.seq)
        put("ts_utc_millis", e.tsUtcMillis)
        put("tz_offset_minutes", e.tzOffsetMinutes)
        put("tz_id", e.tzId)
        put("clock_flags", JSONArray(e.clockFlags))
        put("uptime_millis", e.uptimeMillis)
        put("type", e.type.name)
        put("source", e.source)
        put("payload", JSONObject(e.payload as Map<*, *>))
        put("schema_version", e.schemaVersion)
    }

    private fun deserialize(json: JSONObject): TimeOSEvent? = try {
        val payloadJson = json.getJSONObject("payload")
        val payload = payloadJson.keys().asSequence().associateWith { payloadJson.getString(it) }
        val flagsJson = json.getJSONArray("clock_flags")
        val flags = (0 until flagsJson.length()).map { flagsJson.getString(it) }
        TimeOSEvent(
            eventId = json.getString("event_id"),
            deviceId = json.getString("device_id"),
            seq = json.getLong("seq"),
            tsUtcMillis = json.getLong("ts_utc_millis"),
            tzOffsetMinutes = json.getInt("tz_offset_minutes"),
            tzId = json.getString("tz_id"),
            clockFlags = flags,
            uptimeMillis = json.getLong("uptime_millis"),
            type = EventType.valueOf(json.getString("type")),
            source = json.getString("source"),
            payload = payload,
            schemaVersion = json.getInt("schema_version"),
        )
    } catch (e: Exception) {
        null
    }

    companion object {
        private const val PREFS_NAME = "timeos_event_store"
        private const val KEY_EVENTS = "events"
        private const val KEY_CURSOR = "cursor"
        private const val KEY_NEXT_SEQ = "next_seq"
        private const val KEY_LAST_POLL_AT = "last_poll_at"
        private const val KEY_POLL_TIMESTAMPS = "poll_timestamps"
        private const val KEY_LAST_PERMISSION_LOST_AT = "last_permission_lost_at"
        private const val MAX_EVENTS = 3000
        private const val MAX_POLL_HISTORY = 20
    }
}
