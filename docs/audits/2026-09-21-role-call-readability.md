# Three bounded improvements: roles, invocation evidence, and verified reads

Baseline: `792dcbd5b88caf694561f2a588a31a6e0b91c6bd`, tree
`a2108728030d5c523bd26707a1f0d1f1f4250ecc`, PR #110. This is an
implementation record, not a release or a claim that three entire work packages
are complete.

## 1. Distinguish reference registration from actual verified reading

The shared body reader keeps a private, bounded in-memory ledger of its latest
read outcomes. It records only run-scoped file identity, size, state, verified
byte count and whether UTF-8 text was readable. It does not retain body text in
this ledger, persist it to browser storage, or change an archive. Pending reads,
errors and cancellation cannot preserve a successful latest-read count.

Content health now snapshots that ledger alongside its existing index summary.
`unique-indexed-files-v1` counts unique consistent indexed path/hash/size
references, not invocations or provider activity. Repeated references share one
byte count. An outcome must match the current run/session/source scope and current
graph declarations. Conflicting declarations and ambiguous outcomes cannot turn
into verified counts. Binary bytes can pass hashing without being readable text;
empty UTF-8 content is a verified file with zero bytes.

Changing the selected folder, changing execution scope, leaving or reloading the
page revokes these tab-local results. The health snapshot stays pinned until
explicit refresh/reopen. Limits and incomplete inventories are disclosed. These
are results of completed reads, not continuous file-integrity monitoring,
provider recall, source completeness, task verification, or an archive
certificate. The existing 8 MiB read limit and authenticated/hash-checked reader
remain unchanged; this is not completion of large-body acceptance.

## 2. Open runtime evidence for one exact invocation

An indexed model/tool record now offers Runtime evidence for this invocation.
The action rechecks the current indexed identity, then resolves only an exact
raw invocation node with the appropriate type. Missing, ambiguous, inferred or
presentation-only nodes and contradictory recorded participants are rejected.
Neither a matching name nor the caller's entire activity substitutes for a
missing call node.

The existing bounded graph navigator opens over the investigation dialog and
returns to the expanded record on Escape. When starting from a single call,
traversal cannot cross another invocation through a shared process. Existing
shared-resource boundaries, depth limits and inferred/correlated labels remain.
This is recorded-neighborhood navigation, not new causal attribution, proof that
all nearby activity belongs to a call, or visibility inside a remote tool. A
call with no recorded runtime bridge explicitly has no navigable path.

## 3. Start with roles without changing the full graph

The shared Dashboard adds an initially expanded Start with roles section outside
the captured-response body. It presents a small searchable exact-ID role list
and direct entries for calls, handoffs and artifacts. It registers all node
identities before selecting agents, withholding agent/runtime ID conflicts and
same-ID duplicates instead of resolving them by display name.

The initial list shows at most six roles; search shows at most 25. The full
investigation index remains accessible. Same-run updates retain the user's search
and role buttons until explicit refresh. A new run clears the old scope, and
large-graph protection disables stale-inventory actions. Selecting a role opens
its existing inspector without taking the manual camera or filtering raw/display
graph membership. The complete historical graph remains the default. This is a
role-first navigation layer, not an automatic workflow-only canvas redesign.

## Validation and evidence boundaries

Local environment: Linux, Python 3.13.5, Chromium and Node 22.16.0. Completed
commands and JUnit outputs are retained in the accompanying validation archive.

| Completed test group | Passed | Excluded native cases |
|---|---:|---:|
| New role guide | 16 | 0 |
| New invocation navigation | 13 | 0 |
| New read-outcome/counter components | 23 | 4 |
| Existing reader identity/scope/modal cases | 29 | 3 |
| Existing runtime/investigation cases | 62 | 0 |
| Existing workflow/health/sharing cases | 43 | 1 |
| Unchanged geometry and camera modules | 38 | 0 |

The completed passing groups cover **224 distinct cases**: 52 new component
checks and 172 existing regressions. Existing tests, assertions, workflows,
dependencies, recorder code and package version are unchanged. The commands are
separate focused runs, not one uninterrupted complete product suite.

The four new native read cases were also attempted separately. Each failed at
`page.goto(file:...)` with `ERR_BLOCKED_BY_ADMINISTRATOR` before its actual
reading/crypto journey. They remain enabled for normal CI. The earlier native
HTTP probe was likewise blocked. An initial combined local command exceeded its
execution deadline before a final JUnit result; it is retained, not counted as
passing. No browser policy was bypassed and no skip was added to the repository.

Counter-positive component fixtures supply explicit synthetic ledger outcomes;
they do not establish successful native cryptography. Separate component cases
use actual directory inputs to exercise size-mismatch recording, immutable
outcome snapshots, folder/scope revocation and visible health results. Dedicated
native cases require real File input and SHA-256 for intact text, binary data,
same-size tampering and missing files. Their success remains unestablished
locally. New-head CI and independent verification must supply that evidence.

Ruff, assembled Live/static JavaScript syntax and whitespace checks passed. An
installed wheel imported outside the source directory assembled the shared shell;
all 209 Python files matched the candidate source. Wheel SHA-256:
`e4e41c277ff50f776d792b913c9ac8c9c603c05d833e36851613953a7f31b7d6`.
Dependencies were already available locally; this is not a clean-OS installation
or a release package. The development version remains 0.8.33.

## Original replay checkpoint

Grok #91 separately reported passing original MetaGPT Architect, QA and Project
Manager full-body reads, CAMEL terminal interpretation and two agent-local full
bodies, plus relocated return/reopen on the baseline. Together with #88 this
supplies the previously missing role-reading evidence at its stated versions.
The reports retain original responses, including No actions taken yet, and do
not replace them with model output or invent an earlier CAMEL outgoing message.
This is verifier-reported original replay, not a fresh provider run or a replay
performed locally for this batch. It does not validate the new counters/actions
by itself, and earlier fixed-target reports are not rewritten.

## Change impact and independent rollback

Six production files change: the reader/outcome ledger, health view, runtime
navigator, investigation actions, one new guide module and its shell injection.
Three new test modules and this record are added. No server route, polling loop,
raw event format, graph identity, historical capture, dependency, workflow or
version is changed.

- Revert the reader ledger and health summary together; original archive bytes
  and original reference counts do not require migration.
- Revert the invocation action and runtime resolver together; the pre-existing
  all-runtime and selected-node readers remain available.
- Revert the guide module and its shell import/injection together; no graph or
  layout rollback is required. The additive investigation tab entry can remain.

The changes advance bounded parts of W04, W06 and W07. Independent task
validation, complete native/provider attribution contracts, historical artifact
capture, content-aware redacted archives, large-run performance and fresh-provider
and independent-buyer acceptance remain open. Passing the baseline CI does not
become a new-head pass. No merge, tag, publication or main-branch update is part
of this batch.
