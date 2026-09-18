# Recorded-source navigation and archive-reference verification

Baseline: `a9a4333102065b559dd1197fbbad7787c691b94c`, PR #110.
Scope: content access for W02/W04 and terminal-export verification for W08, not completion of the whole release.

## Recorded-content access

I connected the existing reader to the selected node's explicit content sources. An agent inspector can open directly linked bodies and content from explicitly assigned tasks, tool calls, and model calls without depending on whether an older summary card happened to expose the reference.

- Lookup uses raw node IDs and explicit projection member IDs. Matching names, shared models, parent/child relationships, and nearby timestamps are not identity joins.
- Do not traverse a model resource to every caller or borrow another role's content.
- Distinct calls sharing a body hash retain distinct source entries. Counts describe source references/observations, not delivery, consumption, or successful tasks.
- Display 25 entries initially, with additional batches on demand. Preserve each node's expanded count when switching roles; existing conversation cards and fold policy are unchanged.
- Use the same reader for authentication, hashes, sizes, literal text rendering, and explicit offline-folder selection.
- This is not a complete conversation timeline and does not reconstruct missing provider evidence. Sources absent from the available graph still require further normalization.

## Archive-reference verification

The original required-export check only established the presence of three top-level files. Terminal export now also checks `observed_content` in `graph.json`, including expansion-cluster content nodes, and references declared by `conversations.json`.

- Verify canonical `content/sha256/<hash>.<json|txt|bin>` paths, actual files, full-byte hashes, and recorded sizes.
- Read each duplicate reference once. Conflicting size declarations for one path remain failures even when a later reference is valid.
- Do not parse provider bodies for further filenames or scan arbitrary workspaces. Empty and binary content can pass preservation checks independently of preview support.
- Report invalid JSON, duplicate keys, known session mismatches, missing files, symbolic links/reparse points, non-regular files, changes during reading, and verification limits.
- POSIX uses directory descriptors and `O_NOFOLLOW`. Windows checks reparse points and identity before/after reading. This is not a tamper-proof audit log against an attacker within the same writable trust boundary.
- Default limits are 64 MiB per index, a 1 GiB content-reading budget, and 100,000 references. Reaching a limit produces incomplete status, not skipped work labeled complete. Preserve up to 100 error details plus the total error count and truncation state.
- Source-provided content may be partial while its supplied bytes are fully preserved. Verification is not a claim about provider visibility or end-to-end recall.

`finalization.json` uses schema 0.2, retaining existing fields and adding `artifact_errors` and `content_integrity`. During recording, integrity is `not_checked`; terminal exports cannot be complete when reference verification fails. Write diagnostics before reporting the export failure, and do not replace an existing collector error with the new integrity diagnostic.

The scope is content declared by these two indexes. It does not establish the integrity of every raw event, semantic equivalence with the viewer's embedded data, or resistance to tampering. Other output paths that do not call `record_finalization` do not automatically acquire this verification. Existing archives are not rewritten in the background.

## Initial tests and regression scope

Local results for the source-navigation/integrity batch:

```text
Content integrity and finalization: 61 passed
Source-navigation component: 12 passed (11 Chromium interaction cases)
Total: 73 passed; 1 full-shell integration case not executed locally
Python compilation: PASS
Combined JavaScript syntax: PASS
```

Integrity tests use actual temporary files. Navigation tests execute the component JavaScript and the existing reader to check selection, isolation, batch expansion, and error entry points. Their graphs are synthetic, not fresh provider recordings; HTTP or SHA-256 substitutes are not counted as native transport verification.

Local Chromium policy blocks loopback navigation. These local results therefore do not establish native HTTP/auth behavior. Full Dashboard assembly, the existing suite, three-OS coverage, and installed-package behavior require the corresponding PR workflows. Fresh recordings and independent user acceptance remain outstanding.

The existing finalization regression's successful plain-text `artifact` placeholders were replaced with valid graph/conversation JSON. All original assertions remain. New malformed-JSON negative cases prevent arbitrary nonempty files from satisfying reference verification.

## Integration and rollback

Navigation adds one shared component and an explicit reader `attach` interface without changing ownership inference, raw events, graph layout, or recorders.

