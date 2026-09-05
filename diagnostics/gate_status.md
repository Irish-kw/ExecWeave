# Acceptance gate ledger

Baseline: a098eeb81f641b6e3fb1d65cc1905f46aa8eae30 (v0.8.11).
Only completed checks are PASS. A checkpoint commit does not close a gate.

Current-state re-audit: see `current_state_reaudit.md`. The G2/G3 PASS entries
below are historical scoped checkpoints, not revalidation of the newest head.
G2 is reopened for REAUDIT-001 (unsafe bare-PID cleanup fallback). Formal Windows
G4 executed and FAILED interrupt finalization (REAUDIT-002); required Network
also needs correction (REAUDIT-003). No current full-product PASS is claimed.

| Gate | State | Evidence / remaining work |
|---|---|---|
| G0 baseline and evidence checkpoint | PASS | Native Windows baseline, public PR inventory, audit findings saved; no implementation changes |
| G1 baseline audit report | PASS | Architecture/history, native/browser findings, priorities and design recorded; unexecuted release journeys explicitly remain open |
| G2 minimal defect fixes | PASS | NEW-001/002/003/004/005/006 are verified; the final large-response memory gate is green on Ubuntu, macOS and Windows at exact head `f9edc66` |
| G3 offline acceptance | PASS | Formal `scripts/dashboard_acceptance.py` loopback relay/live/finished journey passes on Ubuntu, macOS and Windows at exact head `0f04fe6`; native/provider-only capabilities remain explicitly outside this gate |
| G4 visible live acceptance | IN_PROGRESS | Formal real-Ollama headed harness exists at `scripts/ollama_visible_acceptance.py`; availability/skip contracts are three-OS CI green at `1c4821e`, but a real local model journey has not yet been executed formally |
| G5 interactive visible and cleanup | IN_PROGRESS | Formal PTY/ConPTY two-round Ollama harness is prepared; real-provider execution is still required before PASS |
| G6 native cross-platform validation | NOT_STARTED | CI/browser/owned-cleanup suites are green on three hosted OSes, but the formal native/provider acceptance matrix is not complete |
| G7 final regression and human review | NOT_STARTED | Draft PR #51 is validation-only; no merge, tag or release permitted |

## Resume protocol

1. Inspect git status/remote branch and this ledger before editing; preserve unrelated changes.
2. Keep unfinished requirements explicit. Unperformed tests must never be described as performed.
3. Commit each completed gate and each independent bug fix separately. Commit messages identify scope, evidence, limitations and the next gate.
4. Save long-running evidence immediately. Large local browser/runtime artifacts remain under `.execweave-acceptance`; do not stage credentials, provider homes, virtual environments or browser binaries.
5. `test/live-dashboard-acceptance` is the implementation branch. `main` remains the v0.8.11 baseline until an explicit later merge decision.

## G4/G5 formal real-provider harness checkpoint

G4 harness implementation head: `1c4821e17edf705593dd1fdd0f7cd51cc954b361`.
All five pull-request workflows completed SUCCESS on that exact head: CI #949, Viewer Agent Isolation #372, Provider Capability Stage Integrity #293, Windows Launcher Compatibility #544, and Provider Dashboard Contract #65. The G4 script owns a fresh loopback Ollama endpoint, launches a real independent `ollama run` client, opens headed Chromium, checks live/finished parity and cleanup, and reports unavailable binaries/models/browser as `SKIP_UNAVAILABLE` rather than PASS. This is harness verification only; no hosted runner result is claimed as a real-provider G4 PASS.

G5 interactive harness is intended to run from `scripts/ollama_interactive_acceptance.py`. POSIX uses a real standard-library PTY. Windows requires pywinpty/ConPTY and refuses ordinary pipes as an interactive substitute. The formal journey sends two prompts in one interactive Ollama session, requires two captured request/response rounds on one `/root`, verifies same-document live update, opens Older history, checks open/closed persistence across live polling and selection switches, interrupts the interactive client through the terminal backend, then checks finished parity, process/network evidence and owned-process cleanup. Missing PTY/ConPTY/model/browser prerequisites remain `SKIP_UNAVAILABLE` unless the provider is explicitly required. This harness must still pass repository CI and then be executed against a real local model before G5 can be PASS.
