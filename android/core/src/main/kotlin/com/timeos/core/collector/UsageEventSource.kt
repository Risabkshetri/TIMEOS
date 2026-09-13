package com.timeos.core.collector

import com.timeos.core.model.RawUsageEvent

/** Abstraction over the OS usage-events query, so [CollectionRunner] is testable without Android. */
interface UsageEventSource {
    fun queryRawEvents(fromMillis: Long, toMillis: Long): List<RawUsageEvent>
}
