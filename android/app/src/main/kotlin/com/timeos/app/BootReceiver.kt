package com.timeos.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Re-schedules collection after a reboot and runs an immediate catch-up drain so the OS's own
 * DEVICE_STARTUP usage event (and anything else queued since shutdown) is picked up promptly
 * rather than waiting up to 15 minutes for the next periodic tick.
 *
 * Belt-and-suspenders: WorkManager persists periodic work across reboots on its own via its
 * internal reschedule receiver, so [CollectionScheduler.ensureScheduled] here is a defensive,
 * idempotent no-op in the common case (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 1B).
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        CollectionScheduler.ensureScheduled(context)
        CollectionScheduler.runCatchUpNow(context)
    }
}
