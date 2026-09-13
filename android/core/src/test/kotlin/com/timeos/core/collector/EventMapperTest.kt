package com.timeos.core.collector

import com.timeos.core.model.EventType
import com.timeos.core.model.RawUsageEvent
import java.util.TimeZone
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EventMapperTest {

    private val tz: TimeZone = TimeZone.getTimeZone("Asia/Kolkata") // fixed +05:30, no DST

    @Test
    fun `deriveEventId is deterministic for identical raw events`() {
        val raw = RawUsageEvent("com.example.app", 1_700_000_000_000L, EventType.APP_FOREGROUND)
        val id1 = EventMapper.deriveEventId("device-1", raw)
        val id2 = EventMapper.deriveEventId("device-1", raw)
        assertEquals(id1, id2)
    }

    @Test
    fun `deriveEventId differs across devices for the same raw event`() {
        val raw = RawUsageEvent("com.example.app", 1_700_000_000_000L, EventType.APP_FOREGROUND)
        val idA = EventMapper.deriveEventId("device-A", raw)
        val idB = EventMapper.deriveEventId("device-B", raw)
        assertNotEquals(idA, idB)
    }

    @Test
    fun `map includes package in payload for app foreground`() {
        val raw = RawUsageEvent("com.example.app", 1_700_000_000_000L, EventType.APP_FOREGROUND)
        val event = EventMapper.map(
            raw = raw,
            deviceId = "device-1",
            eventId = "id-1",
            seq = 0,
            nowWallClockMillis = raw.timeStampMillis + 60_000,
            nowElapsedRealtimeMillis = 5_000_000L,
            timeZone = tz,
        )
        assertEquals("com.example.app", event.payload["package"])
        assertEquals(EventType.APP_FOREGROUND, event.type)
        assertEquals("android", event.source)
        assertEquals(1, event.schemaVersion)
    }

    @Test
    fun `map omits payload for screen events`() {
        val raw = RawUsageEvent("unused", 1_700_000_000_000L, EventType.SCREEN_OFF)
        val event = EventMapper.map(
            raw = raw,
            deviceId = "device-1",
            eventId = "id-2",
            seq = 1,
            nowWallClockMillis = raw.timeStampMillis,
            nowElapsedRealtimeMillis = 1_000L,
            timeZone = tz,
        )
        assertTrue(event.payload.isEmpty())
    }

    @Test
    fun `map records the timezone offset in minutes`() {
        val raw = RawUsageEvent("com.example.app", 1_700_000_000_000L, EventType.APP_FOREGROUND)
        val event = EventMapper.map(
            raw = raw,
            deviceId = "d",
            eventId = "id",
            seq = 0,
            nowWallClockMillis = raw.timeStampMillis,
            nowElapsedRealtimeMillis = 0L,
            timeZone = tz,
        )
        assertEquals(330, event.tzOffsetMinutes) // Asia/Kolkata is UTC+5:30
        assertEquals("Asia/Kolkata", event.tzId)
    }

    @Test
    fun `map approximates uptime at event time assuming no reboot`() {
        val eventTs = 1_700_000_000_000L
        val nowWall = eventTs + 10_000 // 10s after the event
        val nowElapsed = 500_000L
        val raw = RawUsageEvent("com.example.app", eventTs, EventType.APP_FOREGROUND)
        val event = EventMapper.map(
            raw = raw,
            deviceId = "d",
            eventId = "id",
            seq = 0,
            nowWallClockMillis = nowWall,
            nowElapsedRealtimeMillis = nowElapsed,
            timeZone = tz,
        )
        assertEquals(nowElapsed - 10_000, event.uptimeMillis)
    }
}
