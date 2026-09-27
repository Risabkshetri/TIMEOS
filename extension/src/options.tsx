import { useEffect, useState } from "react"

import { type ExtensionConfig, getConfig, setConfig } from "./lib/config"

function IndexOptions() {
  const [config, setConfigState] = useState<ExtensionConfig | null>(null)
  const [backendUrl, setBackendUrl] = useState("")
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    void getConfig().then((c) => {
      setConfigState(c)
      setBackendUrl(c.backendUrl)
    })
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    await setConfig({ backendUrl })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function toggleRawUrlMode(checked: boolean) {
    await setConfig({ rawUrlMode: checked })
    setConfigState((c) => (c ? { ...c, rawUrlMode: checked } : c))
  }

  if (!config) return null

  return (
    <div
      style={{
        padding: 24,
        maxWidth: 480,
        fontFamily: "system-ui, sans-serif"
      }}>
      <h1 style={{ fontSize: 18, fontWeight: 600 }}>TimeOS Settings</h1>

      <form onSubmit={handleSave} style={{ marginTop: 16 }}>
        <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>
          Backend URL
          <input
            value={backendUrl}
            onChange={(e) => setBackendUrl(e.target.value)}
            style={{
              display: "block",
              width: "100%",
              marginTop: 4,
              padding: 6
            }}
          />
        </label>
        <button type="submit" style={{ marginTop: 8 }}>
          Save
        </button>
        {saved ? (
          <span style={{ marginLeft: 8, fontSize: 12, color: "green" }}>
            Saved.
          </span>
        ) : null}
      </form>

      <hr style={{ margin: "24px 0" }} />

      <h2 style={{ fontSize: 14, fontWeight: 600 }}>Raw URL mode</h2>
      <p style={{ fontSize: 12, color: "#666" }}>
        §11.6: when enabled, full URLs (not just the domain) are stored in this
        browser's local IndexedDB only. They are never synced to the server,
        never sent to any AI path, and this setting is independent per browser
        install. Off by default.
      </p>
      <label style={{ fontSize: 13 }}>
        <input
          type="checkbox"
          checked={config.rawUrlMode}
          onChange={(e) => void toggleRawUrlMode(e.target.checked)}
        />{" "}
        Store full URLs locally on this device
      </label>
    </div>
  )
}

export default IndexOptions
