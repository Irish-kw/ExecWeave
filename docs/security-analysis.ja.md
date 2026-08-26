<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <a href="security-analysis.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="security-analysis.ko.md">한국어</a> |
  <a href="security-analysis.fr.md">Français</a> |
  <a href="security-analysis.de.md">Deutsch</a> |
  <a href="security-analysis.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Security Analysis

ExecWeave は completed execution graph 上に conservative で explainable な rule layer を提供します。

```bash
execweave analyze run.graph.json
```

同じ report を file に書くには：

```bash
execweave analyze run.graph.json --output analysis.json
```

Current analysis schema は `0.2` です。

## Goal

Analysis layer は review すべき graph evidence に priority を付けます。Agent が sensitive resource に触れたり network に接続したという理由だけで malicious と主張しません。

Core rule：

> **Co-occurrence や process lineage を data-flow claim に変換しない。**

## Current rules

### Sensitive-file access

Rule は common sensitive location または filename に関係する file edge を探します。例：

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker config
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- common SSH private-key filenames

Causal syscall-backed process edge は non-causal session observation より強い evidence です。

### External network contact

Rule は process から external network endpoint への edge を識別し、明らかな loopback/private/link-local address を除外します。

現在の runtime telemetry は主に IP endpoint ベースです。DNS/domain correlation は future work です。

### Possible same-process sensitive-file-to-network path

**同じ process** が causal sensitive-file access evidence を持ち、その後に causal external network activity を持つ場合、ExecWeave は prioritization finding を emit します。

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

Finding は次を記録します。

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

Graph はその process が 2 つの action を chronological order で実行したことを証明します。ただし file の bytes が connection を通じて送信されたことは**証明しません**。

### Possible delegated sensitive-file-to-network path

Analysis schema `0.2` は chronological causal `SPAWNED` edge も追跡します。

例：

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

Delegated finding は次の条件をすべて満たす場合のみ emit されます。

1. sensitive-file edge が causal；
2. `SPAWNED` edge または chain が causal；
3. spawn sequence が sensitive-file access sequence より後；
4. descendant の external network evidence が spawn chain より後；
5. path depth が analyzer の conservative traversal bound 内。

これは chronological process-lineage path を証明します。ただし child が parent から file data を受け取ったことは依然として**証明しません**。

Delegated finding は次を明示的に記録します。

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` は process creation/lineage の evidence であり、memory inheritance、pipe write、socketpair transfer、shared-memory transfer、environment-secret transfer、その他の具体的な data movement の evidence ではありません。

Actual data-flow または exfiltration claim には taint tracking、IPC-aware provenance、byte-level read/write/network telemetry など、より強い evidence が必要です。

## Severity

Severity value は vulnerability score ではなく prioritization level です。

- `high`
- `medium`
- `low`
- `info`

現在の例：

- external connection 単独：informational；
- sensitive-file access：relation と attribution strength に依存；
- same-process sensitive read の後に confirmed external connection：high-priority signal；
- delegated child-process path：process boundary を越える data transfer が証明されていないため、equivalent same-process path より低い priority。

## Backend dependence

Analysis quality は collector quality によって制約されます。

Linux `strace` reference backend は supported operation について process-attributed syscall evidence を提供できます。Portable backend は filesystem attribution が弱く、同じ process-level conclusion を support できません。

Analyzer は weaker evidence を upgrade せず、graph の `causal` metadata を尊重します。

## Output

Report には次が含まれます。

- analysis schema version
- session ID
- total finding count
- severity counts
- explicit limitations
- per-finding rule ID
- title and summary
- related node IDs
- related edge IDs
- evidence event IDs
- rule-specific attributes

Delegated finding にはさらに process chain、delegation-hop count、spawn sequence、data inheritance/IPC/data flow に関する explicit negative guarantee が含まれます。

## Future analysis layers

将来的な追加候補：

- credential and secret entity resolution
- DNS/domain correlation and context
- explicit IPC edges
- environment-variable and inherited-handle provenance
- agent/tool/MCP semantic context
- anomaly detection
- attack-path ranking
- byte-level data-flow / taint tracking
- runtime allow / warn / block policy

これらも observed evidence、inferred risk、process lineage、proven causal data flow の区別を維持する必要があります。
