# Acceptance gate ledger

Baseline: a098eeb81f641b6e3fb1d65cc1905f46aa8eae30 (v0.8.11).
Only completed checks are PASS. A checkpoint commit does not close a gate.

Latest source/offline re-audit: `acceptance_hardening_20260906.md`. This supersedes
stale present-tense G4/G5 statements below without promoting native gates. Two-round
identity binding and required terminal round-trip are already implemented. Original
Windows clean-2f93d629 evidence includes a revised G4 server-exit PASS and a G5
Ctrl+C/exit-contract FAIL; neither establishes a current-head full native PASS.

Current-state re-audit: see `current_state_reaudit.md`. REAUDIT-001 cleanup identity
safety has been re-exercised by the formal owned-process cleanup on all three hosted
OSes at exact head `1a53b87`; the large-response memory gate remains green from its
three-OS checkpoint at `f9edc66`. REAUDIT-002/003 have source-level G4 corrections,
but the corrected real local-model G4 journey has not yet been formally rerun. No
current full-product PASS is claimed.

| Gate | State | Evidence / remaining work |
|---|---|---|
| G0 baseline and evidence checkpoint | PASS | Native Windows baseline, public PR inventory, audit findings saved; no implementation changes |
| G1 baseline audit report | PASS | Architecture/history, native/browser findings, priorities and design recorded; unexecuted release journeys explicitly remain open |
| G2 minimal defect fixes | PASS | NEW-001/002/003/004/005/006 are verified; the final large-response memory gate is green on Ubuntu, macOS and Windows at exact head `f9edc66`, and identity-aware owned cleanup is current-head green at `1a53b87` |
| G3 offline acceptance | PASS | Formal `scripts/dashboard_acceptance.py` loopback relay/live/finished journey is current-head green on Ubuntu, macOS and Windows at `1a53b87`; native/provider-only capabilities remain explicitly outside this gate |
| G4 visible live acceptance | IN_PROGRESS | Prior clean-2f93d629 revised server-exit journey passed, but collector Ctrl+C is not proved. Strict client Final comparison (1c3cb1e) and redacted live output (38397a1) have source/offline fixes; current-head real journey NEEDS_NATIVE_VALIDATION |
| G5 interactive visible and cleanup | IN_PROGRESS | Marker-bound distinct exchanges, actual terminal round-trip, Ctrl+C then /bye wrapper and redacted visible transcript implemented. Prior real run failed the old exit contract; corrected current-head two-round/fold/finished/cleanup journey NEEDS_NATIVE_VALIDATION |
| G6 native cross-platform validation | IN_PROGRESS | Native OS-only Process/File/Network subgate is PASS on Ubuntu, macOS and Windows at exact head `1a53b87` with real pointer interaction; provider-native acceptance scope remains incomplete |
| G7 final regression and human review | NOT_STARTED | Draft PR #51 is validation-only; no merge, tag or release permitted |

## Resume protocol

1. Inspect git status/remote branch and this ledger before editing; preserve unrelated changes.
2. Keep unfinished requirements explicit. Unperformed tests must never be described as performed.
3. Commit each completed gate and each independent bug fix separately. Commit messages identify scope, evidence, limitations and the next gate.
4. Save long-running evidence immediately. Large local browser/runtime artifacts remain under `.execweave-acceptance`; do not stage credentials, provider homes, virtual environments or browser binaries.
5. `test/live-dashboard-acceptance` is the implementation branch. `main` remains the v0.8.11 baseline until an explicit later merge decision.

## Current three-OS dashboard/native checkpoint

Exact implementation head: `1a53b87e8be339d34162d10106c549a56ecb89b0`.
All five pull-request workflow families completed SUCCESS on this exact head:

- CI #968 / run `33982695918`
- Viewer Agent Isolation #410 / run `33982695924`
- Provider Capability Stage Integrity #312 / run `33982695913`
- Windows Launcher Compatibility #563 / run `33982695912`
- Provider Dashboard Contract #84 / run `33982695909`

Viewer runs on Ubuntu, macOS and Windows all completed the browser selection, formal
offline acceptance and formal owned-process cleanup successfully. The current browser
selection includes the camera scheduler regression and the node-click/drag camera
ownership regression. Native plain-Python OS acceptance completed successfully on all
three hosted OSes, proving actual Process/File/Network observation plus natural pointer
selection in both live and finished dashboards while requiring provider Prompt/Final/
Tool semantics to remain absent.

The Windows defect fixed by `1a53b87` was a cross-platform interaction race: node
`pointerdown` took camera ownership and stopped an in-flight Fit before a click had
become a drag. On faster native-delta timing this could freeze a Network endpoint under
the inspector. A plain node inspection click now leaves Fit active; only motion beyond
the existing drag threshold switches to Manual and moves the node. This checkpoint
closes the native OS-only interaction subgate, not the remaining real-provider matrix.

## G4/G5 formal real-provider harness checkpoint

G4 harness implementation head: `1c4821e17edf705593dd1fdd0f7cd51cc954b361`.
All five pull-request workflows completed SUCCESS on that exact head: CI #949, Viewer Agent Isolation #372, Provider Capability Stage Integrity #293, Windows Launcher Compatibility #544, and Provider Dashboard Contract #65. The G4 script owns a fresh loopback Ollama endpoint, launches a real independent `ollama run` client, opens headed Chromium, checks live/finished parity and cleanup, and reports unavailable binaries/models/browser as `SKIP_UNAVAILABLE` rather than PASS. This is harness verification only; no hosted runner result is claimed as a real-provider G4 PASS.

G5 interactive harness is intended to run from `scripts/ollama_interactive_acceptance.py`. POSIX uses a real standard-library PTY. Windows requires pywinpty/ConPTY and refuses ordinary pipes as an interactive substitute. The formal journey sends two prompts in one interactive Ollama session, requires two captured request/response rounds on one `/root`, verifies same-document live update, opens Older history, checks open/closed persistence across live polling and selection switches, interrupts the interactive client through the terminal backend, then checks finished parity, process/network evidence and owned-process cleanup. Missing PTY/ConPTY/model/browser prerequisites remain `SKIP_UNAVAILABLE` unless the provider is explicitly required. This harness must still pass repository CI and then be executed against a real local model before G5 can be PASS.
