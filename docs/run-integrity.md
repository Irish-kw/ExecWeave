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


## Local-only trust boundary

<!-- ew:trust:local-only -->

The local `seal` / `verify` pair detects accidental corruption and changes that were not re-sealed. It **does not prevent a writer who can rewrite run evidence and `integrity.json` from recomputing hashes and re-sealing a consistent run**. `valid: true` means only local consistency, never evidence of tamper-resistant auditing.

<!-- ew:trust:privileged -->

Root, sudo-capable agents, and any process able to write the output directory can rewrite the evidence and manifest. Protect the run directory with operating-system permissions and process isolation; another pathname with the same privileges is not isolation.

<!-- ew:compat:no-downgrade -->

**Downgrading the reader from v0.8.35+ to v0.8.34 is unsupported.** The older reader can silently omit `observation_assessment` and misrepresent observation completeness. Only conclusions produced by reader v0.8.35 or newer should be trusted. Rolling back a recorder does not justify rolling back the reader.

Seal only completed runs. Verify before relying on archived evidence. A failed check is evidence of a local inconsistency, not by itself proof of malicious activity. The tool never uploads run data or digests; it provides no independent authorization boundary.
