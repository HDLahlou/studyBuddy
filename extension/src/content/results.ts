/**
 * Waiting for a run/submit result panel to settle. Polling only (no MutationObserver), so it
 * behaves the same under fake timers in tests.
 *
 * A result counts as new once the verdict element is a different node from the one present at
 * click time, or its text changed. It is settled when the panel's text is unchanged across
 * `stablePolls` consecutive polls and the probe reports it ready (or `readyGraceMs` has passed
 * since the verdict appeared, for panels that never show the ready marker, e.g. compile errors).
 * Its time is when the new verdict first appeared.
 */

import type { EpochMs } from "../shared/clock";
import { realTimers, type Timers } from "../shared/timers";

export interface ResultProbe<T> {
  /** The verdict element, if one is on the page. */
  verdictNode(): Element | null;
  /** Text that must stop changing before the result is read (usually the panel's text). */
  fingerprint(node: Element): string;
  /** Optional readiness check; until it passes (or `readyGraceMs` elapses) the result isn't read. */
  ready?(node: Element): boolean;
  read(node: Element): T | null;
}

export type Settled<T> =
  | { ok: true; result: T; appearedAt: EpochMs; settledAt: EpochMs }
  | { ok: false; reason: FailReason; at: EpochMs };

/**
 * cancelled: the session stopped (nothing is recorded).
 * superseded: a newer run/submit of the same kind started before this one settled; recorded as
 * an unknown result so a later verdict is never credited to the wrong click.
 */
export type FailReason = "timeout" | "cancelled" | "unreadable" | "superseded";

export interface Waiter<T> {
  done: Promise<Settled<T>>;
  cancel: (reason?: "cancelled" | "superseded") => void;
}

export interface WaitOptions {
  pollMs: number;
  stablePolls: number;
  timeoutMs: number;
  readyGraceMs?: number;
}

export const DEFAULT_WAIT: WaitOptions = { pollMs: 250, stablePolls: 2, timeoutMs: 30_000, readyGraceMs: 5000 };

export function waitForResult<T>(
  probe: ResultProbe<T>,
  now: () => EpochMs,
  opts: WaitOptions = DEFAULT_WAIT,
  timers: Timers = realTimers,
): Waiter<T> {
  const staleNode = probe.verdictNode();
  const staleText = staleNode?.textContent ?? null;
  const startedAt = now();
  let handle: unknown = null;
  let cancelled = false;
  let resolveFn: (s: Settled<T>) => void = () => {};
  const done = new Promise<Settled<T>>((resolve) => (resolveFn = resolve));

  let appearedAt: EpochMs | null = null;
  let lastPrint: string | null = null;
  let stable = 0;

  const tick = () => {
    if (cancelled) return;
    const t = now();
    const node = probe.verdictNode();
    const isNew = node !== null && (node !== staleNode || node.textContent !== staleText);
    if (isNew && node) {
      if (appearedAt === null) appearedAt = t;
      const print = probe.fingerprint(node);
      stable = print === lastPrint ? stable + 1 : 0;
      lastPrint = print;
      const ready = probe.ready?.(node) ?? true;
      const graceOver = t - appearedAt >= (opts.readyGraceMs ?? 5000);
      if (stable >= opts.stablePolls - 1 && (ready || graceOver)) {
        const result = probe.read(node);
        resolveFn(result ? { ok: true, result, appearedAt, settledAt: t } : { ok: false, reason: "unreadable", at: t });
        return;
      }
    }
    if (t - startedAt >= opts.timeoutMs) {
      resolveFn({ ok: false, reason: "timeout", at: t });
      return;
    }
    handle = timers.setTimeout(tick, opts.pollMs);
  };
  handle = timers.setTimeout(tick, opts.pollMs);

  return {
    done,
    cancel: (reason = "cancelled") => {
      if (cancelled) return;
      cancelled = true;
      if (handle !== null) timers.clearTimeout(handle);
      resolveFn({ ok: false, reason, at: now() });
    },
  };
}

/**
 * At most one pending wait per action kind. Starting a new wait supersedes the previous one of
 * the same kind; run and submit use different panels, so they don't interfere.
 */
export class ResultTracker<K extends string> {
  private readonly pending = new Map<K, Waiter<unknown>>();

  start<T>(kind: K, begin: () => Waiter<T>): Waiter<T> {
    this.pending.get(kind)?.cancel("superseded");
    const waiter = begin();
    this.pending.set(kind, waiter as Waiter<unknown>);
    void waiter.done.then(() => {
      if (this.pending.get(kind) === (waiter as Waiter<unknown>)) this.pending.delete(kind);
    });
    return waiter;
  }

  cancelAll(): void {
    for (const w of this.pending.values()) w.cancel("cancelled");
    this.pending.clear();
  }
}
