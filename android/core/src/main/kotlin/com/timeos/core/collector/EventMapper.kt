package com.timeos.core.collector

import com.timeos.core.model.EventType
import com.timeos.core.model.RawUsageEvent
import com.timeos.core.model.TimeOSEvent
import java.nio.charset.StandardCharsets
import java.util.TimeZone
import java.util.UUID

/**
 * Pure mapping from a [RawUsageEvent] to the canonical TimeOS event envelope
 * (docs/TIMEOS_ENGINEERING_SPEC.md §9.1). Deliberately takes no Context and calls no Android or
 * system-clock APIs directly — every time-dependent input is passed in — so this is fully
 * unit-testable without Robolectric.
 */
object EventMapper {

    /**
     * Deterministic event_id derived from (device, package, timestamp, type), so that draining
     * the same OS event twice across overlapping poll windows (§8.3) always yields the same id —
     * this is what makes the overlap-and-dedupe strategy safe rather than duplicate-generating.
     */
    fun deriveEventId(deviceId: String, raw: RawUsageEvent): String {
        val key = "$deviceId|${raw.packageName}|${raw.timeStampMillis}|${raw.eventType.name}"
        return UUID.nameUUIDFromBytes(key.toByteArray(StandardCharsets.UTF_8)).toString()
    }

    fun map(
        raw: RawUsageEvent,
        deviceId: String,
        eventId: String,
        seq: Long,
        nowWallClockMillis: Long,
        nowElapsedRealtimeMillis: Long,
        timeZone: TimeZone,
    ): TimeOSEvent {
        // Approximates elapsedRealtime AT the event's occurrence, assuming no reboot happened
        // between the event and now. This breaks across a reboot (elapsedRealtime resets to 0),
        // which is an accepted Phase 1B limitation — full clock-drift handling is server-side
        // (§13, clock_suspect) and not implemented on-device.
        val approxUptimeAtEvent = nowElapsedRealtimeMillis - (nowWallClockMillis - raw.timeStampMillis)

        val payload: Map<String, String> = when (raw.eventType) {
            EventType.APP_FOREGROUND, EventType.APP_BACKGROUND, EventType.USER_INTERACTION ->
                mapOf("package" to raw.packageName)
            else -> emptyMap()
        }

        return TimeOSEvent(
            eventId = eventId,
            deviceId = deviceId,
            seq = seq,
            tsUtcMillis = raw.timeStampMillis,
            tzOffsetMinutes = timeZone.getOffset(raw.timeStampMillis) / 60_000,
            tzId = timeZone.id,
            clockFlags = emptyList(),
            uptimeMillis = approxUptimeAtEvent,
            type = raw.eventType,
            source = "android",
            payload = payload,
            schemaVersion = 1,
        )
    }
}
