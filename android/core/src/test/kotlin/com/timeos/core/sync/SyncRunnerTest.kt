package com.timeos.core.sync

import com.timeos.core.collector.TimeSource
import com.timeos.core.db.EventDao
import com.timeos.core.db.EventEntity
import com.timeos.core.db.SyncBatchDao
import com.timeos.core.db.SyncBatchEntity
import com.timeos.core.db.SyncBatchStatus
import com.timeos.core.db.SyncMetaDao
import com.timeos.core.db.SyncMetaEntity
import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Hand-written fake: Room DAO interfaces are plain Kotlin interfaces, so this needs no
 * Robolectric or real database — see SyncRunner's class doc. */
private class FakeEventDao : EventDao {
    val events = LinkedHashMap<String, EventEntity>()

    override suspend fun insertAll(events: List<EventEntity>): List<Long> =
        events.map { e -> if (this.events.putIfAbsent(e.id, e) == null) 1L else -1L }

    override suspend fun contains(id: String) = events.containsKey(id)

    override suspend fun getRecent(limit: Int) =
        events.values.sortedByDescending { it.seq }.take(limit)

    override suspend fun getUnbatchedOrderedBySeq(limit: Int) =
        events.values.filter { !it.synced && it.batchId == null }.sortedBy { it.seq }.take(limit)

    override suspend fun getByBatchId(batchId: String) =
        events.values.filter { it.batchId == batchId }.sortedBy { it.seq }

    override suspend fun assignBatch(ids: List<String>, batchId: String) {
        ids.forEach { id -> events[id]?.let { events[id] = it.copy(batchId = batchId) } }
    }

    override suspend fun clearBatch(batchId: String) {
        events.values.filter { it.batchId == batchId }.forEach { events[it.id] = it.copy(batchId = null) }
    }

    override suspend fun markBatchSynced(batchId: String, syncedAtMillis: Long) {
        events.values.filter { it.batchId == batchId }.forEach {
            events[it.id] = it.copy(synced = true, syncedAtMillis = syncedAtMillis)
        }
    }

    override suspend fun countAll() = events.size
    override suspend fun countUnsynced() = events.values.count { !it.synced }
    override suspend fun pruneSyncedOlderThan(beforeMillis: Long) = 0
    override suspend fun deleteOldestSynced(count: Int) = 0
}

private class FakeSyncBatchDao : SyncBatchDao {
    val batches = LinkedHashMap<String, SyncBatchEntity>()

    override suspend fun insert(batch: SyncBatchEntity) {
        batches[batch.batchId] = batch
    }

    override suspend fun update(batch: SyncBatchEntity) {
        batches[batch.batchId] = batch
    }

    override suspend fun oldestPending() =
        batches.values.filter { it.status == SyncBatchStatus.PENDING }.minByOrNull { it.seqFrom }

    override suspend fun quarantinedCount() = batches.values.count { it.status == SyncBatchStatus.QUARANTINED }
    override suspend fun pendingCount() = batches.values.count { it.status == SyncBatchStatus.PENDING }
    override suspend fun recent(limit: Int) = batches.values.sortedByDescending { it.createdAtMillis }.take(limit)
    override suspend fun get(batchId: String) = batches[batchId]
}

private class FakeSyncMetaDao : SyncMetaDao {
    var meta: SyncMetaEntity? = null
    override suspend fun get() = meta
    override suspend fun upsert(meta: SyncMetaEntity) { this.meta = meta }
}

private class FixedTimeSource(private val now: Long) : TimeSource {
    override fun wallClockMillis() = now
    override fun elapsedRealtimeMillis() = now
}

private fun entity(seq: Long, id: String = "id-$seq") = EventEntity(
    id = id,
    deviceId = "device-1",
    seq = seq,
    tsUtcMillis = seq * 1000,
    tzOffsetMinutes = 0,
    tzId = "UTC",
    clockFlags = emptyList(),
    uptimeMillis = seq * 1000,
    type = EventType.APP_FOREGROUND.name,
    source = "android",
    payload = mapOf("package" to "com.example"),
    schemaVersion = 1,
)

class SyncRunnerTest {

    private fun runner(
        eventDao: FakeEventDao,
        batchDao: FakeSyncBatchDao,
        apiClient: IngestApiClient,
        now: Long = 1_000_000L,
        batchId: String = "batch-1",
        syncMetaDao: FakeSyncMetaDao = FakeSyncMetaDao(),
    ) = SyncRunner(
        eventDao = eventDao,
        batchDao = batchDao,
        syncMetaDao = syncMetaDao,
        apiClient = apiClient,
        deviceId = "device-1",
        estimateGzipSize = { 100L },
        timeSource = FixedTimeSource(now),
        batchIdGenerator = { batchId },
    )

    @Test
    fun `no unbatched events and no pending batch means nothing to sync`() = runTest {
        val eventDao = FakeEventDao()
        val batchDao = FakeSyncBatchDao()
        val result = runner(eventDao, batchDao, apiClient = { IngestOutcome.Success }).runOnce()
        assertTrue(result is SyncRunResult.NothingToSync)
    }

