/**
 * §11.2's attribution rule and §11.3's background-lifetime reconciliation, as a pure reducer.
 *
 * "A domain accrues time only when its tab is active, in a focused window, and the browser is
 * not idle" (§11.2). This module never touches a real browser API — `background.ts` is the only
 * place that does, translating real `tabs`/`windows`/`idle`/`alarms` events into the
 * `AttributionSignal` values this file's pure `reduce()` consumes. Keeping the state machine pure
 * is what makes §11.3's core design possible: "all state lives in extension storage and every
 * wake reconciles from `last_seen_ts`" — a pure reducer over a persisted `AttributionState` can be
 * replayed identically whether the background context has been alive for hours (Firefox's event
 * pages) or was just evicted and restarted 30 seconds ago (a Chromium service worker).
 */

export type IdleState = "active" | "idle" | "locked"

export interface AttributionState {
  /** The registrable domain of the current candidate tab, or `null` if none (no tabs, or the
   * active tab isn't attributable — a browser-internal page, a private window, etc). */
  currentDomain: string | null
  windowFocused: boolean
  idleState: IdleState
  /** Epoch ms of the last signal this reducer actually processed — §11.3's `last_seen_ts`, the
   * only thing a wake needs to reconcile from. */
  lastSeenTs: number
}

export type AttributionSignal =
  | { kind: "tab-changed"; domain: string | null; ts: number }
  | { kind: "window-focus-changed"; focused: boolean; ts: number }
  | { kind: "idle-state-changed"; state: IdleState; ts: number }
  | { kind: "heartbeat"; ts: number }

export interface DomainFocusEvent {
  type: "DOMAIN_FOCUS_START" | "DOMAIN_FOCUS_END"
  domain: string
  ts: number
}

export const INITIAL_STATE: AttributionState = {
  currentDomain: null,
  windowFocused: false,
  idleState: "active",
  lastSeenTs: 0
}

/** §11.2's condition, evaluated against a state. */
function isAttributed(state: AttributionState): boolean {
  return (
    state.currentDomain !== null &&
    state.windowFocused &&
    state.idleState === "active"
  )
}

export interface ReduceResult {
  state: AttributionState
  events: DomainFocusEvent[]
}

/**
 * Applies one signal to the current state, returning the new state and any DOMAIN_FOCUS_START/
 * END events the transition produced. A domain change, a focus change, or an idle-state change
 * can each independently flip whether §11.2's condition holds — this function is the one place
 * that condition is evaluated, so `background.ts` never has to reason about it directly.
 */
export function reduce(
  state: AttributionState,
  signal: AttributionSignal
): ReduceResult {
  const wasAttributed = isAttributed(state)
  const previousDomain = state.currentDomain

  let next: AttributionState
  switch (signal.kind) {
    case "tab-changed":
      next = { ...state, currentDomain: signal.domain, lastSeenTs: signal.ts }
      break
    case "window-focus-changed":
      next = { ...state, windowFocused: signal.focused, lastSeenTs: signal.ts }
      break
    case "idle-state-changed":
      next = { ...state, idleState: signal.state, lastSeenTs: signal.ts }
      break
    case "heartbeat":
      next = { ...state, lastSeenTs: signal.ts }
      break
  }

  const nowAttributed = isAttributed(next)
  const events: DomainFocusEvent[] = []

  if (
    wasAttributed &&
    (!nowAttributed || previousDomain !== next.currentDomain)
  ) {
    // previousDomain is non-null here because wasAttributed required currentDomain !== null.
    events.push({
      type: "DOMAIN_FOCUS_END",
      domain: previousDomain as string,
      ts: signal.ts
    })
  }
  if (
    nowAttributed &&
    (!wasAttributed || previousDomain !== next.currentDomain)
  ) {
    events.push({
      type: "DOMAIN_FOCUS_START",
      domain: next.currentDomain as string,
      ts: signal.ts
    })
  }

  return { state: next, events }
}

/**
 * §11.3: "On every wake the background context reconciles: if `last_seen_ts` is older than the
 * alarm period, close the open interval at `last_seen_ts` and open an UNOBSERVED gap." Called
 * once, immediately after loading a persisted state from `storage.session`/`storage.local` on
 * background-context startup — before processing any new live signal. A gap this finds is NOT
 * itself synced anywhere (there is no "UNOBSERVED" browser event type — §11.2's own gap-marking
 * only ever mattered for the domain interval that needs closing); the effect that matters is the
 * DOMAIN_FOCUS_END emitted at the stale `last_seen_ts`, truncating the session exactly where
 * `browser_sessionize.ts`'s own end-of-stream rule would have anyway, without waiting for a
 * heartbeat that may never come if the eviction was actually a real browser restart.
 */
export function reconcileOnWake(
  state: AttributionState,
  now: number,
  heartbeatBoundMs: number
): ReduceResult {
  const staleFor = now - state.lastSeenTs
  if (state.lastSeenTs === 0 || staleFor <= heartbeatBoundMs) {
    return { state, events: [] }
  }

  const events: DomainFocusEvent[] = []
  if (isAttributed(state)) {
    events.push({
      type: "DOMAIN_FOCUS_END",
      domain: state.currentDomain as string,
      ts: state.lastSeenTs
    })
  }

  // The gap itself is unobserved: we don't know what happened while the background context was
  // dead, so the reconciled state starts fresh rather than guessing the tab/focus/idle state is
  // still what it was before the gap.
  return {
    state: { ...INITIAL_STATE, lastSeenTs: state.lastSeenTs },
    events
  }
}
