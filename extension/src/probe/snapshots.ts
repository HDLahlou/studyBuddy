/**
 * When to take code snapshots (docs/design.md "What it captures"):
 *  - debounce: after `debounceMs` of quiet following a change;
 *  - periodic: every `periodicMs`, only if the text changed since the last snapshot (E3);
 *  - forced: on run/submit and at start, always, even if unchanged.
 */

import type { CodeSnapshotData } from "../generated/contract";
import type { EpochMs } from "../shared/clock";
import { type IntervalTimers, realTimers } from "../shared/timers";

export type SnapshotReason = CodeSnapshotData["reason"];

export interface Snapshot {
  code: string;
  reason: SnapshotReason;
  at: EpochMs;
}

export class SnapshotScheduler {
  private last: string | null = null;
  private debounce: unknown = null;
  private periodic: unknown = null;

  constructor(
    private readonly getValue: () => string,
    private readonly emit: (s: Snapshot) => void,
    private readonly now: () => EpochMs,
    private readonly opts: { debounceMs: number; periodicMs: number } = { debounceMs: 500, periodicMs: 15_000 },
    private readonly timers: IntervalTimers = realTimers,
  ) {}

  start(): void {
    this.force("initial");
    this.periodic = this.timers.setInterval(() => this.emitIfChanged("periodic"), this.opts.periodicMs);
  }

  onChange(): void {
    if (this.debounce !== null) this.timers.clearTimeout(this.debounce);
    this.debounce = this.timers.setTimeout(() => {
      this.debounce = null;
      this.emitIfChanged("debounce");
    }, this.opts.debounceMs);
  }

  force(reason: SnapshotReason): void {
    if (this.debounce !== null) {
      this.timers.clearTimeout(this.debounce);
      this.debounce = null;
    }
    this.take(reason);
  }

  stop(): void {
    if (this.debounce !== null) this.timers.clearTimeout(this.debounce);
    if (this.periodic !== null) this.timers.clearInterval(this.periodic);
    this.debounce = this.periodic = null;
  }

  private emitIfChanged(reason: SnapshotReason): void {
    if (this.getValue() !== this.last) this.take(reason);
  }

  private take(reason: SnapshotReason): void {
    const code = this.getValue();
    this.last = code;
    this.emit({ code, reason, at: this.now() });
  }
}
