<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <a href="security-analysis.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="security-analysis.ko.md">한국어</a>
</p>
<!-- i18n-nav:end -->

# Security Analysis

ExecWeave は completed execution graph 上に conservative / explainable な rule layer を提供します。

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

Current analysis schema は `0.2`。

## Goal

目的は review priority を付けることであり、Agent が sensitive resource に触れたり network を使っただけで malicious と判定することではありません。

> **Co-occurrence や process lineage を data-flow claim に変換しない。**

## Rules

### Sensitive-file access

`~/.ssh/*`, `~/.aws/credentials`, `~/.kube/config`, Docker config, `.npmrc`, `.pypirc`, `.netrc`, `.env`, SSH private key などを対象にします。Causal syscall-backed edge は session-level non-causal observation より強い evidence です。

### External network

Process から external endpoint への edge を確認し、loopback/private/link-local を除外します。DNS/domain correlation は future work です。

### Same-process possible path

同じ process が causal sensitive-file access の後に causal external connection を持つ場合、high-priority review signal を出せます。

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

しかし：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

です。Action order は証明できますが bytes の transfer は証明できません。

### Delegated path

Causal chronological `SPAWNED` chain を追跡し、parent sensitive read → spawn → child external network の possible path を示します。

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` は process lineage の evidence であり、memory/pipe/socketpair/shared-memory/environment-secret transfer の証明ではありません。

Actual data flow claim には taint tracking、IPC-aware provenance、byte-level telemetry などが必要です。

## Severity

`high / medium / low / info` は investigation priority であり vulnerability score ではありません。Delegated path は process boundary の data transfer が未証明なので equivalent same-process path より保守的に扱います。

## Backend dependence

Linux `strace` は supported operation の process-attributed syscall evidence を提供できます。Portable filesystem attribution は弱いため同じ conclusion を出せません。Analyzer は graph の `causal` metadata を尊重します。

## Output

Report には schema/session/finding count/severity、limitations、rule ID、related nodes/edges、evidence event IDs、rule-specific attributes が含まれます。Delegated finding には process chain と explicit negative guarantees も含まれます。

Provider semantic evidence や `CORRELATED_WITH_PROCESS` inferred edge は graph に存在できますが、`inferred: true / causal: false` を OS-observed causality に upgrade してはいけません。

## Future

Credential/secret resolution、DNS/domain context、explicit IPC、environment/handle provenance、Agent/Tool/MCP context、anomaly detection、attack-path ranking、byte-level taint、runtime policy などを予定しています。

すべて observed evidence / inferred risk / process lineage / proven data flow の区別を維持する必要があります。
