/**
 * Editor-scoped key categories and burst aggregation. Never stores characters: only the
 * category of each key press is kept, and a burst reports counts per category.
 */

import type { KeyCounts } from "../generated/contract";
import type { EpochMs } from "../shared/clock";
import { realTimers, type Timers } from "../shared/timers";

export type KeyCategory = keyof Required<KeyCounts>;

export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

const NAVIGATION = new Set([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
  "PageUp",
  "PageDown",
]);
const IGNORED = new Set(["Shift", "Control", "Alt", "Meta", "CapsLock", "Escape", "Dead", "Unidentified"]);

export function categorize(e: KeyLike): KeyCategory | null {
  if (IGNORED.has(e.key)) return null;
  if (e.ctrlKey || e.metaKey) return "shortcut";
  // Alt + a printable key types a character on macOS; Alt + a named key is an editor command.
  if (e.altKey && e.key.length > 1) return "shortcut";
  if (e.key === "Backspace" || e.key === "Delete") return "delete";
  if (e.key === "Enter") return "newline";
  if (NAVIGATION.has(e.key)) return "navigation";
  if (e.key === "Tab" || e.key.length === 1) return "insert";
  return null;
}

/** Ctrl/Cmd+Z without Shift. Redo (Shift+Z, Ctrl+Y) is only a shortcut. */
export function isUndo(e: KeyLike & { shiftKey: boolean }): boolean {
  return (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z";
}

export interface Burst {
  at: EpochMs;
  durationS: number;
  counts: KeyCounts;
}

/**
 * Groups key presses into bursts. A burst ends after `quietMs` without keys, or when it has
 * lasted `maxMs`, or on `flush()` (stop, run/submit). `at` is the burst start (E5).
 */
export class BurstAggregator {
  private start: EpochMs | null = null;
  private last: EpochMs = 0;
  private counts: Required<KeyCounts> = { insert: 0, delete: 0, newline: 0, navigation: 0, shortcut: 0 };
  private timer: unknown = null;

  constructor(
    private readonly onBurst: (b: Burst) => void,
    private readonly opts: { quietMs: number; maxMs: number } = { quietMs: 1000, maxMs: 30_000 },
    private readonly timers: Timers = realTimers,
  ) {}

  add(category: KeyCategory, at: EpochMs): void {
    if (this.start !== null && at - this.start >= this.opts.maxMs) this.flush();
    if (this.start === null) this.start = at;
    this.last = at;
    this.counts[category] += 1;
    if (this.timer !== null) this.timers.clearTimeout(this.timer);
    this.timer = this.timers.setTimeout(() => this.flush(), this.opts.quietMs);
  }

  flush(): void {
    if (this.timer !== null) {
      this.timers.clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.start === null) return;
    const counts: KeyCounts = {};
    for (const [k, v] of Object.entries(this.counts) as Array<[KeyCategory, number]>) if (v > 0) counts[k] = v;
    const burst = { at: this.start, durationS: Math.round(this.last - this.start) / 1000, counts };
    this.start = null;
    this.counts = { insert: 0, delete: 0, newline: 0, navigation: 0, shortcut: 0 };
    this.onBurst(burst);
  }
}

/** Size of pasted text; the text itself is never kept. */
export function pasteSize(text: string): { chars: number; lines: number } {
  if (text.length === 0) return { chars: 0, lines: 0 };
  return { chars: text.length, lines: text.split(/\r\n|\r|\n/).length };
}
