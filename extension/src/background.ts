/**
 * §11's background context — the ONLY place in this extension that touches a real `tabs`/
 * `windows`/`idle`/`alarms` API. Everything it decides is delegated to the pure reducer in
 * `lib/attribution.ts`; everything it persists goes through `lib/config.ts` (scalars) and
 * `lib/store.ts` (the event buffer) — never a background-global variable, per §11.3's core design
 * rule, because a Chromium MV3 service worker can be evicted ~30s after going idle and any
 * in-memory state would simply vanish.
 *
 * One TypeScript source tree für both engine targets (§11.1): `webextension-polyfill` normalises
 * `chrome.*`'s callback API and `browser.*`'s promise API into one promise-based surface, so
 * nothing below is Chromium- or Firefox-specific.
 */
import browser, { type Tabs, type Windows } from "webextension-polyfill"

import {
  type AttributionState,
  type IdleState,
  INITIAL_STATE,
  reconcileOnWake,
  reduce
} from "./lib/attribution"
import {
  detectChromiumBrowserFamily,
  getConfig,
  isEnrolled,
  setConfig
} from "./lib/config"
import { toRegistrableDomain } from "./lib/psl"
import { enqueueDomainEvent, flush } from "./lib/sync"
import { enqueue, pendingCount, recordRawUrlLocally } from "./lib/store"

// §11.2: "idle... 180 s". §11.3: "A 1-minute alarms heartbeat bounds gap size."
const IDLE_THRESHOLD_SECONDS = 180
const HEARTBEAT_ALARM_NAME = "timeos-heartbeat"
const HEARTBEAT_PERIOD_MINUTES = 1
// Generous over the 1-minute heartbeat so a single missed alarm tick doesn't itself look like an
// eviction — only a GENUINE gap (the background context was actually dead) should reconcile.
const HEARTBEAT_BOUND_MS = 3 * 60_000
const FLUSH_EVENT_COUNT_THRESHOLD = 200
const STATE_STORAGE_KEY = "attributionState"

let state: AttributionState = INITIAL_STATE
let readyPromise: Promise<void> | null = null

async function loadState(): Promise<AttributionState> {
  const stored = await browser.storage.local.get(STATE_STORAGE_KEY)
  return (
    (stored[STATE_STORAGE_KEY] as AttributionState | undefined) ?? INITIAL_STATE
  )
}

async function saveState(next: AttributionState): Promise<void> {
  await browser.storage.local.set({ [STATE_STORAGE_KEY]: next })
}

async function applyEvents(
  events: ReturnType<typeof reduce>["events"]
): Promise<void> {
  for (const event of events) {
    await enqueueDomainEvent(event.type, event.domain, event.ts, enqueue)
  }
  if (
    events.length > 0 &&
    (await pendingCount()) >= FLUSH_EVENT_COUNT_THRESHOLD
  ) {
    await flush().catch(() => {
      // A flush failure here is not fatal — the events stay buffered in IndexedDB and the next
      // heartbeat (or the next threshold-triggering enqueue) retries. Never throw out of an
      // event listener over a transient network error.
    })
  }
}

async function apply(signal: Parameters<typeof reduce>[1]): Promise<void> {
  const { state: next, events } = reduce(state, signal)
  state = next
  await saveState(state)
  await applyEvents(events)
}

/** §11.3: runs once per background-context startup, before any live signal is processed. */
async function reconcile(): Promise<void> {
  state = await loadState()
  const { state: next, events } = reconcileOnWake(
    state,
    Date.now(),
    HEARTBEAT_BOUND_MS
  )
  state = next
  await saveState(state)
  await applyEvents(events)
}

function ensureReady(): Promise<void> {
  if (readyPromise === null) {
    readyPromise = reconcile()
  }
  return readyPromise
}

