/**
 * Device enrollment and batch sync — reuses the EXISTING backend ingest contract unchanged
 * (§38 Phase 9's own "APIs: existing ingest"; no new endpoint was needed, only new `EventType`
 * values the backend already accepts generically — see backend/timeos/schemas/events.py).
 */
import browser from "webextension-polyfill"

import { type BrowserFamily, getConfig, setConfig } from "./config"
import { type PendingEvent, peekBatch, removeBatch } from "./store"

const SCHEMA_VERSION = 1
const EVENT_SOURCE = "extension"
const FLUSH_BATCH_SIZE = 200 // §11.2: "flush every 5 min or 200 events"

export class SyncError extends Error {}

function localTimezone(): { tzId: string; tzOffsetMin: number } {
  const tzId = Intl.DateTimeFormat().resolvedOptions().timeZone
  // getTimezoneOffset() is minutes to ADD to local time to get UTC — the ingest contract wants
  // the offset FROM UTC, i.e. the negation.
  const tzOffsetMin = -new Date().getTimezoneOffset()
  return { tzId, tzOffsetMin }
}

export async function enroll(
  enrollmentCode: string,
  deviceName: string,
  browserFamily: BrowserFamily
): Promise<void> {
  const config = await getConfig()
  const deviceId = config.deviceId ?? crypto.randomUUID()

  const res = await fetch(`${config.backendUrl}/v1/devices/enroll`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enrollment_code: enrollmentCode,
      device_id: deviceId,
      name: deviceName,
      platform: "browser",
      browser_family: browserFamily
    })
  })
  if (!res.ok) {
    throw new SyncError(`enrollment failed: ${res.status} ${await res.text()}`)
  }
  const body = (await res.json()) as { device_id: string; token: string }
  await setConfig({
    deviceId: body.device_id,
    deviceToken: body.token,
    deviceName,
    browserFamily
  })
}

/** Builds a fully ingest-ready event and enqueues it (`store.ts`) — called by `background.ts`
 * for every `DomainFocusEvent` the attribution reducer emits. Assigns the next `seq` from
 * persisted config, so sequencing survives a service-worker eviction exactly like everything
 * else in this extension. */
export async function enqueueDomainEvent(
  type: "DOMAIN_FOCUS_START" | "DOMAIN_FOCUS_END",
  domain: string,
  tsMs: number,
  enqueueFn: (event: PendingEvent) => Promise<void>
): Promise<void> {
  const config = await getConfig()
  const { tzId, tzOffsetMin } = localTimezone()
  const seq = config.nextSeq
  await setConfig({ nextSeq: seq + 1 })

  await enqueueFn({
    event_id: crypto.randomUUID(),
    seq,
    ts_utc: tsMs,
    tz_offset_min: tzOffsetMin,
    tz_id: tzId,
    uptime_ms: Math.round(performance.now()),
    type,
    payload: { domain }
  })
}

/** Sends up to `FLUSH_BATCH_SIZE` buffered events in one `POST /v1/ingest/batch` call. Returns
 * the number actually sent (0 if not enrolled yet, or nothing was pending). A batch is only
 * removed from the local buffer after the server confirms it — §12.3's idempotent-replay
 * contract means a retried batch (e.g. after a dropped response) is safe to resend as-is. */
export async function flush(): Promise<{ sent: number }> {
  const config = await getConfig()
  if (config.deviceId === null || config.deviceToken === null) {
    return { sent: 0 }
  }

  const pending = await peekBatch(FLUSH_BATCH_SIZE)
  if (pending.length === 0) {
    return { sent: 0 }
  }

  const batchId = crypto.randomUUID()
  const seqFrom = pending[0].seq
  const seqTo = pending[pending.length - 1].seq

  const res = await fetch(`${config.backendUrl}/v1/ingest/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.deviceToken}`
    },
    body: JSON.stringify({
      batch_id: batchId,
      device_id: config.deviceId,
      seq_from: seqFrom,
      seq_to: seqTo,
      events: pending.map((event) => ({
        ...event,
        device_id: config.deviceId,
        clock_flags: [],
        source: EVENT_SOURCE,
        schema_v: SCHEMA_VERSION
      }))
    })
  })

  if (!res.ok) {
    throw new SyncError(
      `ingest batch failed: ${res.status} ${await res.text()}`
    )
  }

  await removeBatch(pending.map((event) => event.seq))
  return { sent: pending.length }
}

export async function logout(): Promise<void> {
  await browser.storage.local.clear()
}
