package com.timeos.core.model

/**
 * A minimally-extracted OS usage event, before mapping to the full TimeOS envelope. This is the
 * seam between [com.timeos.core.collector.UsageEventReader] (the one class that touches the real
 * android.app.usage.UsageEvents API, which cannot be constructed with custom field values in a
 * plain unit test) and [com.timeos.core.collector.EventMapper] (pure, fully unit-testable using
 * this type as its fixture).
 */
data class RawUsageEvent(
    val packageName: String,
    val timeStampMillis: Long,
    val eventType: EventType,
)
