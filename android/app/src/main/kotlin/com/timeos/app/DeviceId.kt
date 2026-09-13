package com.timeos.app

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

/**
 * The TimeOS device identity: a randomly generated UUID, created once on first launch and
 * persisted in Keystore-backed encrypted storage.
 *
 * NEVER derive this from IMEI, serial number, ANDROID_ID, phone number, MAC address, or any
 * other hardware/network identifier — see docs/TIMEOS_ENGINEERING_SPEC.md §8.3, §4.5. Those are
 * explicitly on the "never collected" list; a generated UUID is the only acceptable source.
 */
object DeviceId {
    private const val PREFS_FILE = "timeos_device_identity"
    private const val KEY_DEVICE_ID = "device_id"
    private const val TAG = "TimeOS/DeviceId"

    @Volatile
    private var cached: String? = null

    fun get(context: Context): String {
        cached?.let { return it }
        synchronized(this) {
            cached?.let { return it }
            val prefs = encryptedPrefs(context)
            val existing = prefs.getString(KEY_DEVICE_ID, null)
            val id = existing ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_DEVICE_ID, it).apply()
            }
            cached = id
            return id
        }
    }

    private fun encryptedPrefs(context: Context): SharedPreferences {
        return try {
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
            // Keystore can fail on rare OEM builds. Falling back to plain prefs keeps the app
            // functional; the device ID itself carries no sensitive information (it identifies
            // no person or hardware), only the *sync token* stored later in Phase 2 requires the
            // encrypted store without a fallback.
            Log.w(TAG, "EncryptedSharedPreferences unavailable, falling back to plain prefs", e)
            context.getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE)
        }
    }
}
