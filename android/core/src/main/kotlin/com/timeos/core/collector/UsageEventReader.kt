package com.timeos.core.collector

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import com.timeos.core.model.EventType
import com.timeos.core.model.RawUsageEvent

/**
 * Drains android.app.usage.UsageEvents into our own [RawUsageEvent] type, filtering to the
 * event-type allowlist in docs/TIMEOS_ENGINEERING_SPEC.md §8.1 — everything else (app updates,
 * configuration changes, etc.) is discarded at this layer and never becomes a TimeOS event.
 *
 * This is the one class in the collector that touches the real platform API; its correctness is
 * validated primarily by manual verification on a physical device (§38 Phase 1B, First
 * Validation Loop steps 3-4), since android.app.usage.UsageEvents.Event cannot be constructed
 * with custom field values in a plain unit test.
 */
class UsageEventReader(context: Context) : UsageEventSource {
    private val usageStatsManager =
        context.applicationContext.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager

    override fun queryRawEvents(fromMillis: Long, toMillis: Long): List<RawUsageEvent> {
        if (toMillis <= fromMillis) return emptyList()

        val usageEvents = usageStatsManager.queryEvents(fromMillis, toMillis)
        val result = mutableListOf<RawUsageEvent>()
        // A single Event instance is reused across getNextEvent() calls by design (it's an
        // out-parameter) — fields are copied into our own RawUsageEvent immediately, before the
        // next iteration overwrites them.
        val event = UsageEvents.Event()
        while (usageEvents.hasNextEvent()) {
            usageEvents.getNextEvent(event)
            val mappedType = mapEventType(event.eventType) ?: continue
            val packageName = event.packageName ?: continue
            result.add(RawUsageEvent(packageName, event.timeStamp, mappedType))
        }
        return result
    }

    private fun mapEventType(osEventType: Int): EventType? = when (osEventType) {
        UsageEvents.Event.ACTIVITY_RESUMED -> EventType.APP_FOREGROUND
        UsageEvents.Event.ACTIVITY_PAUSED -> EventType.APP_BACKGROUND
        UsageEvents.Event.ACTIVITY_STOPPED -> EventType.APP_BACKGROUND
        UsageEvents.Event.SCREEN_INTERACTIVE -> EventType.SCREEN_ON
        UsageEvents.Event.SCREEN_NON_INTERACTIVE -> EventType.SCREEN_OFF
        UsageEvents.Event.KEYGUARD_SHOWN -> EventType.DEVICE_LOCK
        UsageEvents.Event.KEYGUARD_HIDDEN -> EventType.DEVICE_UNLOCK
        UsageEvents.Event.DEVICE_SHUTDOWN -> EventType.DEVICE_SHUTDOWN
        UsageEvents.Event.DEVICE_STARTUP -> EventType.DEVICE_STARTUP
        UsageEvents.Event.USER_INTERACTION -> EventType.USER_INTERACTION
        else -> null
    }
}
