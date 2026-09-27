import { useEffect, useState } from "react"

import {
  detectChromiumBrowserFamily,
  type BrowserFamily,
  type ExtensionConfig,
  getConfig,
  isEnrolled
} from "./lib/config"
import { enroll, flush, logout, SyncError } from "./lib/sync"
import { pendingCount } from "./lib/store"

const IS_FIREFOX_BUILD =
  process.env.PLASMO_TARGET?.startsWith("firefox") ?? false

function IndexPopup() {
  const [config, setConfigState] = useState<ExtensionConfig | null>(null)
  const [pending, setPending] = useState(0)
  const [enrollmentCode, setEnrollmentCode] = useState("")
  const [deviceName, setDeviceName] = useState("")
  const [browserFamily, setBrowserFamily] = useState<BrowserFamily>(
    IS_FIREFOX_BUILD ? "firefox" : "chromium"
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setConfigState(await getConfig())
    setPending(await pendingCount())
  }

  useEffect(() => {
    void refresh()
    if (!IS_FIREFOX_BUILD) {
      void detectChromiumBrowserFamily().then(setBrowserFamily)
    }
  }, [])

  async function handleEnroll(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await enroll(
        enrollmentCode,
        deviceName || `${browserFamily} browser`,
        browserFamily
      )
      await refresh()
    } catch (err) {
      setError(
        err instanceof SyncError
          ? err.message
          : `Enrollment failed: ${
              err instanceof Error ? err.message : "could not reach the backend"
            }`
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleFlushNow() {
    setBusy(true)
    setError(null)
    try {
      await flush()
      await refresh()
    } catch (err) {
      setError(err instanceof SyncError ? err.message : "Sync failed.")
    } finally {
      setBusy(false)
    }
  }

  if (!config) {
    return <div style={{ padding: 16, width: 280 }}>Loading…</div>
  }

  return (
    <div
      style={{ padding: 16, width: 280, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>TimeOS</h1>

      {isEnrolled(config) ? (
        <div>
          <p style={{ fontSize: 12, color: "#666" }}>
            Enrolled as <strong>{config.deviceName}</strong> (
            {config.browserFamily})
          </p>
          <p style={{ fontSize: 12, color: "#666" }}>
            {pending} event(s) buffered
          </p>
          <button
            onClick={handleFlushNow}
            disabled={busy}
            style={{ marginTop: 8 }}>
            {busy ? "Syncing…" : "Sync now"}
          </button>
          <p style={{ fontSize: 11, color: "#999", marginTop: 12 }}>
            Only domains and durations are ever sent — no page content, no URLs,
            no query strings.
          </p>
          <button
            onClick={() => void logout().then(refresh)}
            style={{ marginTop: 8, fontSize: 11, color: "#999" }}>
            Remove this device
          </button>
        </div>
      ) : (
        <form onSubmit={handleEnroll}>
          <label style={{ display: "block", fontSize: 12, marginBottom: 8 }}>
            Enrollment code
            <input
              value={enrollmentCode}
              onChange={(e) => setEnrollmentCode(e.target.value.toUpperCase())}
              maxLength={8}
              required
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
          </label>
          <label style={{ display: "block", fontSize: 12, marginBottom: 8 }}>
            Device name
            <input
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder={`${browserFamily} browser`}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
          </label>
          {!IS_FIREFOX_BUILD ? (
            <label style={{ display: "block", fontSize: 12, marginBottom: 8 }}>
              Browser
              <select
                value={browserFamily}
                onChange={(e) =>
                  setBrowserFamily(e.target.value as BrowserFamily)
                }
                style={{ display: "block", width: "100%", marginTop: 4 }}>
                <option value="chromium">Chromium</option>
                <option value="brave">Brave</option>
              </select>
            </label>
          ) : null}
          <button type="submit" disabled={busy || enrollmentCode.length !== 8}>
            {busy ? "Enrolling…" : "Enroll this browser"}
          </button>
          {error ? (
            <p style={{ color: "crimson", fontSize: 11, marginTop: 8 }}>
              {error}
            </p>
          ) : null}
        </form>
      )}
    </div>
  )
}

export default IndexPopup
