package com.timeos.app

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.Configuration
import androidx.work.WorkInfo
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Verifies the boot-recovery re-enqueue path (§38 Phase 1B: "BootReceiver ... re-enqueues work").
 */
@RunWith(AndroidJUnit4::class)
class BootReceiverInstrumentedTest {

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val config = Configuration.Builder()
            .setExecutor(SynchronousExecutor())
            .build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
    }

    @Test
    fun onBootCompleted_enqueuesPeriodicCollectionWork() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        BootReceiver().onReceive(context, Intent(Intent.ACTION_BOOT_COMPLETED))

        val workInfos = androidx.work.WorkManager.getInstance(context)
            .getWorkInfosForUniqueWork("timeos-usage-collection-periodic")
            .get()

        assertTrue(workInfos.isNotEmpty())
        assertTrue(workInfos.any { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.RUNNING })
    }

    @Test
    fun irrelevantIntent_doesNotEnqueueWork() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        BootReceiver().onReceive(context, Intent("some.other.action"))

        val workInfos = androidx.work.WorkManager.getInstance(context)
            .getWorkInfosForUniqueWork("timeos-usage-collection-periodic")
            .get()

        assertTrue(workInfos.isEmpty())
    }
}
