/**
 * §11.2/§38 Phase 9: "A build-failing test asserts both manifests contain neither [host_permissions
 * nor content scripts]." Runs REAL builds for both targets and inspects the actual generated
 * manifest.json — not the source config — so a Plasmo upgrade or a dependency that quietly
 * requests a host permission would fail this test, not just a hand-maintained assumption about
 * what the build produces.
 */
import { execFileSync } from "node:child_process"
import { readFileSync } from "node:fs"
import path from "node:path"

import { describe, expect, it } from "vitest"

const EXTENSION_ROOT = path.resolve(__dirname, "..", "..")

function buildAndReadManifest(
  script: string,
  buildDir: string
): Record<string, unknown> {
  execFileSync("npm", ["run", script], { cwd: EXTENSION_ROOT, stdio: "pipe" })
  const manifestPath = path.join(
    EXTENSION_ROOT,
    "build",
    buildDir,
    "manifest.json"
  )
  return JSON.parse(readFileSync(manifestPath, "utf-8"))
}

describe("manifest security assertions (§11.2)", () => {
  it("the Chromium (Brave + Chromium) manifest has no host_permissions and no content_scripts", () => {
    const manifest = buildAndReadManifest("build", "chrome-mv3-prod")
    expect(manifest.host_permissions).toBeUndefined()
    expect(manifest.content_scripts).toBeUndefined()
    expect(manifest.manifest_version).toBe(3)
    expect(manifest.permissions).toEqual(
      expect.arrayContaining(["tabs", "idle", "storage", "alarms"])
    )
  }, 30_000)

  it("the Firefox manifest has no host_permissions and no content_scripts", () => {
    const manifest = buildAndReadManifest("build:firefox", "firefox-mv3-prod")
    expect(manifest.host_permissions).toBeUndefined()
    expect(manifest.content_scripts).toBeUndefined()
    expect(manifest.manifest_version).toBe(3)
    // §11.1: Firefox does not support background.service_worker — it must be an event page.
    const background = manifest.background as Record<string, unknown>
    expect(background.service_worker).toBeUndefined()
    expect(background.scripts).toBeDefined()
  }, 30_000)

  it("neither manifest requests webNavigation (§11.2)", () => {
    const chrome = buildAndReadManifest("build", "chrome-mv3-prod")
    const firefox = buildAndReadManifest("build:firefox", "firefox-mv3-prod")
    for (const manifest of [chrome, firefox]) {
      const permissions = (manifest.permissions as string[]) ?? []
      expect(permissions).not.toContain("webNavigation")
    }
  }, 30_000)
})
