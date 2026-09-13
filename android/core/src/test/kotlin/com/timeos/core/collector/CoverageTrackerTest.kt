package com.timeos.core.collector

import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CoverageTrackerTest {

    private fun event(type: EventType, tsMillis: Long, pkg: String? = null): TimeOSEvent = TimeOSEvent(
        eventId = "id-$tsMillis-$type",
        deviceId = "device-1",
        seq = 0,
        tsUtcMillis = tsMillis,
        tzOffsetMinutes = 0,
        tzId = "UTC",
        clockFlags = emptyList(),
        uptimeMillis = tsMillis,
        type = type,
        source = "android",
        payload = pkg?.let { mapOf("package" to it) } ?: emptyMap(),
        schemaVersion = 1,
    )

    @Test
    fun `simple foreground then background produces one session`() {
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.a"),
            event(EventType.APP_BACKGROUND, 10_000L, "com.a"),
        )
        val sessions = CoverageTracker.buildSessions(events, nowMillis = 20_000L)
        assertEquals(1, sessions.size)
        assertEquals("com.a", sessions[0].packageName)
        assertEquals(10_000L, sessions[0].durationMillis)
    }

    @Test
    fun `sessions shorter than 3 seconds are dropped`() {
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.a"),
            event(EventType.APP_BACKGROUND, 1_000L, "com.a"),
        )
        val sessions = CoverageTracker.buildSessions(events, nowMillis = 5_000L)
        assertTrue(sessions.isEmpty())
    }

    @Test
    fun `same app bounce within merge gap is merged into one session`() {
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.a"),
            event(EventType.APP_BACKGROUND, 5_000L, "com.a"),
            event(EventType.APP_FOREGROUND, 10_000L, "com.a"), // 5s gap, within the 30s merge window
            event(EventType.APP_BACKGROUND, 20_000L, "com.a"),
        )
        val sessions = CoverageTracker.buildSessions(events, nowMillis = 30_000L)
        assertEquals(1, sessions.size)
        assertEquals(0L, sessions[0].startMillis)
        assertEquals(20_000L, sessions[0].endMillis)
    }

    @Test
    fun `switching apps closes the previous session`() {
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.a"),
            event(EventType.APP_FOREGROUND, 10_000L, "com.b"),
        )
        val sessions = CoverageTracker.buildSessions(events, nowMillis = 20_000L)
            .sortedBy { it.startMillis }
        assertEquals(2, sessions.size)
        assertEquals("com.a", sessions[0].packageName)
        assertEquals(10_000L, sessions[0].endMillis)
        assertEquals("com.b", sessions[1].packageName)
    }

    @Test
    fun `screen off closes an open session`() {
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.a"),
            event(EventType.SCREEN_OFF, 15_000L),
        )
        val sessions = CoverageTracker.buildSessions(events, nowMillis = 100_000L)
        assertEquals(1, sessions.size)
        assertEquals(15_000L, sessions[0].endMillis)
    }

    @Test
    fun `rapid sub-3s bursts of the same app are invisible in buildSessions but appear in summarizeByPackage`() {
        // Reproduces a real observation: an app opened for quick glances (each dwell under the
        // 3s noise floor), interleaved with switches back to the launcher. Every individual
        // dwell is filtered as noise, so the app has zero entries in buildSessions() even though
        // it has real, frequent activity — summarizeByPackage() must still surface it.
        val events = listOf(
            event(EventType.APP_FOREGROUND, 0L, "com.whatsapp"),
            event(EventType.APP_BACKGROUND, 1_500L, "com.whatsapp"),
            event(EventType.APP_FOREGROUND, 40_000L, "com.launcher"),
            event(EventType.APP_BACKGROUND, 41_000L, "com.launcher"),
            event(EventType.APP_FOREGROUND, 42_000L, "com.whatsapp"),
            event(EventType.APP_BACKGROUND, 43_800L, "com.whatsapp"),
            event(EventType.APP_FOREGROUND, 80_000L, "com.launcher"),
        )

        val sessions = CoverageTracker.buildSessions(events, nowMillis = 100_000L)
        assertTrue(sessions.none { it.packageName == "com.whatsapp" })

        val summary = CoverageTracker.summarizeByPackage(events, nowMillis = 100_000L)
        val whatsapp = summary.first { it.packageName == "com.whatsapp" }
        assertEquals(2, whatsapp.openCount)
        assertEquals(1_500L + 1_800L, whatsapp.totalMillis)
    }

    @Test
    fun `runaway session is truncated at the 4 hour cap`() {
        val fourHoursMillis = 4 * 60 * 60 * 1000L
        val events = listOf(event(EventType.APP_FOREGROUND, 0L, "com.a"))
        val sessions = CoverageTracker.buildSessions(events, nowMillis = fourHoursMillis + 3_600_000L)
        assertEquals(1, sessions.size)
        assertTrue(sessions[0].truncated)
        assertEquals(fourHoursMillis, sessions[0].durationMillis)
    }
}
