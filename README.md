# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

<p align="center">
  <strong>English</strong> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**See what AI agents actually do on your machine.**

ExecWeave is an open-source, local-first observability project that turns AI-agent activity into an interactive execution graph while keeping observed evidence separate from inference.

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## Install

ExecWeave is published on PyPI as a standard Python wheel/sdist. Install the latest published release with:

```bash
python -m pip install -U execweave
```

The `main` branch may contain a newer patch than the current PyPI release. To test the latest mainline build directly:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

For development:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Watch Claude Code, OpenAI Codex, or Gemini CLI live:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

Or build the full artifact pipeline:

```bash
execweave record --open -- python my_agent.py
```

## Performance and footprint

ExecWeave includes a reproducible package-level overhead benchmark that is run from an installed wheel. The reference plot follows the same trade-off style commonly used for model quality/cost comparisons:

- **X-axis:** additional peak process-tree RSS, low → high.
- **Y-axis:** runtime overhead, low → high.
- **Bubble area:** median artifact size per run.
- **Preferred region:** lower-left.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |
