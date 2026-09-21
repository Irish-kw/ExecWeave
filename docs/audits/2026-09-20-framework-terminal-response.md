# Framework terminal-response interpretation

Baseline: `a5740b2734a7f2bd1c1a7e8e2cb0d71b09843e6a` (PR #110).
This is a narrow reading improvement, not completion of #75 or buyer acceptance.

## Problem and change

The frozen #83 buyer report identified AutoGen `TERMINATE` and CAMEL
`<CAMEL_TASK_DONE>` as the only text in some response summaries. I retained the
original reported response and added a separate interpretation card for an exact
terminal-text match. When an earlier eligible outgoing message is present in the
same displayed round window, its preview is shown under **Earlier observed
message**. It is not relabeled as a final answer, successful task, or deliverable.
The existing observed-history browser retains the complete published sequence.

The addition is restricted to explicit framework-agent sources (AutoGen, CAMEL,
or MetaGPT). The raw source ID must be unique; exact-source conversation records
must agree on the selected path and cannot carry conflicting native identities.
A legacy name/path fallback is not sufficient. The terminal and earlier records
must name the selected sender and use a supported outgoing-message kind. Inbound,
request, assignment, candidate, encrypted and injected-context records are not
substitutes. Generic assistant records can be repeated model-request context and
are deliberately excluded from the earlier-message excerpt.

Quoted/embedded/lower-case marker text and truncated terminal records are not
classified. A terminal text match is explicitly not a claim about a framework's
protocol state. When no earlier eligible message exists in this window, the note
says so rather than borrowing another source. Existing preview limits apply;
this does not retrieve additional bytes or fill missing history. Earlier message
content uses the existing plain-text card renderer, including HTML escaping.

The original Task/Thinking/Response selection and source text are unchanged. The
new cards are presentation-only; they do not change task verification, source
identity, raw graph data, content hashes or recorded message order.

## Scope and rollback

Three files: one shared child-policy module, one new test module, this record.
The policy keeps its existing assignment grouping and response selection; only
explicit framework terminal reports receive additional cards. Other provider
panels are unchanged. Revert this commit to remove the annotation independently
of model/message navigation and Offline readers.

No recorder, parser, endpoint, authentication, polling, layout, dependency,
workflow, version, or historical test changes are included. No new body fetching,
cache, browser persistence, or source-discovery capability is added.

## Executed checks

The source was reconstructed from the mounted 6a144b3 Actions bundle plus the
5523110, d20182b, 0ad6283 and a5740b2 validated patches. Before editing, the complete
Git tree matched `32742ef051e431dfd09bb1c90e60088e90a08d3b`.
Local runtime: Linux, Python 3.13.5, system Chromium/Playwright, Node 22.16.0.

- Three identical positive-path cases on the baseline: **3 failed**, because the
  earlier-message/interpretation cards did not exist.
- Final new module (22 cases), existing framework-conversation and privacy tests:
  **28 passed**.
- Unchanged model-output panel/refresh and Codex/AGY child-policy tests:
  **35 passed**.
- Unchanged observed-history marker/exclusion cases: **9 passed**;
  34 unrelated cases deselected in that command.
- The final groups contain **72 distinct passing checks**, not including the
  baseline failures or earlier repeated runs.
- Ruff, diff whitespace and assembled Live/static JavaScript syntax: **PASS**.
  The existing Ruff wheel was installed from a mounted CI artifact; no repository
  dependency was changed.

The initial implementation looked only at `provider`, while the real SDK source
in these fixtures publishes `framework`. That candidate had 4 failed/16 passed;
the production gate was corrected to use the explicit framework field. The new
fixture and assertions were not changed to conceal that failure. A redundant
helper self-check was removed before the first baseline comparison. Historical
tests remain unchanged.

These fixtures use real SDK event recording, content storage and index generation
with synthetic messages, rendered by the shipped Dashboard in Chromium. Negative
cases also edit copies of the normalized metadata. They are not an original R1/R2
replay or fresh model run. The screenshots are synthetic inspection evidence.
The earlier-message excerpt does not claim hash-verified plaintext.

The unchanged native relocated intact-body test was attempted first and failed at
`file:` navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`. That blocked run is not a
pass. Native Offline, current-head three-OS/full CI, original R1/R2 replay and
independent buyer acceptance remain separate requirements. No security policy was
bypassed and no native test was skipped in repository configuration.
