# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <strong>Deutsch</strong> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**Sehen Sie, was KI-Agenten auf Ihrem Rechner tatsächlich tun.**

ExecWeave ist ein quelloffenes, lokal ausgerichtetes Observability-Projekt, das die Aktivität von KI-Agenten in einen interaktiven Ausführungsgraphen überführt und dabei beobachtete Belege klar von Inferenz trennt.

> **Das Ereignis ist die Ground Truth. Der Graph ist eine materialisierte Sicht.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live-Ausführungsgraph" width="100%">
</p>

## Installation

ExecWeave wird auf PyPI als reguläres Python-Wheel/sdist veröffentlicht. Installieren Sie die neueste veröffentlichte Version mit:

```bash
python -m pip install -U execweave
```

Der Branch `main` kann bereits einen neueren Patch enthalten als die aktuelle PyPI-Version. Um den neuesten Mainline-Build direkt zu testen:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Für die Entwicklung:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Beobachten Sie Claude Code, OpenAI Codex oder Gemini CLI live:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

Oder erstellen Sie die vollständige Artefakt-Pipeline:

```bash
execweave record --open -- python my_agent.py
```

## Leistung und Ressourcenbedarf

ExecWeave enthält einen reproduzierbaren Benchmark für den Paket-Overhead, der aus einem installierten Wheel ausgeführt wird. Die Referenzgrafik folgt demselben Trade-off-Stil, der häufig für Vergleiche von Modellqualität und Kosten verwendet wird:

- **X-Achse:** zusätzlicher maximaler RSS des Prozessbaums, niedrig → hoch.
- **Y-Achse:** Laufzeit-Overhead, niedrig → hoch.
- **Blasenfläche:** mediane Artefaktgröße pro Lauf.
- **Bevorzugter Bereich:** unten links.

![ExecWeave Overhead-Trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Referenzumgebung: GitHub Actions Ubuntu Runner, Intel Xeon Platinum 8573C, 4 logische CPUs, Python 3.12.14, `n=7`.

| Profil | Mediane Laufzeit | Laufzeit-Overhead | Zusätzlicher maximaler RSS | Mediane Artefakte/Lauf |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |
