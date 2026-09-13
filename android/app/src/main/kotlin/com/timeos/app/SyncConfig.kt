package com.timeos.app

import android.content.Context

/**
 * The ingest server base URL, e.g. "https://timeos.example.com" in production or
 * "http://127.0.0.1:8089" (via `adb reverse`) against the Phase 2 local mock server
 * (tools/mock_ingest_server.py) during development. Plain SharedPreferences is fine here — a
 * server URL is not a secret, unlike DeviceToken.
 *
 * Deliberately empty by default: with no base URL configured, SyncRunner has nowhere to send
 * batches, which is the correct default until a real backend exists (Phase 3) or a developer
 * points it at a local mock server for testing.
 */
object SyncConfig {
    private const val PREFS_FILE = "timeos_sync_config"
    private const val KEY_BASE_URL = "base_url"

    fun getBaseUrl(context: Context): String? =
        context.getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE).getString(KEY_BASE_URL, null)

    fun setBaseUrl(context: Context, url: String) {
        context.getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE)
            .edit().putString(KEY_BASE_URL, url).apply()
    }
}
