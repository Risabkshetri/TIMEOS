package com.timeos.app

import android.app.Application
import android.util.Log

class TimeOSApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        try {
            CollectionScheduler.ensureScheduled(this)
            SyncScheduler.ensureScheduled(this)
        } catch (e: IllegalStateException) {
            // WorkManager's own ContentProvider auto-initializer normally runs before
            // Application.onCreate(), but some test harnesses (Robolectric) don't guarantee
            // that ordering. Scheduling is retried on the next process start (or boot, or app
            // launch via CollectionScheduler.runCatchUpNow), so this must never crash startup.
            Log.w("TimeOS/App", "WorkManager not yet initialized; will retry on next launch", e)
        }
    }
}
