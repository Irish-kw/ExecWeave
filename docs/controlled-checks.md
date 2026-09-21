# Signed fixed-check executions

This path executes a small, explicit acceptance policy against selected bytes. It
is separate from `execweave.task_validation`, which imports an existing JUnit
report. Imported JUnit cannot become an authenticated execution by changing a
label or adding file hashes.

The new runner supports exactly three built-in operations:

| Operation | Evaluation |
|---|---|
| `sha256_equals` | SHA-256 of the captured bytes equals an approved 64-character lowercase digest. Empty and binary files are supported. |
| `utf8_contains` | Strictly decoded UTF-8 contains the approved nonempty literal string. No regular expression or script executes. |
| `json_pointer_equals` | Strict JSON at an RFC 6901 pointer equals an approved scalar, with type-sensitive comparisons. Duplicate fields, unsafe/non-integer numbers and excessive nesting are rejected. |

Unknown operations, extra command fields and empty policies are rejected **before
artifact reads**. No subprocess, shell, artifact import, model invocation, plugin,
network access or user-supplied test code is part of this runner.

## Trust and what a successful result means

A verifier uses its own signing key on a trusted host. The reviewer obtains a
**public profile through an independent approved channel**. That profile pins both
the public key fingerprint and the exact approved policy-file SHA-256. A result
cannot supply its own trust anchor. Merely receiving a profile beside a receipt
is not evidence that either belongs to a trustworthy verifier.

The signature covers the exact serialized payload with a versioned domain prefix.
It binds the run/session/source, complete native task snapshot and fingerprint,
approved policy, each evaluated file's size/hash, and every executed predicate's
outcome. Hashing and predicate evaluation consume the **same immutable Python byte
buffers**. A later change to a source path cannot change the already evaluated
snapshot or its signed hash.

Verification authenticates a statement **under the key selected by the reviewer**.
It is not hardware-backed proof of execution. A compromised verifier host, signing
key holder or altered runner can make false signed statements. Keep the verifier
account, policy and private key separate from the agent and its workspace. Check
key/policy fingerprints through the organization's existing trusted process.
There is no automatic PKI, remote host attestation, key revocation service or
proof of a person's identity behind a display label.

Only the listed predicates are tested. A text-contains rule is not a behavioral
program test. Do not use a trivial rule as evidence of complete task correctness.
The original overall task axis remains `unverified`; the separate result says
**specified fixed checks passed** or **did not all pass**. Arbitrary pytest/JUnit
execution under an isolated authenticated runner is not implemented by this path.

## Install and establish the approved policy

Ordinary recording/viewing does not require Python cryptography. Signing and CLI
signature verification use the optional extra:

```bash
python -m pip install 'execweave[validation]'
```

Create an operator-reviewed policy, for example:

```json
{
  "format": "execweave.fixed-check-policy.v1",
  "name": "Declared output contract",
  "checks": [
    {"id": "status", "path": "result.json", "op": "json_pointer_equals", "pointer": "/status", "expected": "ready"},
    {"id": "count", "path": "result.json", "op": "json_pointer_equals", "pointer": "/count", "expected": 3}
  ]
}
```

On the trusted verifier host, create a new private key and a public profile pinned
to this exact policy file. Changing whitespace in the policy changes its approved
fingerprint. Outputs must be new paths and must not overwrite existing evidence.

```bash
python -m execweave.controlled_checks keygen \
  --policy approved-policy.json \
  --private-key /protected/verifier-key.pem \
  --profile verifier-profile.json \
  --label 'Operator-approved verifier'
```

The private key is unencrypted on disk. POSIX creation uses mode 0600 and signing
rejects group/other permissions. Windows administrators must restrict its ACL
using their established account policy; the command does not claim to configure
Windows ACLs. Never commit, export or give the private key to the agent. If a
second output fails during key generation, a newly created private key may remain;
no existing file is overwritten and no success is reported.

## Execute and verify

Explicit file arguments are the only artifact-read authorization. Paths in the
policy name files inside the result; they do not authorize arbitrary local reads.
The set of selected names must exactly equal the policy's file set.

```bash
python -m execweave.controlled_checks run \
  --graph /copied-run/graph.json \
  --task-id 'EXACT_NATIVE_TASK_ID' \
  --policy approved-policy.json \
  --artifact 'result.json=/delivered/result.json' \
  --private-key /protected/verifier-key.pem \
  --output signed-checks.json
```

The runner records passing **and failing** predicate outcomes. Invalid JSON/UTF-8
needed by a predicate records an input-error outcome, never a pass. A missing file,
invalid policy, invalid key or failed bounded read refuses receipt creation.
The CLI return codes differ deliberately from the external JUnit importer:

- **0:** all nonempty approved fixed checks passed, or key generation completed.
- **1:** the signed execution contains failed checks/input errors.
- **2:** rejected input or creation/verification failure.

A reviewer can verify against an independently obtained profile and the exact
recorded task without reading artifact paths supplied by the receipt:

```bash
python -m execweave.controlled_checks verify \
  --graph /copied-run/graph.json --task-id 'EXACT_NATIVE_TASK_ID' \
  --profile independently-obtained-profile.json --receipt signed-checks.json
```

## Dashboard review and delivered-byte comparison

Open **Run assessment → Task verification → Review signed fixed checks**.
Select the independently obtained verifier profile, compare the displayed public
key/policy fingerprints through a trusted channel, and explicitly confirm trust.
Then select the signed result separately. The browser uses native WebCrypto
Ed25519 verification; unsupported native crypto refuses authentication, with no
fallback to an unsigned success label.

The view verifies the signature, approved policy hash, task snapshot, file
manifest and one-to-one result coverage. It derives counts from the signed case
records rather than accepting an aggregate success claim. Identical imports are
deduplicated. Contradictory executions remain separately visible.

Use **Select delivered artifact folder** to compare current selected bytes with
the exact evaluated hashes. Extra files are not read or certified. A match means
only those listed files match that historical evaluated snapshot. It is not a
whole-directory, dependency, permission or continuing integrity certificate.
Closing the modal revokes folder-comparison results; changing run/task, changing
or withdrawing trust, or pagehide revokes obsolete evidence. No keys, reports or
bodies are stored in browser persistence. Accepted signatures remain tab-local
until revoked and are not automatically added to an archive.

Receipts contain the signed policy (including expected values) and task snapshot;
these may be sensitive. Public review examples must use synthetic data. Artifact
bodies, local artifact source paths and private key bytes are not included.

## Limits and filesystem boundary

Limits are 100 fixed checks, 100 selected files, 8 MiB/file, 64 MiB captured data,
128 KiB policy, 1 MiB signed payload, 2 MiB selected receipt, JSON nesting 32, five
accepted browser results and 10,000 selected directory entries. Existing exact
native-task publication limits still apply. Exhaustion is a disclosed failure.

The artifact reader's before/after handle metadata checks are retained. They are
not an atomic filesystem snapshot. Equal metadata on an unusual overlay cannot
prove that no path replacement occurred; the #95 regression remains a separate
open item. The stronger guarantee in this runner is **identity of the captured
byte objects used for evaluation and signing**, not knowledge of the path's
entire history. Freeze/copy inputs under trusted operational control when that
history matters.

## Cryptographic implementation references

The implementation uses `cryptography`'s Ed25519 API, not custom signing math:
https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/

Browser key import and signature verification use native WebCrypto; the Level 2
specification is a draft and actual browser support is tested separately:
https://www.w3.org/TR/webcrypto/#ed25519
