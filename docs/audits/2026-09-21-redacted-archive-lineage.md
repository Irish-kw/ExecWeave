# Redacted archive + lineage checkpoint — 2026-09-21

Baseline candidate: `9e16bd8abd3bc5f004e5759b4ebdbf8e425c1332` / tree `30e16f68a46e5f166fee96efb5625abdaf82c2bf`.

This batch advances W05/W08 only. It does not add another navigation surface, claim universal task validation, modify providers/recorder/raw captures, or release 0.8.34.

## Implemented

- `redacted_archive.py` creates an independent content-aware derivative from a completed source archive.
- Source finalization, primary exports, declared content, redaction policy and content reads are bounded; policy/finalization must be regular non-link files.
- Text literal, JSON literal/key/pointer, and binary-drop transformations create new content hashes.
- Index content references are rewritten to the derived blobs. Free-text metadata follows the explicit policy; source path is withheld and session identity becomes a deterministic derivative identity.
- Exact `id`/`source`/`target` strings that change under literal redaction are rewritten consistently; post-redaction identity collisions fail closed.
- `lineage.json` records source→derived hash/size mappings, transformation classes, source primary fingerprints and derived primary fingerprints without copying the secret-bearing policy body.
- `finalization.json` pins `lineage.json`, the policy SHA-256, and the source-finalization SHA-256.
- The existing browser archive verifier recognizes derivative lineage and checks the derived side with native SHA-256. The delivery panel labels source fingerprints as declared but not rechecked.
- Python verification can optionally receive the source archive and recheck its finalization/primary/content fingerprints against lineage.
- Output construction is deterministic and staged in a temporary sibling directory before final rename. Existing destinations are never overwritten.

## Local evidence before publication

Completed, distinct focused groups:

- new derivative core: 12 passed;
- new derivative core + JS lineage verifier + existing delivery/content-integrity: 139 passed;
- final new core/component set: 15 passed;
- existing content-integrity + delivery status: 125 passed;
- Ruff on the repository: PASS;
- assembled Live/static JavaScript syntax: 29 scripts PASS;
- release-stage integrity: PASS with the PR's existing pinned historical fixture allowance, 2,820 current test identities, no new skip/xfail.

These groups overlap and must not be added as unique product-test totals. Native browser journeys are separate.

## Preserved non-passes / environment boundaries

- New native `localhost` derivative-folder verification was attempted and failed at `page.goto` with `ERR_BLOCKED_BY_ADMINISTRATOR`, before folder/File/WebCrypto verification.
- New relocated `file://` derivative-folder verification was separately attempted and failed at `page.goto` with the same policy code.
- The pre-existing structural-sharing localhost/native test fails at the same navigation boundary in this environment. This supports an environment classification but does not convert any blocked journey into PASS.
- A full `test_workflow_content_health_share.py` attempt exceeded the execution limit after progressing past most component cases; a bounded `-x` run identified only the same localhost browser-policy failure. Neither incomplete run is counted as a pass.

The native derivative tests remain enabled for ordinary CI / independent Grok verification; no repository skip, request interception, digest bridge, browser policy bypass, or assertion relaxation was added.

## Rollback / impact

The core derivative module is additive. Browser changes only extend the existing explicitly selected archive-folder verifier to admit and validate `lineage.json`, and add derivative disclosure to the archive card. Remove those additions plus the new tests/docs to roll back; source archives and old finalization receipts need no migration.

Security/performance boundaries remain explicit: 128 KiB policy, 16 MiB finalization, 32 MiB lineage, 64 MiB per transformed source blob and 256 MiB total transformed source content. The ordinary recorder/render path pays none of this derivative I/O.

## Open after this batch

- current-head CI on the published derivative candidate;
- authorized native HTTP and relocated Offline folder verification;
- independent source/derivative lineage replay;
- remaining broad W02/W03/W04/W06/W07 coverage and fresh-provider/large-run/final buyer acceptance.
