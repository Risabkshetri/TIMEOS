import { describe, expect, it } from "vitest"

import { toRegistrableDomain } from "../psl"

describe("toRegistrableDomain", () => {
  it.each([
    ["https://github.com/anthropics/claude-code", "github.com"],
    ["https://mail.google.com/u/0/#inbox?q=is:unread", "google.com"],
    ["http://www.example.com/path", "example.com"],
    // Multi-level public suffixes — the whole reason a bundled PSL is used instead of a
    // hand-rolled "split on the last two dots" reduction (§38 Phase 9's own named test case).
    ["https://www.bbc.co.uk/news", "bbc.co.uk"],
    ["https://sub.example.co.uk/", "example.co.uk"],
    ["https://someone.github.io/their-project/", "github.io"],
    ["https://a.b.c.github.io/", "github.io"],
    ["https://timeos.herokuapp.com/dashboard", "herokuapp.com"],
    // Subdomains of an ordinary domain all reduce to the same registrable domain.
    ["https://docs.google.com/document/d/abc", "google.com"],
    ["https://calendar.google.com/calendar/r", "google.com"],
    // No scheme.
    ["example.com/path", "example.com"]
  ])("%s -> %s", (url, expected) => {
    expect(toRegistrableDomain(url)).toBe(expected)
  })

  it.each([
    ["not a url at all", null],
    ["http://localhost:3000/app", null],
    ["http://127.0.0.1:8080/", null],
    ["chrome://extensions", null],
    ["about:blank", null],
    ["", null]
  ])("%s -> null (nothing to attribute)", (url, expected) => {
    expect(toRegistrableDomain(url)).toBe(expected)
  })
})
