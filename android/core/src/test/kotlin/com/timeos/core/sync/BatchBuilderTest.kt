package com.timeos.core.sync

import com.timeos.core.model.EventType
import com.timeos.core.model.TimeOSEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BatchBuilderTest {

    private fun event(seq: Long) = TimeOSEvent(
        eventId = "id-$seq",
        deviceId = "device-1",
        seq = seq,
        tsUtcMillis = seq * 1000,
        tzOffsetMinutes = 0,
        tzId = "UTC",
        clockFlags = emptyList(),
        uptimeMillis = seq * 1000,
        type = EventType.APP_FOREGROUND,
        source = "android",
        payload = mapOf("package" to "com.example"),
        schemaVersion = 1,
    )

    @Test
    fun `empty input produces no batches`() {
        val batches = BatchBuilder.buildBatches(emptyList(), "device-1", { "batch" }, { 0L })
        assertTrue(batches.isEmpty())
    }

    @Test
    fun `events under the count cap form a single batch preserving order`() {
        val events = (1L..10L).map { event(it) }
        val batches = BatchBuilder.buildBatches(events, "device-1", { "batch-1" }) { 100L }
        assertEquals(1, batches.size)
        assertEquals(1L, batches[0].seqFrom)
        assertEquals(10L, batches[0].seqTo)
        assertEquals(10, batches[0].events.size)
        assertEquals("id-1", batches[0].events.first().eventId)
        assertEquals("id-10", batches[0].events.last().eventId)
    }

    @Test
    fun `exactly 1000 events forms one batch, 1001 forms two`() {
        val exactCap = (1..BatchBuilder.MAX_EVENTS_PER_BATCH.toLong()).map { event(it) }
        val oneBatch = BatchBuilder.buildBatches(exactCap, "d", batchIdGenerator()) { 100L }
        assertEquals(1, oneBatch.size)

        val overCap = (1..(BatchBuilder.MAX_EVENTS_PER_BATCH + 1).toLong()).map { event(it) }
        val twoBatches = BatchBuilder.buildBatches(overCap, "d", batchIdGenerator()) { 100L }
        assertEquals(2, twoBatches.size)
        assertEquals(BatchBuilder.MAX_EVENTS_PER_BATCH, twoBatches[0].events.size)
        assertEquals(1, twoBatches[1].events.size)
    }

    @Test
    fun `a batch estimated over the gzip cap is split smaller`() {
        val events = (1L..100L).map { event(it) }
        // Simulate: any chunk of more than 10 events "compresses" to over the 1MB cap.
        val estimate: (List<TimeOSEvent>) -> Long = { chunk ->
            if (chunk.size > 10) BatchBuilder.MAX_GZIP_BYTES + 1 else 500L
        }
        val batches = BatchBuilder.buildBatches(events, "d", batchIdGenerator(), estimate)
        assertTrue(batches.all { it.events.size <= 10 })
        // No events lost or reordered across the split.
        val allIds = batches.flatMap { it.events.map { e -> e.eventId } }
        assertEquals(events.map { it.eventId }, allIds)
    }

    @Test
    fun `seqFrom and seqTo reflect the actual chunk boundaries`() {
        val events = (1L..5L).map { event(it) }
        val estimate: (List<TimeOSEvent>) -> Long = { chunk -> if (chunk.size > 2) BatchBuilder.MAX_GZIP_BYTES + 1 else 0L }
        val batches = BatchBuilder.buildBatches(events, "d", batchIdGenerator(), estimate)
        assertTrue(batches.size >= 2)
        for (b in batches) {
            assertEquals(b.events.first().seq, b.seqFrom)
            assertEquals(b.events.last().seq, b.seqTo)
        }
    }

    private fun batchIdGenerator(): () -> String {
        var n = 0
        return { "batch-${n++}" }
    }
}
