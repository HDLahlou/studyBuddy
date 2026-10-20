/**
 * One adapter per platform (docs/design.md "Site adapters"). All platform-specific selectors
 * live in the adapter. Parsing functions take a root node so they can be tested on saved HTML.
 *
 * Differences from the design sketch: `editor()` is replaced by `editorSelector`, because the
 * editor is read by the main-world page probe, which only needs to know where the editor is;
 * `readResult()` is split into run and submit readers, whose panels differ.
 */

import type { ProblemLoadedData, RunResultData, SubmitResultData } from "../generated/contract";

export type RunResult = Omit<RunResultData, "run_id">;
export type SubmitResult = Omit<SubmitResultData, "submit_id">;

export interface ResultReader<T> {
  verdictNode(root: ParentNode): Element | null;
  fingerprint(node: Element): string;
  /** Optional: the panel has finished rendering (e.g. stats shown after the verdict). */
  ready?(node: Element): boolean;
  read(node: Element): T | null;
}

export interface SiteAdapter {
  readonly name: string;
  readonly platform: string;
  readonly version: string;
  matches(url: URL): boolean;
  /** Stable problem key within the platform (the slug), or null if not a problem page. */
  problemKey(url: URL): string | null;
  canonicalUrl(slug: string): string;
  readProblem(root: Document, url: URL): ProblemLoadedData | null;
  /** True when the statement itself was found (not only the title). */
  hasStatement(problem: ProblemLoadedData): boolean;
  /** Editor language as the platform names it, e.g. "python3". */
  readLanguage(root: Document): string | null;
  /** CSS selector of the editor container the page probe should attach to. */
  readonly editorSelector: string;
  /** Classify a click target or key press as run / submit. */
  actionForClick(target: Element): "run" | "submit" | null;
  actionForKey(e: KeyboardEvent): "run" | "submit" | null;
  /** Whether the run and submit buttons exist (Capabilities.run_events). */
  hasRunButtons(root: Document): boolean;
  /** True while a previous run/submit is in progress and the platform ignores new clicks. */
  actionPending(root: Document, action: "run" | "submit"): boolean;
  runResult: ResultReader<RunResult>;
  submitResult: ResultReader<SubmitResult>;
}
