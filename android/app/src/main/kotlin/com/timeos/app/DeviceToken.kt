package com.timeos.app

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Client-side storage for the device's ingest auth token, Keystore-backed per
 * docs/TIMEOS_ENGINEERING_SPEC.md §28 (the token is the one Phase 2 secret that genuinely
 * requires encryption, unlike the device id).
 *
 * Real enrollment (POST /v1/devices/enroll, §12.2/§38 Phase 3) doesn't exist yet — that's Phase
 * 3's backend work. For Phase 2's client-side sync testing, this exposes a settable dev token
 * (entered on the diagnostic screen against a local mock server) rather than a real enrollment
 * flow.
 */
object DeviceToken {
    private const val PREFS_FILE = "timeos_device_token"
    private const val KEY_TOKEN = "token"
    private const val TAG = "TimeOS/DeviceToken"

    fun get(context: Context): String? = prefs(context).getString(KEY_TOKEN, null)

    fun set(context: Context, token: String) {
        prefs(context).edit().putString(KEY_TOKEN, token).apply()
    }

    private fun prefs(context: Context): SharedPreferences = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        Log.w(TAG, "EncryptedSharedPreferences unavailable, falling back to plain prefs", e)
        context.getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE)
    }
}
