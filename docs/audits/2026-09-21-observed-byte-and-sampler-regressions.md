# Repeated artifact-byte observations and sampler readiness

Baseline: PR #110 at `c3ab4821b68fe0a280389d915476403526236f4c`, tree
`0d193a9f4cad9f4018a0e74d7a4afbc3a9590a15`. This batch repairs two existing
regressions. It introduces no new validator authority or buyer-facing feature.

## Artifact changes hidden by equal metadata

Grok #95 reported that replacing a selected file on its overlay filesystem could
leave the metadata signature unchanged. The old reader accepted the replacement
because its first observation read metadata only. Its archive helper's Windows
compatibility correction did not address this byte-observation gap.

I reproduced the algorithmic failure independently with real selected files and
explicitly frozen metadata: replace/rewrite at the data open or final path open.
All four cases failed before the repair, while four controls passed. This is
fault injection modeling the reported filesystem behavior, not a measurement of
native overlay metadata on the local host. The old unmodified path-swap test
passed locally, which is not evidence that the reported defect disappeared.

The selected-artifact reader now obtains bounded bytes at the initial selection,
the data open, and the final reopened path. It requires equality of all three
byte observations, as well as exact device/inode/size/mtime_ns/ctime_ns checks.
The data handle stays open during the final path read. A difference fails the
operation; there is no retry that silently substitutes a newer version.

All observations use descriptor metadata; path timestamps do not override it.
Leaf-link/reparse rejection, binary mode, size budgets and error cleanup remain.
The archive reader and its metadata helper are unchanged. Only an explicitly
selected artifact authorizes these reads, not a path embedded in a report.

Cost: three bounded reads instead of one payload read. Each reads at most 8 MiB
plus one overflow byte. At most the original and one comparison buffer are kept
at once; original per-file, inventory and total-byte limits remain unchanged.
This is extra I/O in the optional artifact/controlled-check path, not in recording
or graph rendering. No throughput benchmark is claimed.

**Equal observations are not an atomic snapshot or proof of an immutable path.**
Transient changes restored between observations can escape detection, as can
changes after the last observation. Hashes and fixed predicates still use the
same returned immutable buffer. This closes the reproduced substitution cases,
not all adversarial filesystem races or the wider W01/W08 requirements.

New tests exercise unchanged metadata with actual changed bytes, empty/binary
content, all seven metadata-error boundaries, exact final metadata differences,
stream-construction/read failures, closed descriptors and bounded three-pass
reads. On a platform that refuses unlink of an open file, the final-replacement
case accepts only that refusal with the old file intact; it is not labeled as a
successful byte-comparison experiment. The rewrite cases remain separate.

## Sampler test waits for an actual observation

The earlier macOS/Python 3.10 failure asserted that a 100 ms sleep must allow a
sample. The test now waits for a real sample count with a two-second deadline;
absent or failed sampling fails explicitly. The five-second child-process
limit, the native timer and all original assertions remain unchanged.

The sampler implementation is unchanged. Two new tests cover delayed real
sampling and refusal of absent/failed sampling. The delayed fixture controls
thread admission but still uses the actual sampling implementation and native
stack dump. No sample count or stack text is fabricated. Original assertion ASTs
were compared and are identical across all six existing test functions.

## Completed local validation and limits

- Artifact/report/controlled-check/archive-helper command: **191 passed**.
- Complete sampler module: **8 passed**.
- **199 distinct passing cases**, including 33 new artifact cases and two new
  sampler cases. The earlier 63/176-case runs overlap and are not added.
- Ruff, compilation, whitespace and original-assertion/source boundaries checked.

Two broader diagnostic commands did not produce final JUnit before their tool
execution limits (45 and 120 seconds). Both reached the descendant-cleanup case;
its journal records test start but no completed summary. Those are incomplete
runs, not passes and not proof of the cause of the stall. No diagnostic runner,
cleanup code, test budget or CI workflow was changed. The first deadline case
had a completed cleanup/summary. Evidence is retained for independent diagnosis.

An unchanged artifact-UI component command also exceeded its local command limit
after partial progress, without final JUnit. It is not counted as passing. This
batch does not claim a completed browser suite, fresh native Windows/macOS run,
new original-provider replay or full CI acceptance. Native and independent
fixed-target verification remain required.

The baseline was reconstructed from the verified 7f51c21 source bundle and the
successive changed-file packages. Every intermediate tree matched the recorded
remote tree, ending at the exact c3ab482 tree. Synthetic reconstruction ancestry
is local only and must not be pushed as repository ancestry.

## Impact and independent rollback

Four files change: `task_artifacts.py`, the existing sampler test module, the new
artifact regression module and this record. Recorder, graph/layout, browser
components, signing protocol, archive helper, sampler implementation, workflow,
dependency and package version are unchanged.

The artifact read repair and sampler prerequisite change can be reverted
independently. No graph or archive migration is needed. Existing signed receipts
and unsigned v1/v2 reports keep their formats and trust boundaries. Earlier
failed heads and #95/#96 fixed-target reports stay intact. No merge or release
is included in this batch.
