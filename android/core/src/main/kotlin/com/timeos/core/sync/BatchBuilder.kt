package com.timeos.core.sync

import com.timeos.core.model.TimeOSEvent

/**
 * Groups ordered (by seq, ascending) unbatched events into batches per docs/.../§26:
 * "≤1000 events or ≤1MB gzipped, whichever first". Size is checked with an injected estimator
 * (production wiring gzips for real; tests can use a cheap synthetic estimate) so this stays a
 * pure, fast function.
 */
object BatchBuilder {
    const val MAX_EVENTS_PER_BATCH = 1000
    const val MAX_GZIP_BYTES = 1_000_000L

    /**
     * @param events already ordered by seq ascending.
     * @param estimateGzipSize returns the compressed size in bytes of a candidate chunk.
     */
    fun buildBatches(
        events: List<TimeOSEvent>,
        deviceId: String,
        batchIdGenerator: () -> String,
        estimateGzipSize: (List<TimeOSEvent>) -> Long,
    ): List<IngestBatchRequest> {
        if (events.isEmpty()) return emptyList()

        val batches = mutableListOf<IngestBatchRequest>()
        var index = 0
        while (index < events.size) {
            var end = (index + MAX_EVENTS_PER_BATCH).coerceAtMost(events.size)
            while (end > index + 1 && estimateGzipSize(events.subList(index, end)) > MAX_GZIP_BYTES) {
                end = index + (end - index) / 2
            }
            val chunk = events.subList(index, end)
            batches.add(
                IngestBatchRequest(
                    batchId = batchIdGenerator(),
                    deviceId = deviceId,
                    seqFrom = chunk.first().seq,
                    seqTo = chunk.last().seq,
                    events = chunk.map { it.toPayload() },
                ),
            )
            index = end
        }
        return batches
    }
}
