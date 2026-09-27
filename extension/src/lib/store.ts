/**
 * §11.2's IndexedDB buffer: "Buffer in IndexedDB; flush every 5 min or 200 events." Domain-focus
 * events accumulate here between flushes, surviving a service-worker eviction (§11.3) — unlike an
 * in-memory array, IndexedDB persists across background-context restarts, which is exactly the
 * property a Chromium MV3 service worker (evicted after ~30s idle) needs.
 *
 * Stores only what the ingest contract needs (§12.3's `IngestEvent` shape) — never a raw URL,
 * only the already-reduced registrable domain (`timeos/lib/psl.ts`'s only output).
 */
import { type IDBPDatabase, openDB } from "idb"

const DB_NAME = "timeos-extension"
const DB_VERSION = 2
const STORE_NAME = "pending_events"
const RAW_URL_STORE_NAME = "local_raw_urls"
const MAX_RAW_URL_ROWS = 5000 // a bound so §11.6's opt-in local log can't grow unbounded forever

/** Shaped to match backend/timeos/schemas/events.py's `IngestEvent` exactly, minus `device_id`
 * (constant per install — `sync.ts` attaches it at send time) and `schema_v`/`source` (also
 * constant, attached the same way). */
export interface PendingEvent {
  event_id: string
  seq: number
  ts_utc: number
  tz_offset_min: number
  tz_id: string
  uptime_ms: number
  type: "DOMAIN_FOCUS_START" | "DOMAIN_FOCUS_END"
  payload: { domain: string }
}

let dbPromise: Promise<IDBPDatabase> | null = null

function getDb(): Promise<IDBPDatabase> {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          db.createObjectStore(STORE_NAME, { keyPath: "seq" })
        }
        if (oldVersion < 2) {
          db.createObjectStore(RAW_URL_STORE_NAME, {
            keyPath: "id",
            autoIncrement: true
          })
        }
      }
    })
  }
  return dbPromise
}

export async function enqueue(event: PendingEvent): Promise<void> {
  const db = await getDb()
  await db.put(STORE_NAME, event)
}

export async function pendingCount(): Promise<number> {
  const db = await getDb()
  return db.count(STORE_NAME)
}

/** Returns up to `limit` pending events in `seq` order — the order the ingest contract requires
 * (`seq_from`/`seq_to` describe a contiguous range). Does NOT remove them; the caller only
 * removes a batch after the server has confirmed it, so a flush that fails partway through (the
 * network drops mid-request) leaves the buffer intact for the next attempt. */
export async function peekBatch(limit: number): Promise<PendingEvent[]> {
  const db = await getDb()
  const all: PendingEvent[] = await db.getAll(STORE_NAME)
  all.sort((a, b) => a.seq - b.seq)
  return all.slice(0, limit)
}

export async function removeBatch(seqs: number[]): Promise<void> {
  const db = await getDb()
  const tx = db.transaction(STORE_NAME, "readwrite")
  await Promise.all(seqs.map((seq) => tx.store.delete(seq)))
  await tx.done
}

/**
 * §11.6: "Raw URLs may be stored in IndexedDB on-device only, per browser, behind an explicit
 * toggle. Never synced, never in any AI path, default off." This is the ONLY function in the
 * whole extension that ever persists a full URL — `background.ts` calls it exclusively when
 * `config.rawUrlMode` is true, and nothing here (or anywhere else) ever reads this store back
 * into a sync payload; `sync.ts`'s `flush()` only ever touches `pending_events`.
 */
export async function recordRawUrlLocally(
  url: string,
  tsMs: number
): Promise<void> {
  const db = await getDb()
  await db.add(RAW_URL_STORE_NAME, { url, ts: tsMs })
  const count = await db.count(RAW_URL_STORE_NAME)
  if (count > MAX_RAW_URL_ROWS) {
    const tx = db.transaction(RAW_URL_STORE_NAME, "readwrite")
    let cursor = await tx.store.openCursor()
    let toDelete = count - MAX_RAW_URL_ROWS
    while (cursor && toDelete > 0) {
      await cursor.delete()
      cursor = await cursor.continue()
      toDelete -= 1
    }
    await tx.done
  }
}