async function isRealWindowFocused(windowId: number): Promise<boolean> {
  if (windowId === browser.windows.WINDOW_ID_NONE) {
    return false
  }
  try {
    const window = await browser.windows.get(windowId)
    // §11.2: "Private/incognito windows are excluded entirely, in all three browsers." Brave's
    // Tor windows are also incognito windows under the hood, so this same check covers them.
    return window.focused === true && window.incognito !== true
  } catch {
    return false // the window was closed before we could check it
  }
}

async function domainOfActiveTabIn(windowId: number): Promise<string | null> {
  const tabs = await browser.tabs.query({ windowId, active: true })
  const url = tabs[0]?.url
  if (!url) return null

  // §11.6: the ONLY place a full URL is ever looked at beyond this function's own scope — only
  // when the user has explicitly opted in, and only into this browser's own local IndexedDB.
  const config = await getConfig()
  if (config.rawUrlMode) {
    await recordRawUrlLocally(url, Date.now())
  }
  return toRegistrableDomain(url)
}

async function handleFocusedWindowChanged(windowId: number): Promise<void> {
  await ensureReady()
  const focused = await isRealWindowFocused(windowId)
  await apply({ kind: "window-focus-changed", focused, ts: Date.now() })
  if (focused) {
    const domain = await domainOfActiveTabIn(windowId)
    await apply({ kind: "tab-changed", domain, ts: Date.now() })
  } else {
    await apply({ kind: "tab-changed", domain: null, ts: Date.now() })
  }
}

browser.windows.onFocusChanged.addListener((windowId: number) => {
  void handleFocusedWindowChanged(windowId)
})

browser.tabs.onActivated.addListener(
  (activeInfo: Tabs.OnActivatedActiveInfoType) => {
    void (async () => {
      await ensureReady()
      if (!state.windowFocused) return
      const currentWindow = await browser.windows.getCurrent()
      if (currentWindow.id !== activeInfo.windowId) return
      const domain = await domainOfActiveTabIn(activeInfo.windowId)
      await apply({ kind: "tab-changed", domain, ts: Date.now() })
    })()
  }
)

browser.tabs.onUpdated.addListener(
  (tabId: number, changeInfo: Tabs.OnUpdatedChangeInfoType, tab: Tabs.Tab) => {
    if (!changeInfo.url || !tab.active) return
    void (async () => {
      await ensureReady()
      if (!state.windowFocused) return
      const url = changeInfo.url as string
      const config = await getConfig() // §11.6, same rule as domainOfActiveTabIn
      if (config.rawUrlMode) {
        await recordRawUrlLocally(url, Date.now())
      }
      const domain = toRegistrableDomain(url)
      await apply({ kind: "tab-changed", domain, ts: Date.now() })
    })()
  }
)

browser.idle.setDetectionInterval(IDLE_THRESHOLD_SECONDS)
browser.idle.onStateChanged.addListener((newState: string) => {
  void (async () => {
    await ensureReady()
    const idleState: IdleState =
      newState === "active"
        ? "active"
        : newState === "locked"
          ? "locked"
          : "idle"
    await apply({
      kind: "idle-state-changed",
      state: idleState,
      ts: Date.now()
    })
  })()
})

browser.alarms.create(HEARTBEAT_ALARM_NAME, {
  periodInMinutes: HEARTBEAT_PERIOD_MINUTES
})
browser.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== HEARTBEAT_ALARM_NAME) return
  void (async () => {
    await ensureReady()
    await apply({ kind: "heartbeat", ts: Date.now() })
    const config = await getConfig()
    if (isEnrolled(config)) {
      await flush().catch(() => {
        // Same reasoning as applyEvents' flush call — retried on the next heartbeat.
      })
    }
  })()
})

// First-run browser_family detection for Chromium-target installs (Firefox's build sets this
// directly — see popup.tsx's enrollment flow, which is Firefox-target-aware). Harmless to run on
// every startup; it's idempotent and only writes when unset.
void (async () => {
  const config = await getConfig()
  if (
    config.browserFamily === null &&
    process.env.PLASMO_TARGET?.startsWith("chrome")
  ) {
    const family = await detectChromiumBrowserFamily()
    await setConfig({ browserFamily: family })
  }
})()

void ensureReady()
