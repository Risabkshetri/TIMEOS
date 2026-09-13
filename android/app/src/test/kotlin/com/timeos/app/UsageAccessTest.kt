package com.timeos.app

import android.app.AppOpsManager
import android.content.Context
import android.os.Process
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

// Robolectric 4.14's newest supported simulated platform is API 35; the app's real targetSdk 36
// (§4.3) is unaffected — this only pins which android-all jar the JVM test runs against.
@Config(sdk = [34])
@RunWith(RobolectricTestRunner::class)
class UsageAccessTest {

    @Test
    fun `isGranted is false when the op is explicitly denied`() {
        // Robolectric's ShadowAppOpsManager defaults an unset op to MODE_ALLOWED, which is the
        // opposite of the real OS default for PACKAGE_USAGE_STATS. Set the mode explicitly so
        // this test verifies UsageAccess's own logic rather than the shadow's default.
        val context = ApplicationProvider.getApplicationContext<Context>()
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        shadowOf(appOps).setMode(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
            AppOpsManager.MODE_ERRORED,
        )

        assertFalse(UsageAccess.isGranted(context))
    }

    @Test
    fun `isGranted reflects MODE_ALLOWED from AppOpsManager`() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        shadowOf(appOps).setMode(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
            AppOpsManager.MODE_ALLOWED,
        )

        assertTrue(UsageAccess.isGranted(context))
    }

    @Test
    fun `isGranted reflects revocation back to MODE_ERRORED`() {
        // Simulates the exact scenario the app must handle without any OS callback: the user
        // grants, then revokes, Usage Access from Settings (§8.2).
        val context = ApplicationProvider.getApplicationContext<Context>()
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val shadow = shadowOf(appOps)

        shadow.setMode(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
            AppOpsManager.MODE_ALLOWED,
        )
        assertTrue(UsageAccess.isGranted(context))

        shadow.setMode(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName,
            AppOpsManager.MODE_ERRORED,
        )
        assertFalse(UsageAccess.isGranted(context))
    }
}
