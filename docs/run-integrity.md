# Run Integrity

<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 can seal a completed run into a deterministic SHA-256 inventory and later verify that inventory. This feature is for local post-seal corruption and modification detection. It is deliberately not described as adversary-resistant tamper evidence when the manifest and evidence remain inside the same writable trust boundary.

## Scope

`execweave-integrity seal` inventories every regular file under the selected run directory, recursively, except `integrity.json` itself. Entries are sorted by relative POSIX path and record the path, byte size, and SHA-256 digest. Symbolic links are rejected rather than followed or silently normalized.

The seal is intended to run only after capture and all desired derived artifacts are complete. A file created after sealing is reported as unsealed; a sealed file that is changed, replaced, or deleted fails verification.

## Seal and verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` refuses to overwrite an existing non-empty integrity contract. `verify` returns success only when the manifest schema is valid, its body digest matches, every sealed file has the expected size and SHA-256 digest, and no additional regular file has appeared since sealing.

## Manifest contract

| Field | Meaning |
| --- | --- |
| `schema_version` | Integrity schema version; v0.6.5 starts at `0.1`. |
| `files` | Deterministically ordered sealed file inventory. |
| `manifest_body_sha256` | SHA-256 of canonical manifest content excluding this digest field. |
| `trust_model` | Explicit statement of what this local seal does and does not prove. |

The manifest records `malicious_writer_resistance: false` and `external_trust_anchor: false`. These fields are part of the schema contract, not optional documentation language.

## Trust boundary

A local digest is useful for detecting accidental corruption, incomplete copies, or post-seal changes relative to the recorded seal. It does not stop a process that can rewrite both the run evidence and `integrity.json`: such a process can recompute hashes and construct a new internally consistent manifest.

For a stronger guarantee, copy `manifest_body_sha256` or the complete manifest to a location outside the observed process's write boundary, or protect/sign it with a key unavailable to that process. That external action creates the trust anchor; ExecWeave does not claim that an in-directory manifest creates one by itself.

## Operational rules

Seal only a completed run. Verify before relying on archived or transferred evidence. Treat any verification error as a signal that the directory no longer exactly matches the sealed inventory, not as proof of malicious activity. If more artifacts must be generated after sealing, create them first and then seal a new finalized copy rather than silently rewriting the original manifest.
