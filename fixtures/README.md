# Fixtures

Sample session bundles. Every pipeline stage is tested by replaying these, without a browser.
Add one fixture per new bug class (seq gaps, missing audio, failed result scrape, repeat problem).
When `schema_version` changes, update every fixture in the same change.

## `two_sum_basic/`

A clean ~3-minute LeetCode "Two Sum" session in Python 3, practice mode. 41 events in total.

- `events.jsonl` has 31 captured events (seq 1–31): problem load, code snapshots (initial, debounce, periodic, run, submit), keystroke bursts, a paste, an undo, a tab away and back, a failed run (Wrong Answer on `[3,2,4]`, output `[0,0]`, because the code inserts into `seen` before checking), a passing run and an accepted submit.
- `derived/transcript.jsonl` has 9 `speech` segments and 1 `marker` (`stuck`, origin `speech`). **These are hand-written**: they stand in for what the transcription stage will produce. The audio itself is silence.
- `media/audio/` has 18 chunks of silent WebM/Opus in 10 s timeslices, starting 0.35 s after `session_start`. They're regenerated with `make fixtures-audio`, which needs ffmpeg. Joining the chunks in order gives a valid file.
- `manifest.json` contains the `end` info (final seq 31, final audio chunk 17), so the bundle is complete.

## `two_sum_seq_gap/`

The same session with transport faults:

- **Lost events:** seqs 18–20 are missing. They were lost from the extension's buffer, so they were never received.
- **Replayed events:** after a reconnect, seqs 21 and 22 were sent again. They're identical, so they're dropped as duplicates.
- **Resulting state:** `end` arrived with `final_seq` 31, but the bundle is incomplete because of the gap. Audio and video are off.

## `two_sum_live_order/`

The `two_sum_basic` session, renumbered the way the real extension numbers events: in **arrival** order. Keystroke bursts are stored about 1 s after their last key, and results after their panel settles, so `seq` isn't in time order (6 inversions). Use `Bundle.timeline()` to order by time. There's no audio and there are no derived files.

## `two_sum_failed_scrape/`

The same session, in arrival order, except that the first run's result never settled. It's recorded at the 30 s timeout with `verdict: "unknown"` and `confidence: 0` (bug class "failed result scrape").

`tools/make_variant_fixtures.py` generates both variants from `two_sum_basic`.

## `tools/`

- `make_silent_audio.py` writes silent audio chunks into a bundle through `BundleWriter`.
- `make_variant_fixtures.py` regenerates `two_sum_live_order` and `two_sum_failed_scrape`.
