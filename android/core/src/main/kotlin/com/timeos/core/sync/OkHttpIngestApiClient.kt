package com.timeos.core.sync

import java.io.IOException
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import kotlin.coroutines.resume

/**
 * Real network implementation of [IngestApiClient], targeting docs/.../§12.3's
 * POST /v1/ingest/batch contract. Compresses the body with gzip and sets `Idempotency-Key` to
 * the batch id — the two mechanisms the batch ledger and dedup design depend on client-side.
 *
 * `baseUrl` is passed in rather than hardcoded: production points at the deployed API over TLS
 * (§28: TLS 1.2+ only), while Phase 2 development/testing points at a local mock server — see
 * app/src/main/kotlin/com/timeos/app/SyncConfig.kt and the debug-only network security config
 * that permits cleartext HTTP to that address alone.
 */
class OkHttpIngestApiClient(
    private val baseUrl: String,
    private val deviceToken: () -> String,
    private val client: OkHttpClient = OkHttpClient(),
) : IngestApiClient {

    override suspend fun postBatch(request: IngestBatchRequest): IngestOutcome {
        val json = IngestJson.serialize(request)
        val compressed = try {
            GzipUtil.gzip(json.toByteArray(Charsets.UTF_8))
        } catch (e: IOException) {
            return IngestOutcome.NetworkFailure("gzip failed: ${e.message}")
        }

        val httpRequest = Request.Builder()
            .url("$baseUrl/v1/ingest/batch")
            .header("Authorization", "Bearer ${deviceToken()}")
            .header("Idempotency-Key", request.batchId)
            .header("Content-Encoding", "gzip")
            .post(compressed.toRequestBody("application/json".toMediaType()))
            .build()

        return try {
            executeAsync(httpRequest).use { response -> response.toOutcome() }
        } catch (e: IOException) {
            IngestOutcome.NetworkFailure(e.message ?: e.javaClass.simpleName)
        }
    }

    private suspend fun executeAsync(request: Request): Response =
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(
                object : Callback {
                    override fun onFailure(call: Call, e: IOException) {
                        cont.resumeWith(Result.failure(e))
                    }

                    override fun onResponse(call: Call, response: Response) {
                        cont.resume(response)
                    }
                },
            )
        }

    private fun Response.toOutcome(): IngestOutcome = when {
        code in 200..299 -> IngestOutcome.Success
        code == 429 -> {
            val retryAfter = header("Retry-After")?.toIntOrNull()
            IngestOutcome.RateLimited(retryAfter)
        }
        code in 400..499 -> IngestOutcome.ClientError(code, body?.string()?.take(500))
        code in 500..599 -> IngestOutcome.ServerError(code)
        else -> IngestOutcome.NetworkFailure("unexpected status $code")
    }
}
