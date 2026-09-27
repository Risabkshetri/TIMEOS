import { describe, expect, it } from "vitest"

import {
  INITIAL_STATE,
  reconcileOnWake,
  reduce,
  type AttributionState
} from "../attribution"

const T0 = 1_700_000_000_000

const FOCUSED_ACTIVE: AttributionState = {
  currentDomain: null,
  windowFocused: true,
  idleState: "active",
  lastSeenTs: T0
}

describe("reduce — §11.2 attribution", () => {
  it("emits DOMAIN_FOCUS_START when a domain becomes active in a focused, non-idle window", () => {
    const { state, events } = reduce(FOCUSED_ACTIVE, {
      kind: "tab-changed",
      domain: "github.com",
      ts: T0 + 1000
    })
    expect(state.currentDomain).toBe("github.com")
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_START", domain: "github.com", ts: T0 + 1000 }
    ])
  })

  it("emits nothing for a tab change while the window is unfocused — background tabs accrue zero", () => {
    const unfocused: AttributionState = {
      ...FOCUSED_ACTIVE,
      windowFocused: false
    }
    const { events } = reduce(unfocused, {
      kind: "tab-changed",
      domain: "github.com",
      ts: T0 + 1000
    })
    expect(events).toEqual([])
  })

  it("emits DOMAIN_FOCUS_END when the window loses focus while a domain is attributed", () => {
    const attributed: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const { state, events } = reduce(attributed, {
      kind: "window-focus-changed",
      focused: false,
      ts: T0 + 5000
    })
    expect(state.windowFocused).toBe(false)
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_END", domain: "github.com", ts: T0 + 5000 }
    ])
  })

  it("emits DOMAIN_FOCUS_END when the browser goes idle (180s threshold enforced by background.ts)", () => {
    const attributed: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const { events } = reduce(attributed, {
      kind: "idle-state-changed",
      state: "idle",
      ts: T0 + 9000
    })
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_END", domain: "github.com", ts: T0 + 9000 }
    ])
  })

  it("emits DOMAIN_FOCUS_START when returning from idle to active with a domain already current", () => {
    const idleButPresent: AttributionState = {
      currentDomain: "github.com",
      windowFocused: true,
      idleState: "idle",
      lastSeenTs: T0
    }
    const { events } = reduce(idleButPresent, {
      kind: "idle-state-changed",
      state: "active",
      ts: T0 + 2000
    })
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_START", domain: "github.com", ts: T0 + 2000 }
    ])
  })

  it("switching domains while attributed ends the old one and starts the new one atomically", () => {
    const attributed: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const { events } = reduce(attributed, {
      kind: "tab-changed",
      domain: "youtube.com",
      ts: T0 + 3000
    })
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_END", domain: "github.com", ts: T0 + 3000 },
      { type: "DOMAIN_FOCUS_START", domain: "youtube.com", ts: T0 + 3000 }
    ])
  })

  it("navigating to a non-attributable page (null domain) ends the session with no new start", () => {
    const attributed: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const { state, events } = reduce(attributed, {
      kind: "tab-changed",
      domain: null,
      ts: T0 + 4000
    })
    expect(state.currentDomain).toBeNull()
    expect(events).toEqual([
      { type: "DOMAIN_FOCUS_END", domain: "github.com", ts: T0 + 4000 }
    ])
  })

  it("a heartbeat alone (no dimension changed) never emits an event", () => {
    const attributed: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const { state, events } = reduce(attributed, {
      kind: "heartbeat",
      ts: T0 + 60_000
    })
    expect(events).toEqual([])
    expect(state.lastSeenTs).toBe(T0 + 60_000) // still advances, for §11.3's reconciliation
  })

  it("a redundant focus-changed signal with the same value emits nothing", () => {
    const { events } = reduce(FOCUSED_ACTIVE, {
      kind: "window-focus-changed",
      focused: true,
      ts: T0 + 1000
    })
    expect(events).toEqual([])
  })
})

describe("reconcileOnWake — §11.3 background-lifetime reconciliation", () => {
  const HEARTBEAT_BOUND_MS = 120_000 // 2 minutes, generous over the spec's 1-minute alarm

  it("does nothing when the persisted state is fresh (within the heartbeat bound)", () => {
    const state: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const result = reconcileOnWake(state, T0 + 30_000, HEARTBEAT_BOUND_MS)
    expect(result.events).toEqual([])
    expect(result.state).toEqual(state)
  })

  it("closes a stale open interval at the last-seen instant, not at now", () => {
    const state: AttributionState = {
      ...FOCUSED_ACTIVE,
      currentDomain: "github.com"
    }
    const now = T0 + 10 * 60_000 // 10 minutes later — well past the heartbeat bound
    const result = reconcileOnWake(state, now, HEARTBEAT_BOUND_MS)
    expect(result.events).toEqual([
      { type: "DOMAIN_FOCUS_END", domain: "github.com", ts: T0 }
    ])
    expect(result.state.currentDomain).toBeNull()
  })

  it("emits no close event when nothing was attributed at the time of the gap", () => {
    const state: AttributionState = { ...INITIAL_STATE, lastSeenTs: T0 }
    const result = reconcileOnWake(state, T0 + 10 * 60_000, HEARTBEAT_BOUND_MS)
    expect(result.events).toEqual([])
  })

  it("treats a never-initialized state (lastSeenTs=0) as nothing to reconcile", () => {
    const result = reconcileOnWake(
      INITIAL_STATE,
      T0 + 10 * 60_000,
      HEARTBEAT_BOUND_MS
    )
    expect(result.events).toEqual([])
    expect(result.state).toEqual(INITIAL_STATE)
  })
})
