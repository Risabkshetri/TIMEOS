package com.timeos.core.sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BackoffPolicyTest {

    private fun noJitter() = 0.5 // maps to zero jitter: (0.5*2-1)=0

    @Test
    fun `schedule follows 30s, 1m, 5m, 15m, 1h with no jitter`() {
        assertEquals(30_000L, BackoffPolicy.delayMillis(0, ::noJitter))
        assertEquals(60_000L, BackoffPolicy.delayMillis(1, ::noJitter))
        assertEquals(300_000L, BackoffPolicy.delayMillis(2, ::noJitter))
        assertEquals(900_000L, BackoffPolicy.delayMillis(3, ::noJitter))
        assertEquals(3_600_000L, BackoffPolicy.delayMillis(4, ::noJitter))
    }

    @Test
    fun `delay is capped at the last step for attempts beyond the schedule`() {
        assertEquals(3_600_000L, BackoffPolicy.delayMillis(10, ::noJitter))
        assertEquals(3_600_000L, BackoffPolicy.delayMillis(100, ::noJitter))
    }

    @Test
    fun `jitter stays within plus-or-minus 20 percent of the base step`() {
        val base = 60_000L // attempt=1
        val maxDelay = BackoffPolicy.delayMillis(1) { 1.0 } // +100% of range -> +20% of base
        val minDelay = BackoffPolicy.delayMillis(1) { 0.0 } // -100% of range -> -20% of base
        assertTrue(maxDelay <= (base * 1.2).toLong())
        assertTrue(minDelay >= (base * 0.8).toLong())
    }

    @Test
    fun `negative attempt index is clamped to the first step`() {
        assertEquals(30_000L, BackoffPolicy.delayMillis(-1, ::noJitter))
    }
}
