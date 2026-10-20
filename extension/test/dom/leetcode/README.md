# LeetCode DOM fragments

These are reduced copies of leetcode.com markup, captured on 2026-10-19 in Chrome (Two Sum and Valid Parentheses), and used by `test/leetcode.test.ts`.

What was kept:

- Element nesting.
- `data-e2e-locator`, `data-track-load` and `data-layout-path` attributes.
- The Tailwind class tokens the adapter reads (`text-*`, `font-menlo`, `cursor-pointer`, `bg-fill-3`, `flexlayout__*`).

What was changed or removed:

- SVG paths, images and other attributes were dropped.
- Statement prose is paraphrased.
- The account handle is replaced with `USER`.

Sources:

| File | Source |
| --- | --- |
| `problem.html` | Description tab of `/problems/two-sum/` |
| `run-wrong-answer.html` | Run result for a C++ solution returning `{0, 0}` |
| `run-accepted.html` | Run result for a correct C++ solution |
| `run-compile-error.html` | Compile Error run result |
| `run-runtime-error.html` | Runtime Error run result (Java, two-sum). The "Last Executed Input" label also contains an "Open Testcase" link, so it isn't a leaf element. |
| `submit-accepted.html` | Fresh Accepted submission on Valid Parentheses (Java), captured 2026-10-19. |
| `submit-wrong-answer.html` | Fresh Wrong Answer submission on Valid Parentheses (`return s.length() % 2 == 0;`). Failed submissions have no `data-e2e-locator`; the verdict is an `<h3>`. Also includes the verdict-named tab title (`/ts0/tb1`), which must not be mistaken for the result. |

When LeetCode changes its markup, recapture these files, update the adapter, and bump `ADAPTER_VERSION`.
