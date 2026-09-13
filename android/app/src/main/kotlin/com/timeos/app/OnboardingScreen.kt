package com.timeos.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

/**
 * Explains why Usage Access is needed and provides the button that opens the OS settings
 * screen for it. Shown whenever [UsageAccess.isGranted] is false — including immediately after
 * a revocation the app detects on resume.
 *
 * See docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 1A: this screen, and the permission-state
 * detection it drives, must exist and work BEFORE any usage-stats collection code runs.
 */
@Composable
fun OnboardingScreen(onGrantClick: () -> Unit, settingsOpenFailed: Boolean) {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.Start,
        ) {
            Text(
                text = stringResource(R.string.onboarding_title),
                style = MaterialTheme.typography.headlineSmall,
            )

            Column(modifier = Modifier.padding(top = 16.dp)) {
                Text(
                    text = stringResource(R.string.onboarding_body),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }

            Button(
                onClick = onGrantClick,
                modifier = Modifier.padding(top = 24.dp),
            ) {
                Text(stringResource(R.string.grant_button))
            }

            Text(
                text = stringResource(R.string.find_in_list_hint),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 8.dp),
            )

            if (settingsOpenFailed) {
                Text(
                    text = stringResource(R.string.settings_open_failed),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 16.dp),
                )
            }
        }
    }
}
