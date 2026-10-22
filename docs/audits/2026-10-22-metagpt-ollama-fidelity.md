# MetaGPT/Ollama fidelity audit — 2026-10-22

Base ExecWeave: `ad476e1f1399574c987f8fc144ef729c866363ee` (v0.8.39).
Branch: `fix/metagpt-ollama-request-fidelity`. No release/version change.

## Source and environment

- Windows 10 API build 26200, AMD64; Python 3.11.16.
- Actual installed MetaGPT distribution: 1.0.0, imported from the existing
  `metagpt-minimal-runtime` Conda environment. An isolated project venv uses its
  installed packages and adds ExecWeave development dependencies.
- The installation's `direct_url.json` refers to a local source directory which
  no longer exists. A source Git SHA cannot be recovered; the installed version
  and byte hashes below are the authoritative identifiers, not latest upstream.
- `base_llm.py` SHA-256:
  `eadb2ec250316c88017cee64f4db4e56cc3f374b8421909274ce7ff6fd7a8276`.
- `ollama_api.py` SHA-256:
  `4f1706c30303a509ac838c221cb446eca641c6fff1af69a3ed48ab17c1d77ba9`.
- Genuine local Ollama 0.24.0 at `127.0.0.1:12345`, model `llama3.1:8b`,
  model ID prefix `46e0c10c039e` (4.9 GB). No cloud model was used.
- Fresh clone/fetch; clean main before changes. No open PRs at inspection time.
  Existing integration PRs #87/#92/#94/#108 were inspected for context; none
  provides this three-boundary capture. No unrelated checkout was modified.

## Independently observed original defects

| Issue | Source/function and root cause | Reproducer and observed/expected result | Ownership |
|---|---|---|---|
| A | acceptance `ObservedOllamaLLM.aask` logs only supplied system arguments; `BaseLLM.aask` supplies defaults later | `use_system_prompt=True`, no `system_msgs`: old record has none, processed input has default. Expected separate caller/processed evidence | acceptance wrapper |
| B | `OllamaLLM.__init__` disables system generation; `BaseLLM.aask` later appends `format_msgs`/caller lists | explicit BRAVO is absent on wire; injected DELTA survives construction then is relabeled user by adapter. Expected no blanket claim that all system inputs are transmitted or absent | upstream behavior plus wrapper semantics |
| C/D | `OllamaMessageChat.apply` reads only first content and reconstructs user messages | three turns -> one user turn; enabled default -> only default text as user, actual user question dropped. Expected recorder to expose actual payload; preserving history requires explicit correction | upstream adapter; recorder previously missed it |
| E | only logical `aask` was observed; retry count inferred after terminal error | one logical call can have two real transmissions; recovered parser retry was not reported. Expected distinct call/attempt identities and actual retry callbacks | acceptance instrumentation |
| F | proposed shared `_pending` is unsafe, but **does not exist in baseline** | original code has no concurrent pending-state defect to reproduce. New overlapping same-instance calls are tested with per-call ContextVar attribution; direct/batch completion was previously unobserved | design risk and missing coverage, not fabricated baseline finding |
| G | payload takes `config.stream` and hard-coded temperature 0.3; abstraction independently takes call stream | config true/call false produces NDJSON decode failure; config false/call true can return provider dict from stream path. Expected capture of both flags/options, not invented normalization | upstream behavior; wrapper omitted effective transport |

Baseline evidence: original ActionNode task completed once (18 semantic events,
1 logical request/response). Six additional real proxy probes confirmed normal,
multi-turn loss, explicit suppression, enabled default/explicit prompt relabeling,
and independently injected system content. Success of the baseline task was not
used as proof of prompt correctness.

## Implementation

- `metagpt_recording.py`: per-instance requestor/session wrapping captures the
  serialized body immediately at HTTP request; per-call ContextVar identities;
  separate processed/transport content events; direct completion coverage;
  explicit pre-transport, attempted, response-received and failure outcomes;
  actual ActionNode retry callbacks, including recovered retries.
- `metagpt_ollama_compat.py`: opt-in chat history/role/base64-image conversion,
  isolated from recording. Instance activation is recorded explicitly.
- `real_metagpt_acceptance.py`: reuse mixin; additive CLI flag and summary counts;
  installed framework version; no implied independent verification in its summary.
- `verify_metagpt_ollama_fidelity.py`: independent HTTP proxy, assertions over
  exact JSON and content SHA-256, genuine-model and labeled fault scenarios.
- New deterministic SDK tests and [operator contract](../metagpt-ollama-fidelity.md).

## Executed validation and limits

Development run `fidelity-v3`: 21 scenarios, 27 observed HTTP requests, of which
26 reached genuine Ollama and one image-transform request received a mock
response. All recorded request JSON matched independent proxy JSON, including
roles, order, contents, stream, model, options and all fields. Two normal
ActionNode tasks succeeded; a controlled malformed-output scenario exhausted
two attempts as expected; a recovered scenario succeeded on attempt two.
Actual 404 and stream-mismatch failure are intentional negative cases, not
claimed model successes. Transport retry injects built-in `ConnectionError`
after a real response, because installed MetaGPT does not retry every translated
network exception. See the operator contract for exact scope.

87 focused SDK/framework regression tests passed. Whole-repository Ruff passed.
Static dashboard materialization of both ActionNode sidecars passed, including
live/finished semantic identity parity and existing conversation references.
Those static runs used the existing synthetic process anchor; they are not
claims of native OS tracing or browser interaction.

One earlier recovered-retry probe failed because its abbreviated prompt produced
the JSON string `"OK"` instead of the required object. The failure was retained
locally as `fidelity-v2`; the corrected test uses ActionNode's native compiled
structured prompt. No successful request or count was fabricated. Initial
regression collection lacked watchdog and was rerun after installing declared
project dependencies. Initial stage-integrity execution encountered Windows
cp950 decoding errors; rerun uses `PYTHONUTF8=1`, without editing the guard.

The committed machine-readable evidence and final CI results accompany the PR.
Acceptance requires G1–G10 and exact-head CI; pending/blocked checks do not
authorize a merge. This document does not claim the unmodified upstream adapter
preserves history, cloud/vision inference works, or local logs resist tampering.