Archive checks are confined to `content_integrity.py` and `finalization.py`. They do not rewrite source artifacts or bump the version. Navigation and terminal verification can be reverted separately if a regression requires it; deleting failing tests or relaxing incomplete-archive classification is not a rollback strategy.

## Cross-platform follow-up

Linux/macOS provider contracts and the 13 provider-specific contracts passed for `b0ccc42`, but Windows Live/top terminal export failed. The implementation compared the complete `os.fstat` signature directly with `Path.stat`, mixing Windows metadata interfaces.

I changed the path-side check to reopen the inspected path and obtain `os.fstat` metadata through the same interface. Identity, size, mtime, and ctime checks remain exact, without timestamp rounding or a Windows bypass. Any one-unit change in a checked field remains a failure. Additional handles close on errors as well. Native confirmation requires the subsequent commit's Windows checks.

Stage Integrity also rejected the undocumented migration of the successful fixture to valid JSON. Its existing exception mechanism now names only `tests/test_audit_closure_20260917.py` on this branch and pins its complete blob hash. Unexpected changes still fail. Historical test names and all assertions remain intact.

The follow-up targeted local result was **82 passed, 1 deselected**, including nine new portability/handle-lifecycle cases. The unexecuted case was the full Dashboard shell integration test; these local results are not Windows, full installed-package, or fresh-provider acceptance.

## Platform security-test follow-up

`5e81d3a` removes new skip markers. Symlink-fixture setup failures now fail explicitly. POSIX exercises a real FIFO path; Windows exercises a real directory at a content path. An additional native pipe-handle rejection case runs on every platform. Product behavior and Stage Integrity are not relaxed.

The targeted local result at this point was **83 passed, 1 deselected**. These are historical results tied to that batch, not an assertion that all later heads pass the complete suite.

## Framework task-navigation contract follow-up

The full Ubuntu/Python 3.12 suite at `5e81d3a` reported **1 failed, 1,905 passed, 5 skipped**. The failure was the existing OpenCode delegation test: the new shared navigation script contained `ASSIGNED_AGENT_TASK` even when the graph contained no such assignment. That HTML assertion alone does not prove that a runtime edge was fabricated. Inspecting the mapping exposed a separate contract error: the navigator accepted this provider-delegation relation for ordinary framework `task` nodes, although the framework adapter emits `task -> ASSIGNED_TO -> agent`.

I narrowed the reverse task join to that canonical relation and its endpoint types. Inferred and viewer-only assignment edges are not used as raw assignment evidence. Provider subtask/tool-call delegation stays with its existing identity policy; direct source inspection remains available. This removes an unsupported mapping rather than hiding a string or changing the historical assertion.

Validation used the complete production modules from the exact-head CI package artifact, with the existing delegation test fetched separately and verified byte-for-byte against Git blob `56acc16be36d8d3fdd2d6bf4eac687307bb7d3a5`. The artifact's recorded source is the PR merge ref `d68636af32a4af9b2ed6a9e1331b19209ded1d8e`; the checked source tree is `40101b2319cea5b62d997795691e7c244c5d1747`.

```sh
PYTHONPATH=src EXECWEAVE_E2E_CHROMIUM=/usr/bin/chromium python -m pytest -q \
  tests/test_delegation_viewer.py tests/test_recorded_source_task_contract.py
```

- Before the correction: **9 failed, 14 passed** (one historical HTML regression and eight new contract failures).
- After the correction: **23 passed**, including the three unchanged historical tests and 20 new Chromium contract/interaction cases.
- A positive test obtains assignment evidence from the real CAMEL adapter API and graph accumulator, without starting CAMEL or a model provider. Negative cases cover unsupported relations, wrong endpoint types/direction, inferred/view-only assignments, same-named agents, and direct inspection of otherwise unassigned task content.
- Live, Static, and projected-static Dashboard scripts pass `node --check`, and each includes exactly one source navigator and content reader.
- Ruff passed for the changed production module and new test file. Local execution used Linux/Python 3.13.5 and Chromium; it is not a replacement for the required Python 3.10/3.12 OS matrix.

These browser tests use real component JavaScript and DOM behavior with synthetic data; they do not claim fresh provider capture, native HTTP/auth validation, or a rerun of the full 1,900-plus-test suite. The original delegation tests, recorders, source events, and version metadata remain unchanged. This follow-up also converts the improvement plan and this record to English without rewriting Git history.
