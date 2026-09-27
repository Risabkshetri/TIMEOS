/**
 * Persistent extension configuration — `storage.local` via `webextension-polyfill`, which unlike
 * IndexedDB (used only for the event buffer, `store.ts`) is a natural fit for small,
 * individually-addressed scalars. Survives a service-worker eviction exactly like the buffer does
 * (§11.3: "all state lives in extension storage... never in background globals").
 */
import browser from "webextension-polyfill"

export type BrowserFamily = "brave" | "chromium" | "firefox"

export interface ExtensionConfig {
  /** A generated TimeOS device ID (UUIDv4) — never a hardware/browser identifier (mirrors the
   * Android client's own identity rule, §4.5). Generated once at first enrollment and kept
   * forever; every event this install has ever collected carries this id. */
  deviceId: string | null
  deviceToken: string | null
  deviceName: string
  browserFamily: BrowserFamily | null
  backendUrl: string
  nextSeq: number
  /** §11.6: "Raw URLs may be stored in IndexedDB on-device only... default off." Independent per
   * browser install, never synced. */
  rawUrlMode: boolean
}

const DEFAULT_BACKEND_URL = "http://localhost:8000"

const DEFAULTS: ExtensionConfig = {
  deviceId: null,
  deviceToken: null,
  deviceName: "",
  browserFamily: null,
  backendUrl: DEFAULT_BACKEND_URL,
  nextSeq: 0,
  rawUrlMode: false
}

export async function getConfig(): Promise<ExtensionConfig> {
  const stored = await browser.storage.local.get(Object.keys(DEFAULTS))
  return { ...DEFAULTS, ...stored } as ExtensionConfig
}

export async function setConfig(
  patch: Partial<ExtensionConfig>
): Promise<void> {
  await browser.storage.local.set(patch)
}

export function isEnrolled(config: ExtensionConfig): boolean {
  return config.deviceId !== null && config.deviceToken !== null
}

/** Detects Brave vs plain Chromium at runtime — the two share a byte-identical build (§11.1), so
 * this can't be resolved at build time the way the Firefox target is. `navigator.brave` is a
 * real, documented Brave-only API requiring no extra permission. Firefox never calls this; its
 * `browserFamily` is set directly from the build target. */
export async function detectChromiumBrowserFamily(): Promise<
  "brave" | "chromium"
> {
  const nav = navigator as Navigator & {
    brave?: { isBrave: () => Promise<boolean> }
  }
  try {
    if (nav.brave && (await nav.brave.isBrave())) {
      return "brave"
    }
  } catch {
    // Feature-detection failed for some reason — fall through to the safe default. The
    // enrollment UI lets the user correct this manually if it ever guesses wrong.
  }
  return "chromium"
}
