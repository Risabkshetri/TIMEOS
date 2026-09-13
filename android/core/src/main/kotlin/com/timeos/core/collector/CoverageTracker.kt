package com.timeos.core.collector

import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent

data class LocalSession(
    val packageName: String,
    val startMillis: Long,
    val endMillis: Long,
    val truncated: Boolean,
) {
    val durationMillis: Long get() = endMillis - startMillis
}

/**
 * Builds an approximate local session timeline purely for on-device diagnostic display
 * (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 1B). This is NOT the authoritative sessionizer —
 * that is the deterministic, re-runnable, server-side engine specified in §14 and implemented in
 * Phase 4. This local approximation applies only a lightweight subset of those rules (open/close
 * boundaries, minimum duration, same-app bounce merging, truncation of runaway sessions) so the
 * diagnostic screen can show "you used X for Y minutes" instead of a raw event list.
 */
object CoverageTracker {
    private const val MIN_SESSION_MILLIS = 3_000L
    private const val MERGE_GAP_MILLIS = 30_000L
    private const val MAX_SESSION_MILLIS = 4 * 60 * 60 * 1000L

    fun buildSessions(events: List<TimeOSEvent>, nowMillis: Long): List<LocalSession> {
        val chronological = events.sortedBy { it.tsUtcMillis }
        val sessions = mutableListOf<LocalSession>()

        var openPackage: String? = null
        var openStart = 0L
        // When the open app backgrounds, we don't finalize immediately — it might resume within
        // the merge window (a same-app "bounce"). lastActiveEnd holds the backgrounding
        // timestamp to close at if no resume arrives; pendingBackground distinguishes "currently
        // backgrounded, waiting to see if it resumes" from "still actively foregrounded".
        var lastActiveEnd = 0L
        var pendingBackground = false

        fun close(endMillis: Long) {
            val pkg = openPackage ?: return
            val truncated = endMillis - openStart > MAX_SESSION_MILLIS
            val actualEnd = if (truncated) openStart + MAX_SESSION_MILLIS else endMillis
            if (actualEnd - openStart >= MIN_SESSION_MILLIS) {
                sessions.add(LocalSession(pkg, openStart, actualEnd, truncated))
            }
            openPackage = null
            pendingBackground = false
        }

        for (e in chronological) {
            when (e.type) {
                EventType.APP_FOREGROUND -> {
                    val pkg = e.payload["package"] ?: continue
                    if (openPackage == pkg && pendingBackground && e.tsUtcMillis - lastActiveEnd <= MERGE_GAP_MILLIS) {
                        // Resumed the same app within the merge window: cancel the pending
                        // close and keep the original session open.
                        pendingBackground = false
                    } else {
                        val finalEnd = if (pendingBackground) lastActiveEnd else e.tsUtcMillis
                        close(finalEnd)
                        openPackage = pkg
                        openStart = e.tsUtcMillis
                        pendingBackground = false
                    }
                }

                EventType.APP_BACKGROUND -> {
                    val pkg = e.payload["package"]
                    if (openPackage != null && openPackage == pkg) {
                        lastActiveEnd = e.tsUtcMillis
                        pendingBackground = true
                    }
                }

                EventType.SCREEN_OFF, EventType.DEVICE_LOCK, EventType.DEVICE_SHUTDOWN -> {
                    val finalEnd = if (pendingBackground) lastActiveEnd else e.tsUtcMillis
                    close(finalEnd)
                }

                else -> Unit
            }
        }

        if (openPackage != null) {
            close(if (pendingBackground) lastActiveEnd else nowMillis)
        }

        return sessions.sortedByDescending { it.startMillis }
    }
}
