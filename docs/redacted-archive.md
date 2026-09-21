# Content-aware redacted derivative archives

ExecWeave can create a **separate sharing derivative** from a completed run archive. The source archive is opened read-only and is never rewritten. The derivative has its own content-addressed blobs, graph, conversation index, viewer, finalization receipt, and `lineage.json`.

This is not an anonymization guarantee. It applies an explicit bounded policy and records exactly which source content hashes produced which derived hashes. Unlisted sensitive values can remain if the policy does not remove them.

## Policy v1

The policy is UTF-8 JSON and is intentionally **not copied into the derivative**, because literal redaction terms may themselves be secrets.

```json
{
  "format": "execweave.redaction-policy.v1",
  "name": "external sharing",
  "replacement": "[REDACTED]",
  "literals": ["secret literal", "user@example.com"],
  "json_pointers": ["/credentials/token"],
  "redact_keys": ["cwd", "hostname", "password"],
  "binary": "drop"
}
```

`literals` are replaced in UTF-8 text, JSON string values, and free-text index metadata. `json_pointers` replace existing JSON values. `redact_keys` replace matching JSON/index metadata values, but structural keys such as `id`, `type`, `relation`, `path`, and `sha256` cannot be declared as redaction keys. Opaque binary content is replaced with an empty binary blob in v1 rather than copied.

Node/edge/message identifiers that contain an explicit literal are transformed consistently. If two identities would collide after redaction, creation fails closed.

## Create

```bash
python -m execweave.redacted_archive create \
  /path/to/completed-run \
  /path/to/new-sharing-derivative \
  --policy /path/to/redaction-policy.json
```

Requirements:

- the source finalization receipt must be complete;
- all declared source content references must exist and match their hashes/sizes;
- the destination must not already exist;
- policy/finalization/content reads are bounded and regular-file only;
- no file URL, remote URL, parent traversal, symlink/reparse-point target, command, script, or model call is authorized by the policy.

The output is prepared in a sibling temporary directory, verified, and then renamed into place. A failed build does not leave a partially accepted destination.

## Verify

Standalone derivative integrity and lineage declarations:

```bash
python -m execweave.redacted_archive verify /path/to/derivative
```

Also recheck the source fingerprints recorded in the lineage manifest:

```bash
python -m execweave.redacted_archive verify \
  /path/to/derivative \
  --source /path/to/original-run
```

The derivative contains `lineage.json`. Each mapping records source path/hash/size, derived path/hash/size, whether the bytes changed, and the applied transformation class. `finalization.json` pins the lineage file hash and the policy hash. `graph.json` identifies the archive as `execweave.redacted-archive.v1` and carries the same policy hash.

The derivative viewer remains a normal ExecWeave Offline viewer. When a recipient explicitly selects the derivative folder, the existing archive verifier now checks the primary exports, declared content, `lineage.json`, derived mappings, and policy/source-finalization fingerprints with native SHA-256. It reports that the source archive is **declared by fingerprint but not rechecked** unless the source archive is separately supplied to the Python verifier.

## Evidence boundary

A successful derivative verification establishes that:

- the derivative's graph/conversations/viewer match its finalization receipt;
- every declared derivative content blob matches its derived hash/size;
- the lineage manifest matches its receipt hash;
- every derived content reference is covered by the lineage mappings;
- if the source archive is supplied, its finalization, primary exports, and mapped source content hashes match the lineage declarations.

It does **not** establish that:

- the policy removed every possible secret;
- the output is anonymous or resistant to re-identification;
- the source archive is authentic when it is not supplied;
- the provider exposed all relevant source evidence;
- the task was correct or independently validated;
- a writable filesystem never changed between bounded observations.

The original archive, original hashes, and original finalization receipt remain unchanged.
