package com.timeos.core.sync

import com.timeos.core.model.TimeOSEvent

/** Mirrors docs/TIMEOS_ENGINEERING_SPEC.md §9.1's event envelope, as sent over the wire. */
data class IngestEventPayload(
    val eventId: String,
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
)

/** Mirrors the /v1/ingest/batch request body from §12.3. */
data class IngestBatchRequest(
    val batchId: String,
    val deviceId: String,
    val seqFrom: Long,
    val seqTo: Long,
    val events: List<IngestEventPayload>,
)

fun TimeOSEvent.toPayload(): IngestEventPayload = IngestEventPayload(
    eventId = eventId,
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
