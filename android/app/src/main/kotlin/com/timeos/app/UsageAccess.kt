package com.timeos.app

import android.app.AppOpsManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Process
import android.provider.Settings

/**
 * Detects and requests the PACKAGE_USAGE_STATS special permission.
 *
 * This permission cannot be requested via a runtime dialog (ActivityCompat.requestPermissions
 * has no effect on it) and Android delivers NO callback when the user revokes it later. Callers
 * must re-check [isGranted] on every onResume — see docs/TIMEOS_ENGINEERING_SPEC.md §8.2.
 */
object UsageAccess {

    /**
     * True if this app currently has Usage Access. Uses AppOpsManager rather than
     * checkSelfPermission because PACKAGE_USAGE_STATS is an appop-backed special permission,
     * not a normal or dangerous one — checkSelfPermission always returns DENIED for it even
     * when Settings shows it as granted.
     */
    @Suppress("DEPRECATION") // unsafeCheckOpNoThrow is deprecated in favor of an API-23+ overload
    // that takes the same arguments in a different order; this is still the correct, standard
    // way to check an appop-backed permission without recording an access note (§8.2).
    fun isGranted(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.unsafeCheckOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    /**
     * Opens the OS Usage Access settings screen so the user can grant this app the permission.
     *
     * One UI (the target device, Samsung Galaxy S24 FE) presents this at
     * Settings > Security and privacy > More privacy settings > Usage data access, as a LIST
     * of apps rather than a per-app toggle — the generic intent below lands on that list, not
     * directly on TimeOS's row, which is why the UI must tell the user to find TimeOS in it
     * (see strings.xml find_in_list_hint).
     *
     * Returns false if no activity could handle the intent at all (rare, OEM-dependent), so the
     * caller can fall back to manual instructions instead of crashing.
     */
    fun openSettings(context: Context): Boolean {
        return try {
            val intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).apply {
                // Some OEM builds honor a direct-to-app-details deep link via this extra data
                // URI; when they don't, it degrades gracefully to the generic list.
                data = Uri.parse("package:${context.packageName}")
            }
            context.startActivity(intent)
            true
        } catch (e: ActivityNotFoundException) {
            try {
                context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                true
            } catch (e2: ActivityNotFoundException) {
                false
            }
        }
    }
}
