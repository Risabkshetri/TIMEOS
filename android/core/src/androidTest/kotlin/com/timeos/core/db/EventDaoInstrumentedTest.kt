package com.timeos.core.db

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real-Room instrumented tests for the Phase 2 schema (docs/.../§38 Phase 2: "Room migration
 * tests" — since v1 is the baseline with no prior version, this validates the baseline schema's
 * actual behavior on-device rather than a version-to-version migration).
 */
@RunWith(AndroidJUnit4::class)
class EventDaoInstrumentedTest {

    private lateinit var db: TimeOSDatabase

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        db = Room.inMemoryDatabaseBuilder(context, TimeOSDatabase::class.java).build()
    }

    @After
    fun tearDown() {
        db.close()
    }

    private fun entity(seq: Long, id: String = "id-$seq") = EventEntity(
        id = id,
        deviceId = "device-1",
        seq = seq,
        tsUtcMillis = seq * 1000,
        tzOffsetMinutes = 330,
        tzId = "Asia/Kolkata",
        clockFlags = listOf("NTP_SYNCED"),
        uptimeMillis = seq * 1000,
        type = "APP_FOREGROUND",
        source = "android",
        payload = mapOf("package" to "com.example.app"),
        schemaVersion = 1,
    )

    @Test
    fun insertAndReadBack_roundTripsAllFields() = kotlinx.coroutines.runBlocking {
        val original = entity(1)
        db.eventDao().insertAll(listOf(original))

        val recent = db.eventDao().getRecent(10)
        assertEquals(1, recent.size)
        assertEquals(original, recent[0])
    }

    @Test
    fun insertAll_conflictIsIgnoredAndReportedAsMinusOne() = kotlinx.coroutines.runBlocking {
        val first = db.eventDao().insertAll(listOf(entity(1)))
        assertTrue(first[0] != -1L)

        val second = db.eventDao().insertAll(listOf(entity(1))) // same id, duplicate
        assertEquals(-1L, second[0])

        assertEquals(1, db.eventDao().countAll())
    }

    @Test
    fun getUnbatchedOrderedBySeq_excludesSyncedAndBatchedEvents() = kotlinx.coroutines.runBlocking {
        db.eventDao().insertAll(listOf(entity(1), entity(2), entity(3)))
        db.eventDao().assignBatch(listOf("id-2"), "batch-x")

        val unbatched = db.eventDao().getUnbatchedOrderedBySeq(10)
        assertEquals(listOf("id-1", "id-3"), unbatched.map { it.id })
    }

    @Test
    fun markBatchSynced_marksOnlyThatBatchsEvents() = kotlinx.coroutines.runBlocking {
        db.eventDao().insertAll(listOf(entity(1), entity(2)))
        db.eventDao().assignBatch(listOf("id-1"), "batch-a")

        db.eventDao().markBatchSynced("batch-a", 5000L)

        val all = db.eventDao().getRecent(10).associateBy { it.id }
        assertTrue(all["id-1"]!!.synced)
        assertEquals(5000L, all["id-1"]!!.syncedAtMillis)
        assertTrue(!all["id-2"]!!.synced)
    }

    @Test
    fun pruneSyncedOlderThan_neverDeletesUnsyncedRows() = kotlinx.coroutines.runBlocking {
        db.eventDao().insertAll(listOf(entity(1), entity(2)))
        db.eventDao().assignBatch(listOf("id-1"), "batch-a")
        db.eventDao().markBatchSynced("batch-a", 1000L)

        val deleted = db.eventDao().pruneSyncedOlderThan(5000L)
        assertEquals(1, deleted)
        assertEquals(1, db.eventDao().countAll())
        assertEquals("id-2", db.eventDao().getRecent(10)[0].id) // the unsynced one survives
    }

    @Test
    fun clearBatch_releasesEventsBackToTheUnbatchedPool() = kotlinx.coroutines.runBlocking {
        db.eventDao().insertAll(listOf(entity(1)))
        db.eventDao().assignBatch(listOf("id-1"), "batch-a")
        assertTrue(db.eventDao().getUnbatchedOrderedBySeq(10).isEmpty())

        db.eventDao().clearBatch("batch-a")
        assertEquals(1, db.eventDao().getUnbatchedOrderedBySeq(10).size)
    }

    @Test
    fun syncMeta_cursorAndSeqPersist() = kotlinx.coroutines.runBlocking {
        assertNull(db.syncMetaDao().get())

        db.syncMetaDao().upsert(SyncMetaEntity(cursorTsUtcMillis = 42L, nextSeq = 7L))
        val meta = db.syncMetaDao().get()!!
        assertEquals(42L, meta.cursorTsUtcMillis)
        assertEquals(7L, meta.nextSeq)

        // upsert replaces the singleton row rather than duplicating it.
        db.syncMetaDao().upsert(meta.copy(nextSeq = 8L))
        assertEquals(8L, db.syncMetaDao().get()!!.nextSeq)
    }

    @Test
    fun syncBatch_oldestPendingRespectsSeqOrderAndExcludesQuarantined() = kotlinx.coroutines.runBlocking {
        db.syncBatchDao().insert(
            SyncBatchEntity("b2", 200, seqFrom = 20, seqTo = 20, eventCount = 1, status = SyncBatchStatus.PENDING),
        )
        db.syncBatchDao().insert(
            SyncBatchEntity("b1", 100, seqFrom = 10, seqTo = 10, eventCount = 1, status = SyncBatchStatus.PENDING),
        )
        db.syncBatchDao().insert(
            SyncBatchEntity("b0", 50, seqFrom = 5, seqTo = 5, eventCount = 1, status = SyncBatchStatus.QUARANTINED),
        )

        val oldest = db.syncBatchDao().oldestPending()
        assertEquals("b1", oldest?.batchId) // lowest seqFrom among PENDING, quarantined excluded
    }
}
