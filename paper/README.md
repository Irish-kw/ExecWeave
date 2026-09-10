# ExecWeave journal manuscript

This directory contains the first Overleaf-ready journal draft for ExecWeave.

## Files

- `main.tex` — main IEEE journal manuscript.
- `references.bib` — bibliography used by the manuscript.

## Typesetting target

- Template: `IEEEtran`, journal, two-column.
- Working length target: approximately 14 pages including figures, tables, and references. The exact page count should be frozen only after the final venue/template and empirical-result tables are fixed.
- Overleaf main document: `main.tex`.
- Compiler: pdfLaTeX + BibTeX (Overleaf's normal automatic build is sufficient).

## Reproducibility rule for the paper source

The manuscript is intentionally self-contained at typesetting time:

- no Python execution from TeX;
- no CSV loading from TeX;
- no runtime benchmark-data import from TeX;
- all reported numeric values are written statically into `main.tex` after evidence verification.

This rule is deliberate: the paper should compile independently of the experiment environment and every submitted number should be auditable in the frozen manuscript diff.

## Current scientific framing

The draft does **not** claim that ExecWeave is the first agent graph or the first agent-observability dashboard. Contemporary products and papers already expose trace trees, agent graphs, temporal graphs, or execution graphs.

The paper instead studies the **semantic--runtime observability gap**: provider/framework telemetry describes logical agent actions, while independent operating-system telemetry describes processes, files, and network effects. ExecWeave's main research object is an evidence-aware cross-layer execution-provenance graph that preserves those observation boundaries and abstains from unsupported semantic-to-runtime attribution.

The current contribution structure is:

1. a typed cross-layer execution-provenance model for agentic software;
2. conservative semantic-to-runtime attribution with explicit abstention and evidence strength;
3. evidence-preserving live/final graph materialization across heterogeneous providers and operating systems;
4. a controlled comparative evaluation methodology against agent-observability, OS-only, and naive-fusion baselines.

## Comparison set in v1

The literature/competitive positioning currently covers:

- LangSmith;
- Langfuse;
- Arize Phoenix;
- AgentOps;
- W&B Weave;
- AgentGraph (AAAI 2026);
- AgentSeer (AAAI 2026);
- AgentTrace;
- Graph of Trace;
- OpenTelemetry / distributed tracing;
- classical whole-system provenance systems including PASS, Hi-Fi, SPADE, Linux Provenance Modules, CamFlow, ProTracer, and RAIN;
- classical layered and dynamic graph-drawing literature.

Product rows use conservative wording such as **Not native** rather than claiming that a general tracing system can never represent custom OS-derived spans. Final submission claims should be based on frozen versions and controlled runs, not documentation alone.

## What is already evidence-backed

The manuscript uses repository documentation/source contracts for the system design and includes one historical, frozen reference microbenchmark from ExecWeave v0.6.0. That table is clearly labeled preliminary/historical and is **not** presented as v0.8.22 performance.

## Submission blockers intentionally left open

The first draft does not fabricate missing empirical results. A submission-quality revision still needs:

1. a frozen ground-truth workload harness independent of ExecWeave output;
2. controlled competitor runs under equivalent workloads;
3. a fresh v0.8.22 cross-provider × cross-OS campaign;
4. attribution precision/recall, false-attribution rate, and abstention measurements under concurrency;
5. current overhead and scalability measurements;
6. robustness experiments covering short-lived activity, interruption, surviving descendants, missing hooks, and ambiguity;
7. a controlled analyst/debugging study if the target venue expects human-utility claims;
8. final author metadata, target journal, and venue-specific formatting.

These gaps are explicitly visible in the manuscript so that later empirical results can replace placeholders without silently changing the contribution claim.
