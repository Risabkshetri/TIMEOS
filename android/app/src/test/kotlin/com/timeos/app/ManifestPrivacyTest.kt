package com.timeos.app

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

/**
 * Build-failing enforcement of docs/TIMEOS_ENGINEERING_SPEC.md §35: the manifest must never
 * declare anything that could expose contacts, SMS, phone/hardware identifiers, notification
 * content, or accessibility-service content. INTERNET was forbidden through Phase 1A/1B (its
 * absence was proof nothing left the device); Phase 2's sync client legitimately needs it, so it
 * moved out of the forbidden set here rather than being removed from testing altogether — see
 * `manifest declares INTERNET starting Phase 2` below and the AndroidManifest.xml doc comment.
 *
 * This is the Android-source mirror of backend/tests/test_privacy_isolation.py — a structural
 * check that fails the build the moment a forbidden permission is added, rather than relying on
 * anyone remembering to review the manifest by hand.
 */
class ManifestPrivacyTest {

    private val forbiddenPermissions = setOf(
        "android.permission.READ_CONTACTS",
        "android.permission.WRITE_CONTACTS",
        "android.permission.READ_SMS",
        "android.permission.RECEIVE_SMS",
        "android.permission.SEND_SMS",
        "android.permission.READ_PHONE_STATE",
        "android.permission.READ_PHONE_NUMBERS",
        "android.permission.READ_PRIVILEGED_PHONE_STATE",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
        "android.permission.READ_CALL_LOG",
        "android.permission.PROCESS_OUTGOING_CALLS",
    )

    private val forbiddenServiceBindings = setOf(
        "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
        "android.permission.BIND_ACCESSIBILITY_SERVICE",
    )

    private fun loadManifest(): Element {
        val manifestFile = File("src/main/AndroidManifest.xml")
        require(manifestFile.exists()) { "AndroidManifest.xml not found at ${manifestFile.absolutePath}" }
        val factory = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val doc = factory.newDocumentBuilder().parse(manifestFile)
        return doc.documentElement
    }

    private fun declaredPermissions(root: Element): Set<String> {
        val nodes = root.getElementsByTagName("uses-permission")
        return buildSet {
            for (i in 0 until nodes.length) {
                val el = nodes.item(i) as Element
                el.getAttributeNS("http://schemas.android.com/apk/res/android", "name")
                    .takeIf { it.isNotEmpty() }
                    ?.let { add(it) }
            }
        }
    }

    @Test
    fun `manifest declares no forbidden permission`() {
        val declared = declaredPermissions(loadManifest())
        val violations = declared.intersect(forbiddenPermissions)
        assertTrue(
            "AndroidManifest.xml declares forbidden permission(s): $violations. " +
                "Phase 1A/1B must never request these — see spec §8.2, §35.",
            violations.isEmpty(),
        )
    }

    @Test
    fun `manifest declares no forbidden service binding`() {
        val declared = declaredPermissions(loadManifest())
        val violations = declared.intersect(forbiddenServiceBindings)
        assertTrue(
            "AndroidManifest.xml declares forbidden service binding(s): $violations. " +
                "Notification listener and accessibility service are prohibited (§8.6, §35).",
            violations.isEmpty(),
        )
    }

    @Test
    fun `manifest declares PACKAGE_USAGE_STATS`() {
        val declared = declaredPermissions(loadManifest())
        assertTrue(
            "AndroidManifest.xml must declare PACKAGE_USAGE_STATS so the OS lists this app " +
                "under Settings > Usage Access.",
            declared.contains("android.permission.PACKAGE_USAGE_STATS"),
        )
    }

    @Test
    fun `manifest declares INTERNET starting Phase 2`() {
        val declared = declaredPermissions(loadManifest())
        assertTrue(
            "Phase 2's sync client needs INTERNET to upload batches (§26); its absence would " +
                "mean sync is silently non-functional.",
            declared.contains("android.permission.INTERNET"),
        )
    }
}
