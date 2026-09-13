package com.timeos.core.collector

import com.timeos.core.model.EventType
import com.timeos.core.model.RawUsageEvent
import com.timeos.core.model.TimeOSEvent
import java.util.TimeZone
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Simulates the real UsageStatsManager: returns whatever known events fall in the queried window. */
private class FakeUsageEventSource : UsageEventSource {
    private val allEvents = mutableListOf<RawUsageEvent>()

    fun seed(vararg events: RawUsageEvent) {
        allEvents.addAll(events)
    }

    override fun queryRawEvents(fromMillis: Long, toMillis: Long): List<RawUsageEvent> =
        allEvents.filter { it.timeStampMillis in fromMillis..toMillis }
}

private class FakeTimeSource(private val wallClock: Long, private val elapsedRealtime: Long) : TimeSource {
    override fun wallClockMillis(): Long = wallClock
    override fun elapsedRealtimeMillis(): Long = elapsedRealtime
}

/** In-memory [EventStore] test double — the production store is
 * [com.timeos.core.db.RoomEventStore] as of Phase 2. */
private class InMemoryEventStore : EventStore {
    private val events = LinkedHashMap<String, TimeOSEvent>()
    private var cursor: Long? = null
    private var seqCounter = 0L
    private val pollTimestamps = mutableListOf<Long>()
    private var lastPollAt: Long? = null
    private var lastPermissionLostAt: Long? = null

    override suspend fun contains(eventId: String) = events.containsKey(eventId)

    override suspend fun appendIfNew(events: List<TimeOSEvent>): Int {
        var appended = 0
        for (e in events) {
            if (this.events.putIfAbsent(e.eventId, e) == null) appended++
        }
        return appended
    }

    override suspend fun getRecent(limit: Int): List<TimeOSEvent> =
        events.values.sortedByDescending { it.tsUtcMillis }.take(limit)

    override suspend fun getCursor(): Long? = cursor
    override suspend fun setCursor(tsUtcMillis: Long) { cursor = tsUtcMillis }
    override suspend fun nextSeq(): Long = seqCounter++
    override suspend fun recordPoll(atMillis: Long, appendedCount: Int) {
        lastPollAt = atMillis
        pollTimestamps.add(atMillis)
    }

    override suspend fun recordPermissionLost(atMillis: Long) {
        lastPermissionLostAt = atMillis
    }

    override suspend fun health() =
        CollectionHealth(lastPollAt, pollTimestamps.toList(), events.size, lastPermissionLostAt)
}

class CollectionRunnerTest {

    private val tz: TimeZone = TimeZone.getTimeZone("UTC")

    @Test
    fun `first run seeds from the initial lookback window and appends mapped events`() = runTest {
        val source = FakeUsageEventSource()
        val now = 10_000_000L
        val eventTs = now - 1_000_000L // well within the 24h lookback default
        source.seed(RawUsageEvent("com.a", eventTs, EventType.APP_FOREGROUND))

        val store = InMemoryEventStore()
        val runner = CollectionRunner(
            source = source,
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { true },
            timeSource = FakeTimeSource(now, 1_000_000L),
            timeZoneProvider = { tz },
        )

        val result = runner.runOnce() as CollectionRunResult.Success
        assertEquals(1, result.appended)
        assertEquals(eventTs, store.getCursor())
        assertEquals(1, store.getRecent(10).size)
    }

    @Test
    fun `re-querying an overlapping window does not duplicate events`() = runTest {
        val source = FakeUsageEventSource()
        val store = InMemoryEventStore()
        val eventTs = 1_000_000L
        source.seed(RawUsageEvent("com.a", eventTs, EventType.APP_FOREGROUND))

        val first = CollectionRunner(
            source = source,
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { true },
            timeSource = FakeTimeSource(1_100_000L, 1_000_000L),
            timeZoneProvider = { tz },
        ).runOnce() as CollectionRunResult.Success
        assertEquals(1, first.appended)

        // Second run's window overlaps the first (cursor - 5min back), re-querying the same
        // underlying OS event -- must be deduped, not appended again.
        val second = CollectionRunner(
            source = source,
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { true },
            timeSource = FakeTimeSource(1_200_000L, 1_100_000L),
            timeZoneProvider = { tz },
        ).runOnce() as CollectionRunResult.Success
        assertEquals(0, second.appended)
        assertEquals(1, store.getRecent(10).size)
    }

    @Test
    fun `permission denied records permission lost and does not query the source`() = runTest {
        var queried = false
        val source = object : UsageEventSource {
            override fun queryRawEvents(fromMillis: Long, toMillis: Long): List<RawUsageEvent> {
                queried = true
                return emptyList()
            }
        }
        val store = InMemoryEventStore()
        val runner = CollectionRunner(
            source = source,
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { false },
            timeSource = FakeTimeSource(1_000_000L, 1_000_000L),
            timeZoneProvider = { tz },
        )

        val result = runner.runOnce()
        assertTrue(result is CollectionRunResult.PermissionDenied)
        assertTrue(!queried)
        assertEquals(1_000_000L, store.health().lastPermissionLostAtMillis)
    }

    @Test
    fun `cursor never moves backward across runs`() = runTest {
        val source = FakeUsageEventSource()
        val store = InMemoryEventStore()
        source.seed(RawUsageEvent("com.a", 2_000_000L, EventType.APP_FOREGROUND))

        CollectionRunner(
            source = source,
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { true },
            timeSource = FakeTimeSource(2_100_000L, 2_000_000L),
            timeZoneProvider = { tz },
        ).runOnce()
        assertEquals(2_000_000L, store.getCursor())

        // A later run whose window happens to return nothing new must not reset the cursor.
        CollectionRunner(
            source = FakeUsageEventSource(),
            store = store,
            deviceId = "device-1",
            isUsageAccessGranted = { true },
            timeSource = FakeTimeSource(2_200_000L, 2_100_000L),
            timeZoneProvider = { tz },
        ).runOnce()
        assertEquals(2_000_000L, store.getCursor())
    }
}
