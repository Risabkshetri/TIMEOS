package com.timeos.core.sync

import org.json.JSONArray
import org.json.JSONObject

object IngestJson {
    fun serialize(request: IngestBatchRequest): String {
        val root = JSONObject()
        root.put("batch_id", request.batchId)
        root.put("device_id", request.deviceId)
        root.put("seq_from", request.seqFrom)
        root.put("seq_to", request.seqTo)
        val events = JSONArray()
        request.events.forEach { events.put(serializeEvent(it)) }
        root.put("events", events)
        return root.toString()
    }

    private fun serializeEvent(e: IngestEventPayload): JSONObject = JSONObject().apply {
        put("event_id", e.eventId)
        put("device_id", e.deviceId)
        put("seq", e.seq)
        put("ts_utc", e.tsUtcMillis)
        put("tz_offset_min", e.tzOffsetMinutes)
        put("tz_id", e.tzId)
        put("clock_flags", JSONArray(e.clockFlags))
        put("uptime_ms", e.uptimeMillis)
        put("type", e.type)
        put("source", e.source)
        put("payload", JSONObject(e.payload as Map<*, *>))
        put("schema_v", e.schemaVersion)
    }
}
