/**
 * The session clock (decision E16, replacing E1).
 *
 * Every extension context stamps captures with the system wall clock, Date.now(). The service
 * worker owns the origin t0 (stored in the session record) and converts captures to session
 * time with toSessionT.
 *
 * The page's performance clock is not used: it stops while the machine sleeps, so a tab opened
 * before a sleep runs behind the service worker's clock and its captures land before t0.
 */

export type EpochMs = number;

/** A capture this far before t0 means a clock problem, not a race. */
export const CLOCK_SKEW_TOLERANCE_MS = 1000;

export function epochNow(): EpochMs {
  return Date.now();
}

/** Seconds from session start, rounded to the millisecond, never negative. */
export function toSessionT(at: EpochMs, t0: EpochMs): number {
  return Math.max(0, Math.round(at - t0)) / 1000;
}

/** True when a capture is stamped implausibly early (see CLOCK_SKEW_TOLERANCE_MS). */
export function isSkewed(at: EpochMs, t0: EpochMs): boolean {
  return t0 - at > CLOCK_SKEW_TOLERANCE_MS;
}
