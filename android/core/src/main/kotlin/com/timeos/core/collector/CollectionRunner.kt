package com.timeos.core.collector

import com.timeos.core.model.TimeOSEvent
import java.util.TimeZone
import java.util.concurrent.TimeUnit

sealed interface CollectionRunResult {
    data class Success(val queried: Int, val appended: Int) : CollectionRunResult
    data object PermissionDenied : CollectionRunResult
}

/**
 * One collection cycle: query new OS usage events since the last cursor (with a 5-minute overlap
 * to absorb clock jitter, §8.3), deduplicate by deterministic event_id, map to the TimeOS
 * envelope, and append to the store. Pure orchestration with no direct Android framework
 * dependency beyond the [UsageEventSource]/[EventStore]/[TimeSource] abstractions it is given —
 * this is what makes it unit-testable without Robolectric.
 * See docs/TIMEOS_ENGINEERING_SPEC.md §8.3, §8.4, §38 Phase 1B.
 */
class CollectionRunner(
    private val source: UsageEventSource,
    private val store: EventStore,
    private val deviceId: String,
    private val isUsageAccessGranted: () -> Boolean,
    private val timeSource: TimeSource = SystemTimeSource(),
    private val timeZoneProvider: () -> TimeZone = { TimeZone.getDefault() },
    private val initialLookbackMillis: Long = TimeUnit.HOURS.toMillis(24),
    private val overlapMillis: Long = TimeUnit.MINUTES.toMillis(5),
) {
    fun runOnce(): CollectionRunResult {
        val now = timeSource.wallClockMillis()

        if (!isUsageAccessGranted()) {
            store.recordPermissionLost(now)
            return CollectionRunResult.PermissionDenied
        }

        val cursor = store.getCursor()
        val from = if (cursor != null) {
            (cursor - overlapMillis).coerceAtLeast(0)
        } else {
            (now - initialLookbackMillis).coerceAtLeast(0)
        }

        val raw = source.queryRawEvents(from, now)
        val nowElapsed = timeSource.elapsedRealtimeMillis()
        val timeZone = timeZoneProvider()

        val toAppend = mutableListOf<TimeOSEvent>()
        for (r in raw) {
            val eventId = EventMapper.deriveEventId(deviceId, r)
            if (store.contains(eventId)) continue
            val seq = store.nextSeq()
            toAppend.add(
                EventMapper.map(
                    raw = r,
                    deviceId = deviceId,
                    eventId = eventId,
                    seq = seq,
                    nowWallClockMillis = now,
                    nowElapsedRealtimeMillis = nowElapsed,
                    timeZone = timeZone,
                ),
            )
        }

        val appended = store.appendIfNew(toAppend)

        val maxTs = raw.maxOfOrNull { it.timeStampMillis }
        if (maxTs != null) {
            store.setCursor(maxOf(maxTs, cursor ?: 0L))
        }

        store.recordPoll(now, appended)
        return CollectionRunResult.Success(queried = raw.size, appended = appended)
    }
}
