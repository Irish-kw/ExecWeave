# ExecWeave journal manuscript

This directory contains the first Overleaf-ready journal draft for ExecWeave.

## Files

- `main.tex` — Overleaf root document and manuscript metadata.
- `sections/01_intro_related.tex` — introduction, motivation, and related work.
- `sections/02_formulation_design.tex` — problem formulation and system design.
- `sections/03_implementation_evaluation.tex` — implementation and controlled evaluation methodology.
- `sections/04_preliminary_discussion.tex` — repository-backed preliminary characterization and discussion.
- `sections/05_validity_conclusion.tex` — validity, reproducibility/ethics, future directions, and conclusion.
- `references.bib` — bibliography used by the manuscript.

## Typesetting target and verified build

- Template: `IEEEtran`, journal, two-column.
- Overleaf main document: `main.tex`.
- Compiler: pdfLaTeX + BibTeX (Overleaf's normal automatic build is sufficient).
- The current branch snapshot was compiled locally with the same root/section/BibTeX structure and produces **14 pages including references**.
- The 14-page count is a working IEEE-journal target, not a promise that another journal's production template will paginate identically.
- The verified build has no unresolved citations/references and no overfull horizontal boxes.

## Reproducibility rule for the paper source

The manuscript is intentionally self-contained at typesetting time:

- no Python execution from TeX;
- no CSV loading from TeX;
- no runtime benchmark-data import from TeX;
- all reported numeric values are written statically in the TeX source after evidence verification.

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

Product rows use conservative wording such as **Not native** rather than claiming that a general tracing system can never represent custom OS-derived spans. The empirical methodology further separates native/default instrumentation, documented extensibility, and common externally supplied OS evidence so that competitors are not handicapped or given unfair extra telemetry.

## What is already evidence-backed

The manuscript uses repository documentation/source contracts for the system design and includes one historical, frozen reference microbenchmark from ExecWeave v0.6.0. That table is clearly labeled preliminary/historical and is **not** presented as v0.8.22 performance.

The evaluation plan already specifies attribution precision/recall, false-attribution and abstention rates, diagnostic-question scoring, cross-provider/cross-OS graph agreement, negative controls, instrumentation tiers, ablations, performance/scalability measures, robustness tests, and statistical analysis.

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
