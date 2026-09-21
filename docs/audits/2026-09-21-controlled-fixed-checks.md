# Controlled fixed-check execution: local candidate

Baseline: b10e252d3545f2d7175e5fbba28ed0e30ef8482b
Baseline tree: 2a5b842dd53bc61f8c3c1e345cb94bfba6b6d811
Status: local implementation; not pushed, not independent acceptance.

## Bounded W01 delivery

This batch connects direct fixed-predicate execution, evaluated-byte identity,
Ed25519 result signing, separately pinned key/policy verification and delivered
folder comparison. It does not just sign an imported report or relabel an
operator-supplied artifact association as execution evidence.

The runner deliberately does not execute arbitrary artifact code. Its supported
criteria are file SHA-256, literal UTF-8 containment, and type-sensitive JSON
pointer/scalar equality. Signer and reviewer must trust the verifier host and
separately approve the key and policy. The user guide records that threat model,
CLI/operator journey, budgets and limitations. Whole-task correctness and a
host-isolated arbitrary test executor remain outside this implemented path.

## Change impact

- `controlled_checks.py`: strict policy, actual bounded reads, immutable byte
  predicates, signed payload, key/profile generation and CLI verification.
- `viewer_controlled_checks.py`: signature/profile/coverage validation, explicit
  trust consent, exact published task binding, signed evidence review and actual
  directory comparison. No persistence, network fetch or arbitrary commands.
- `viewer_run_assessment.py`: additive shared-shell injection. Original axes and
  unsigned external report behavior remain unchanged.
- `pyproject.toml`: optional `validation` extra and developer test dependency on
  `cryptography>=44`. Base runtime dependencies and version are unchanged; normal
  recorder/viewer import does not require cryptography.
- Two new test modules and the operator guide/audit. No historical assertions,
  tests, CI workflows, collector, provider routing, source captures or main changed.

These eight files are one reviewable batch. Revert the injection with its modules,
new tests and optional dependency entries to remove the feature. Existing unsigned
v1/v2 reports and original archives need no migration.

## Tests and evidence

The baseline report/artifact-core command passed 71 existing cases. Initial new
core tests passed 54, including Python signatures verified by real Node WebCrypto
using the shipped strict-JSON and verification JavaScript. The result is native
Python/Node interoperability, not native browser acceptance.

The final expanded core/assessment/artifact command passed 223 distinct cases.
One preceding command used the wrong optional browser-selection environment name:
215 passed and eight setup errors (bundled Chromium absent). Setting the existing
`EXECWEAVE_E2E_CHROMIUM` selector to the installed executable completed all 223;
no test or assertion was changed for this correction.

The signed-check browser component module passed 18 cases. These deliberately use
an explicitly named Python-cryptography bridge for UI/trust/race testing; they
are not native browser signature evidence. A larger combined browser command
reached only partial progress before the tool deadline, with no completed JUnit;
it is retained as incomplete, not passed. Final component runs are reported by
their actual distinct test IDs in the local evidence bundle.

Four native file-origin Ed25519/folder cases remain enabled. Local browser policy
blocks file-origin navigation, so no local native browser acceptance is claimed.
No policy was bypassed and no skip/xfail marker was introduced.

The final completed groups cover **286 distinct checks**, without double-counting
iterations:

| Group | Passed | Native cases not selected in this group |
|---|---:|---:|
| Fixed-check core plus existing assessment/report/artifact regressions | 223 | 0 |
| New signed-check UI components | 18 | 4 |
| Existing external-report UI components | 20 | 4 |
| Existing artifact-comparison UI components | 19 | 4 |
| Existing content-priority and first-screen checks | 6 | 0 |

The four new native cases were attempted separately: **four failures at navigation,
zero completed journeys**. The eight older native cases were not rerun in this
batch. These five focused commands are not a full uninterrupted product suite.
The core group includes 54 new cases; the new browser component group includes
18, so the passing total is 72 new and 214 existing checks. The native failures
and incomplete combined runs remain in the evidence rather than being relabeled.

The installed wheel was unpacked and imported outside the source checkout; all
**214 packaged Python files** match the candidate. Normal shell rendering also
passed with imports of the optional cryptography package deliberately blocked.
All 15 assembled JavaScript fragments passed native Node syntax checks. Ruff and
whitespace checks passed. Existing dependencies were used, not a fresh-OS install.
Exact candidate tree, wheel/source fingerprints, commands and unchanged-file
checks are in the accompanying local validation manifest. Historical CI badges
are not this candidate's acceptance.

The unchanged release-stage checker passed with the branch's pre-existing pinned
audit-fixture allowance only: baseline test identities retained, no new skip/xfail,
unchanged critical-release/version rules, and capability/i18n checks passed. Its
2,768 collected identities are collection evidence, not 2,768 executed passes.
An earlier checker invocation failed to import `execweave` in its child process
because this restored checkout was not installed editable. Setting `PYTHONPATH`
to this exact checkout's `src` directory resolved that setup error without
changing any checker or dependency declaration. Both logs are retained. Two
Markdown line-ending whitespace findings were removed before final diff checks.

## Publication and unresolved gates

The current connection exposes 48 GitHub read/search actions, not commit/ref or
issue-write actions; write-action discovery and installed-plugin discovery did not
provide an available writer. No authenticated CLI is installed in the runtime.
This candidate therefore remains local. The patch and fixed-baseline handoff are
provided without claiming a push, a new PR head, a new bot issue or CI results.

The last observed remote head remains b10e252. Its known macOS diagnostic sampler
failure and #95 overlay path-swap defect remain separate unresolved regressions.
This batch does not change those tests or silently mark them fixed. New-head native
Windows/macOS, independent signed-check verification, provider coverage, broader
lineage/redacted-export work and final buyer acceptance remain open. W01 as a
whole and release readiness are not declared complete.
