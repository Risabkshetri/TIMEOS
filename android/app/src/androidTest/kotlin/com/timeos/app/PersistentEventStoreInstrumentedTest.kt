package com.timeos.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.timeos.core.collector.PersistentEventStore
import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent
import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Exercises [PersistentEventStore] against a real Context on a real device — this is the
 * component the First Validation Loop's "events survive app restart" step (§38 Phase 1B) depends
 * on, so its round-trip behavior is verified with real SharedPreferences rather than Robolectric.
 *
 * This deliberately does NOT clear the store before/after each test: on a device where the real
 * app is installed and its WorkManager periodic work is genuinely running (as it was throughout
 * Phase 1B's manual verification), this test shares the exact same SharedPreferences file as
 * production data. Wiping it would destroy real collected events. Assertions therefore check
 * "our test event is present" rather than "the store contains exactly N events" — the store is
 * additive, not test-isolated, which is an accepted property of this Phase 1B-only component
 * (superseded by an isolated Room test database in Phase 2).
 */
@RunWith(AndroidJUnit4::class)
class PersistentEventStoreInstrumentedTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun uniqueId(prefix: String) = "$prefix-${UUID.randomUUID()}"

    private fun sampleEvent(id: String, ts: Long) = TimeOSEvent(
        eventId = id,
        deviceId = "device-1",
        seq = 0,
        tsUtcMillis = ts,
        tzOffsetMinutes = 0,
        tzId = "UTC",
        clockFlags = emptyList(),
        uptimeMillis = ts,
        type = EventType.APP_FOREGROUND,
        source = "android",
        payload = mapOf("package" to "com.example.app"),
        schemaVersion = 1,
    )

    @Test
    fun eventsSurviveARecreatedStoreInstance_simulatingAppRestart() {
        val id = uniqueId("evt")
        val store1 = PersistentEventStore(context)
        val appended = store1.appendIfNew(listOf(sampleEvent(id, System.currentTimeMillis())))
        assertEquals(1, appended)

        // A fresh instance pointed at the same SharedPreferences file simulates the app process
        // being force-stopped and relaunched: the constructor takes no in-memory state.
        val store2 = PersistentEventStore(context)
        assertTrue(store2.contains(id))
        assertTrue(store2.getRecent(5000).any { it.eventId == id })
    }

    @Test
    fun appendIfNew_dedupesByEventId() {
        val id = uniqueId("evt-dup")
        val store = PersistentEventStore(context)
        val first = store.appendIfNew(listOf(sampleEvent(id, System.currentTimeMillis())))
        val second = store.appendIfNew(listOf(sampleEvent(id, System.currentTimeMillis())))
        assertEquals(1, first)
        assertEquals(0, second)
    }

    @Test
    fun cursorAndSeqPersistAcrossInstances() {
        val store1 = PersistentEventStore(context)
        val marker = System.currentTimeMillis()
        store1.setCursor(marker)
        val seq0 = store1.nextSeq()
        val seq1 = store1.nextSeq()

        val store2 = PersistentEventStore(context)
        assertEquals(marker, store2.getCursor())
        assertEquals(seq0 + 1, seq1)
        assertEquals(seq1 + 1, store2.nextSeq())
    }
}