    @Test
    fun `successful post marks events synced and batch ACKED`() = runTest {
        val eventDao = FakeEventDao().apply {
            events["id-1"] = entity(1)
            events["id-2"] = entity(2)
        }
        val batchDao = FakeSyncBatchDao()
        val syncMetaDao = FakeSyncMetaDao()

        val result = runner(eventDao, batchDao, apiClient = { IngestOutcome.Success }, syncMetaDao = syncMetaDao)
            .runOnce()

        assertTrue(result is SyncRunResult.Synced)
        assertEquals(2, (result as SyncRunResult.Synced).eventCount)
        assertTrue(eventDao.events.values.all { it.synced })
        assertEquals(SyncBatchStatus.ACKED, batchDao.batches.values.single().status)
        assertEquals(1_000_000L, syncMetaDao.meta?.lastSyncAttemptAtMillis)
        assertEquals("SUCCESS", syncMetaDao.meta?.lastSyncResult)
    }

    @Test
    fun `server error retries with backoff and keeps the batch pending`() = runTest {
        val eventDao = FakeEventDao().apply { events["id-1"] = entity(1) }
        val batchDao = FakeSyncBatchDao()

        val result = runner(eventDao, batchDao, apiClient = { IngestOutcome.ServerError(500) }).runOnce()

        assertTrue(result is SyncRunResult.Retrying)
        val batch = batchDao.batches.values.single()
        assertEquals(SyncBatchStatus.PENDING, batch.status)
        assertEquals(1, batch.attemptCount)
        assertTrue(eventDao.events.values.none { it.synced })
    }

    @Test
    fun `client error quarantines the batch and never retries`() = runTest {
        val eventDao = FakeEventDao().apply { events["id-1"] = entity(1) }
        val batchDao = FakeSyncBatchDao()

        val result = runner(eventDao, batchDao, apiClient = { IngestOutcome.ClientError(422, "bad request") }).runOnce()

        assertTrue(result is SyncRunResult.Quarantined)
        assertEquals(SyncBatchStatus.QUARANTINED, batchDao.batches.values.single().status)

        // A quarantined batch must not block a fresh batch from later unbatched events, and must
        // not be re-attempted on the next cycle.
        eventDao.events["id-2"] = entity(2)
        var secondCallCount = 0
        val secondResult = runner(eventDao, batchDao, apiClient = {
            secondCallCount++
            IngestOutcome.Success
        }, now = 2_000_000L, batchId = "batch-2").runOnce()
        assertTrue(secondResult is SyncRunResult.Synced)
        assertEquals(1, secondCallCount)
        assertEquals(listOf("id-2"), (secondResult as SyncRunResult.Synced).let {
            eventDao.getByBatchId(it.batchId).map { e -> e.id }
        })
    }

    @Test
    fun `a pending batch not yet due for retry blocks the api client from being called`() = runTest {
        val eventDao = FakeEventDao().apply { events["id-1"] = entity(1) }
        val batchDao = FakeSyncBatchDao().apply {
            batches["batch-1"] = SyncBatchEntity(
                batchId = "batch-1",
                createdAtMillis = 0,
                seqFrom = 1,
                seqTo = 1,
                eventCount = 1,
                status = SyncBatchStatus.PENDING,
                attemptCount = 1,
                lastAttemptAtMillis = 1_000_000L,
            )
        }
        var called = false
        val result = runner(eventDao, batchDao, apiClient = {
            called = true
            IngestOutcome.Success
        }, now = 1_000_010L).runOnce() // 10ms later, nowhere near the ~30s backoff

        assertTrue(result is SyncRunResult.WaitingForBackoff)
        assertTrue(!called)
    }

    @Test
    fun `an existing pending batch blocks a new batch from being built this cycle`() = runTest {
        val eventDao = FakeEventDao().apply {
            events["id-1"] = entity(1).copy(batchId = "batch-1")
            events["id-2"] = entity(2) // unbatched, would otherwise form a new batch
        }
        val batchDao = FakeSyncBatchDao().apply {
            batches["batch-1"] = SyncBatchEntity(
                batchId = "batch-1", createdAtMillis = 0, seqFrom = 1, seqTo = 1,
                eventCount = 1, status = SyncBatchStatus.PENDING,
            )
        }
        val result = runner(eventDao, batchDao, apiClient = { IngestOutcome.Success }).runOnce()

        assertTrue(result is SyncRunResult.Synced)
        assertEquals("batch-1", (result as SyncRunResult.Synced).batchId)
        // id-2 must still be unbatched -- it was never touched this cycle.
        assertNull(eventDao.events["id-2"]!!.batchId)
    }

    @Test
    fun `network failure is retryable, not quarantined`() = runTest {
        val eventDao = FakeEventDao().apply { events["id-1"] = entity(1) }
        val batchDao = FakeSyncBatchDao()
        val result = runner(
            eventDao,
            batchDao,
            apiClient = { IngestOutcome.NetworkFailure("host unreachable") },
        ).runOnce()

        assertTrue(result is SyncRunResult.Retrying)
        assertEquals(SyncBatchStatus.PENDING, batchDao.batches.values.single().status)
    }
}
