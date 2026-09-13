package com.timeos.core.sync

/**
 * Outcome of one /v1/ingest/batch attempt, distinguishing the cases §26/§27 require different
 * handling for: only [ClientError] is permanent (quarantine); everything else is retryable.
 */
sealed interface IngestOutcome {
    data object Success : IngestOutcome
    data class ClientError(val code: Int, val body: String?) : IngestOutcome
    data class RateLimited(val retryAfterSeconds: Int?) : IngestOutcome
    data class ServerError(val code: Int) : IngestOutcome
    data class NetworkFailure(val message: String) : IngestOutcome
}

fun interface IngestApiClient {
    suspend fun postBatch(request: IngestBatchRequest): IngestOutcome
}
