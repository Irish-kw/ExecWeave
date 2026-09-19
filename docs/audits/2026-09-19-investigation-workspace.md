# Investigation workspace: roles, handoffs, calls, and file evidence

Baseline: `6bd573127f7ff1d11ae20f649e361ae978a45fb4`, PR #110.

## What is now directly inspectable

I added **Explore run**, a searchable workspace with four categories: Agents,
Handoffs, Model / tool calls, and Files / artifacts. Role discovery no longer
requires navigating the canvas. An exact agent can open the existing inspector
or filter its handoffs and calls. The graph, recorder, and raw identity policy
are unchanged.

Messages retain native message IDs, participants, send/receipt observations,
source event IDs, timestamps, and recorded body references. A send to a different
recipient is not paired with another recipient's receipt. Equal text does not
merge different messages. Exact replay of an event is deduplicated; contradictory
reuse of an event ID is withheld and counted. Receipt is not consumption,
comprehension, or task success.

Framework model/tool observations retain request, response, and failure phases
using canonical occurrence IDs. Native graph call IDs supplement that inventory,
with content links and uniquely supported ownership only. A lone root, common
model, or matching name is not an ownership fallback. An ambiguous or missing
owner stays unknown. Native graph rows can represent separate observation points
for one unresolved underlying inference; the UI counts indexed records, not an
asserted total of unique real-world invocations.

File rows expose known snapshot references, hashes, observation times, and direct
recorded relationships. Only the explicit before-read file-content contract is
classified as a file snapshot. Other associated content remains readable but is
not promoted to file bytes, a producer, or a consumer. A filename without a
snapshot is labeled as such; the current workspace file is never substituted.

All registered body references reuse the existing authenticated/selected-folder
content reader. Every offered reference must also exist in the graph's content
inventory with matching size/hash metadata, so the feature cannot create a
second class of references outside archive verification.

## Evidence scope and safety

The event index currently recognizes canonical CAMEL, AutoGen, and MetaGPT SDK
records. Native provider calls are included when explicit call nodes/content
edges exist. Other native message formats are not reconstructed from aggregated
edges or prose; existing observed history and source inspectors remain available.

Only fixed recorded stream names within the supplied run folder are eligible.
The implementation does not read paths inside provider bodies, workspace files,
or external URLs. Symlinks/reparse points, non-regular files, conflicting scope,
malformed JSON, and changing files do not become accepted event evidence.
This is a local evidence reader, not protection against an adversary who controls
the entire writable archive and its claims.

Inspection is bounded to 100,000 events, 10,000 canonical observations, 32 MiB of
stream bytes, 1 MiB per line, and 100,000 graph records. Graph-derived output is
bounded to 10,000 roles/calls/files and 50 content links per graph record.
Budget exhaustion and omitted rows are explicit. Index metadata and bodies have
separate availability/verification states. A recorded reference is not a verified
body; an unobserved receipt is not a proven delivery failure.

The workspace renders 25 rows per page and expands details lazily. Open rows are
retained across pagination in bounded run-local memory. New index responses do
not replace the open snapshot; explicit refresh is required. Scope changes close
and clear old results. Labels render literally and no message bodies or search
terms are written to browser storage.

## Publication and performance boundary

The index is additive to `conversations.json` and embedded beside the raw graph
in standalone pages. It does not modify graph nodes/edges or raw graph metadata.
Live inspection uses the existing authenticated endpoint with an explicit
`investigation=1` request. Ordinary history polling does not scan event streams.
Final export materializes the index once per export path; an unchanged stream
snapshot can be reused through a bounded per-Live-state cache. Cache key/value
publication is atomic so concurrent readers cannot mix a new scope with an old
snapshot. This is not completion of all large-run memory/latency acceptance.

## Compatibility regressions addressed

The baseline full Ubuntu/Python 3.12 CI reported 2 failures, 2,143 passes, and
5 skips. The failures were existing inspector/export source contracts, not a
successful full-suite verdict. I retained those tests and corrected the shared
integration: secondary surfaces access the one inspector instance through the
Dashboard host, while the existing public export remains. HTTP success, status,
scope, and publication success remain separate final-synchronization checks.

The new filter-reset action is labeled **Clear agent filter** rather than the
retired rooted-tree control's misleading label. It does not resurrect the old
whole-conversation tree.

## Verification and limitations

Source was reconstructed from the exact-head full Git bundle artifact
`10557868315`, SHA-256
`115f7e5650dec98605c8d894ce0a6230475c67798758056ef0221b96745c43b0`,
whose tree is `93580667ed0adc6f4d55e70a64069dad28cd7522`.
Unlike the earlier wheel-only source, this includes the complete historical test
suite. No existing test, dependency, workflow, version, or release metadata is
changed in this work.

The new tests exercise actual Chromium DOM interactions, exact SDK records,
four runtime content normalizers, live HTTP authentication, request-on-demand
behavior, record/call isolation, strict reference handling, pagination, and
source budgets. The real portable workload test exits 3 and exports an
inspectable send/receipt exchange while preserving failed execution and a
complete declared-content archive. This invokes the real recorder and SDK, not
a paid model or a fresh upstream framework deployment.

Local verification results are recorded with the final tested tree in the PR.
A medium synthetic inventory reports time and encoded size; it is not the
planned product p95 benchmark. Browser document tests are not automatically
native HTTP/file-navigation acceptance. Python 3.10/3.12 and Windows/macOS/Linux
CI must be checked on the new remote head.

## Change impact and rollback

| Area | Preservation boundary |
|---|---|
| `investigation_index.py` | Read-only native event/graph metadata; no body parsing, workspace reads, speculative ownership, or delivery inference. |
| Conversation payload and Live handler | Additive opt-in data on the existing authenticated route; ordinary polling keeps its previous file-read behavior. |
| Static projection/bootstrap | Same renderer and raw graph; embed the same index written to the archive, not a separate UI-only reconstruction. |
| Shared inspector/synchronizer | One inspector instance, original public methods, strict response/scope checks, and no additional polling loop. |
| Workspace | Independent role lookup, bounded lazy DOM, safe text, scope clearing, and the existing verified-body reader. |

The workspace and its publication hooks can be reverted together. Retain the
independent inspector/synchronization compatibility fixes. Do not restore
speculative graph joins or weaken the original tests to resolve regressions.

Full-plan gaps remain: independent task-validation evidence, full native message
coverage, automatic workflow-first canvas layout, cross-provider completeness
contracts, artifact capture policies, large-run acceptance, safe sharing, and
fresh-provider/user acceptance. This commit does not mark those gates complete.
