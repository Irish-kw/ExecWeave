# Security Analysis

ExecWeave includes a conservative, explainable rule layer over a completed execution graph.

```bash
execweave analyze run.graph.json
```

Write the same report to a file:

```bash
execweave analyze run.graph.json --output analysis.json
```

The current analysis schema is `0.2`.

## Goal

The analysis layer prioritizes graph evidence for review. It does not claim that an agent is malicious merely because it touched a sensitive resource or contacted the network.

The core rule is:

> **Do not convert co-occurrence or process lineage into data-flow claims.**

## Current rules

### Sensitive-file access

The rule looks for file edges involving common sensitive locations or filenames, including examples such as:

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker config
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- common SSH private-key filenames

A causal syscall-backed process edge is stronger evidence than a non-causal session observation.

### External network contact

The rule identifies process edges to external network endpoints while excluding obvious loopback/private/link-local addresses.

Current runtime telemetry is primarily IP endpoint based. DNS/domain correlation is future work.

### Possible same-process sensitive-file-to-network path

When the **same process** has causal sensitive-file access evidence and later causal external network activity, ExecWeave emits a prioritization finding.

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

The finding records:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

The graph proves that the process performed both actions in chronological order. It does **not** prove that bytes from the file were sent over the connection.

### Possible delegated sensitive-file-to-network path

Analysis schema `0.2` also follows chronological causal `SPAWNED` edges.

Example:

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

A delegated finding is emitted only when:

1. the sensitive-file edge is causal;
2. the `SPAWNED` edge or chain is causal;
3. the spawn sequence occurs after the sensitive-file access sequence;
4. the descendant's external network evidence occurs after the spawn chain;
5. the path depth stays within the analyzer's conservative traversal bound.

This proves a chronological process-lineage path. It still does **not** prove that the child received file data from the parent.

Delegated findings explicitly record:

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` is evidence of process creation/lineage, not evidence of memory inheritance, a pipe write, socketpair transfer, shared-memory transfer, environment-secret transfer, or any other concrete data movement.

Actual data-flow or exfiltration claims require stronger evidence such as taint tracking, IPC-aware provenance, or byte-level read/write/network telemetry.

## Severity

Severity values are prioritization levels rather than vulnerability scores:

- `high`
- `medium`
- `low`
- `info`

Current examples:

- external connection alone: informational;
- sensitive-file access: depends on relation and attribution strength;
- same-process sensitive read followed by confirmed external connection: high-priority signal;
- delegated child-process path: lower than an equivalent same-process path because data transfer across the process boundary is not proven.

## Backend dependence

Analysis quality is bounded by collector quality.

The Linux `strace` reference backend can provide process-attributed syscall evidence for supported operations. The portable backend has weaker filesystem attribution and therefore cannot support the same process-level conclusions.

The analyzer respects the graph's `causal` metadata rather than upgrading weaker evidence.

## Output

The report contains:

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

Delegated findings additionally include the process chain, delegation-hop count, spawn sequences, and explicit negative guarantees about data inheritance/IPC/data flow.

## Future analysis layers

Possible future additions include:

- credential and secret entity resolution
- DNS/domain correlation and context
- explicit IPC edges
- environment-variable and inherited-handle provenance
- agent/tool/MCP semantic context
- anomaly detection
- attack-path ranking
- byte-level data-flow / taint tracking
- runtime allow / warn / block policy

These should continue to preserve the distinction between observed evidence, inferred risk, process lineage, and proven causal data flow.
