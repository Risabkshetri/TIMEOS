/**
 * §11.2: "Every URL is reduced to its registrable domain using a bundled Public Suffix List
 * snapshot, at the moment of capture, inside the background context. The full URL is never
 * written to storage and never leaves the function scope."
 *
 * `tldts` bundles its own PSL data snapshot at build time (no network fetch, no live PSL lookup)
 * and correctly handles multi-level public suffixes (`co.uk`, `github.io`) — exactly what a
 * hand-rolled "split on the last two dots" reduction gets wrong. This is the ONLY function in the
 * whole extension that ever sees a full URL; every caller gets back a domain string or `null`,
 * never the URL itself.
 */
import { getDomain } from "tldts"

/**
 * Reduces a full URL (or bare hostname) to its registrable domain.
 * `mail.google.com/u/0/#inbox?q=...` -> `google.com`. Returns `null` for anything that isn't a
 * real, publicly-registrable domain (a bare IP address, `localhost`, a browser-internal page like
 * `chrome://extensions`, or a malformed URL) — there is nothing meaningful to attribute time to
 * in those cases, and returning `null` lets the caller skip attribution entirely rather than
 * invent a fake domain.
 */
export function toRegistrableDomain(url: string): string | null {
  try {
    return getDomain(url, { allowPrivateDomains: false })
  } catch {
    return null
  }
}
