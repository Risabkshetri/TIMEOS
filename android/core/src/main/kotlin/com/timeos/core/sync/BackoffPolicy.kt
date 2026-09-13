package com.timeos.core.sync

/**
 * Retry backoff schedule from docs/TIMEOS_ENGINEERING_SPEC.md §26:
 * "exponential backoff 30 s → 1 m → 5 m → 15 m → 1 h, capped, with ±20% jitter."
 */
object BackoffPolicy {
    private val stepsMillis = listOf(30_000L, 60_000L, 300_000L, 900_000L, 3_600_000L)

    /**
     * @param attempt 0-indexed: 0 is the delay before the *first* retry (after the initial
     *   attempt fails), 1 before the second retry, and so on, capped at the last step.
     * @param randomSource injectable for deterministic tests; defaults to real randomness.
     */
    fun delayMillis(attempt: Int, randomSource: () -> Double = Math::random): Long {
        val base = stepsMillis[attempt.coerceIn(0, stepsMillis.lastIndex)]
        val jitterRange = base * 0.2
        val jitter = (randomSource() * 2 - 1) * jitterRange // uniform in [-20%, +20%]
        return (base + jitter).toLong().coerceAtLeast(0)
    }
}
