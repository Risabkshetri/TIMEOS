package com.timeos.core.collector

import android.os.SystemClock

/** Abstraction over wall-clock and monotonic time, so [CollectionRunner] is testable without Android. */
interface TimeSource {
    fun wallClockMillis(): Long
    fun elapsedRealtimeMillis(): Long
}

class SystemTimeSource : TimeSource {
    override fun wallClockMillis(): Long = System.currentTimeMillis()
    override fun elapsedRealtimeMillis(): Long = SystemClock.elapsedRealtime()
}
