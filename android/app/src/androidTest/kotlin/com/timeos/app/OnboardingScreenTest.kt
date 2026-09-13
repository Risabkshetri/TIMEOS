package com.timeos.app

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Instrumented UI tests for the onboarding states described in
 * docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 1A manual verification:
 *   1. "Usage Access not granted" (initial state)
 *   2. Settings-open failure shows the manual-navigation fallback text
 *   3. The granted state (DiagnosticScreen, Phase 1B) shows the device ID
 *
 * Requires a connected device or emulator to run (./gradlew connectedDebugAndroidTest).
 */
@RunWith(AndroidJUnit4::class)
class OnboardingScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun onboardingScreen_showsGrantButtonAndExplanation() {
        composeTestRule.setContent {
            OnboardingScreen(onGrantClick = {}, settingsOpenFailed = false)
        }

        composeTestRule.onNodeWithText("Open Usage Access Settings").assertExists()
    }

    @Test
    fun onboardingScreen_showsFallbackInstructions_whenSettingsFailToOpen() {
        composeTestRule.setContent {
            OnboardingScreen(onGrantClick = {}, settingsOpenFailed = true)
        }

        composeTestRule
            .onNodeWithText("Couldn't open the settings screen automatically.", substring = true)
            .assertExists()
    }

    @Test
    fun diagnosticScreen_showsDeviceId() {
        composeTestRule.setContent {
            DiagnosticScreen(deviceId = "test-device-id-1234")
        }

        composeTestRule.onNodeWithText("test-device-id-1234", substring = true).assertExists()
    }
}
