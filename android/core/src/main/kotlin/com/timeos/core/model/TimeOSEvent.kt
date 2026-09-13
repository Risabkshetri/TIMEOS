package com.timeos.core.model

/**
 * The canonical TimeOS event envelope (docs/TIMEOS_ENGINEERING_SPEC.md §9.1), as produced
 * on-device. The eventual sync payload (Phase 2/3) serializes this to the exact §9.1 JSON shape;
 * field names here are Kotlin-idiomatic rather than snake_case.
 */
data class TimeOSEvent(
    val eventId: String,
    val deviceId: String,
    val seq: Long,
    val tsUtcMillis: Long,
    val tzOffsetMinutes: Int,
    val tzId: String,
    val clockFlags: List<String>,
    val uptimeMillis: Long,
    val type: EventType,
    val source: String,
    val payload: Map<String, String>,
    val schemaVersion: Int,
)
