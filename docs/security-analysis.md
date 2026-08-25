# Security Analysis

ExecWeave includes a small, explainable rule layer over a completed execution graph.

```bash
execweave analyze run.graph.json
```

Write the same report to a file:

```bash
execweave analyze run.graph.json --output analysis.json
```

## Goal

The analysis layer is intentionally conservative. It prioritizes graph evidence for review; it does not claim that an agent is malicious merely because it touched a sensitive resource or contacted the network.

The current rules are designed around one principle:

> **Do not convert co-occurrence into data-flow claims.**

## Current rules

### Sensitive-file access

The rule looks for process-attributed file edges involving common sensitive locations or filenames, including examples such as:

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker config
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- common SSH private-key filenames

A causal syscall-backed `OPENED_READ` is treated as stronger evidence than a non-causal session-level observation.

### External network contact

The rule identifies process edges to external network endpoints while excluding obvious loopback/private/link-local addresses.

Current runtime telemetry is primarily IP endpoint based. DNS/domain correlation is future work.

### Possible sensitive-file-to-network path

When the **same process** has causal sensitive-file access evidence and later causal external network activity, ExecWeave emits a prioritization finding.

Example:

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

This finding explicitly records:

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

The graph proves that the process performed both actions in that order. It does **not** prove that bytes from the file were sent over the connection.

Actual exfiltration claims require stronger telemetry such as byte-level data-flow or taint tracking.

## Severity

The current severity values are prioritization levels rather than vulnerability scores:

- `high`
- `medium`
- `low`
- `info`

For example, a confirmed external connection by itself is informational. A causal sensitive-file read followed by a confirmed external connection from the same process is higher priority, but still not proof of data exfiltration.

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

## Future analysis layers

Possible future additions include:

- credential and secret entity resolution
- domain reputation/context
- parent/child cross-process path analysis
- agent/tool/MCP semantic context
- anomaly detection
- attack-path ranking
- byte-level data-flow / taint tracking
- runtime allow / warn / block policy

These should continue to preserve the distinction between observed evidence, inferred risk, and proven causal data flow.
