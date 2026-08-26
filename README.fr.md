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
  <strong>Français</strong> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**Voyez ce que les agents d’IA font réellement sur votre machine.**

ExecWeave est un projet open source, local-first, d’observabilité qui transforme l’activité des agents d’IA en un graphe d’exécution interactif tout en séparant les preuves observées des inférences.

> **L’événement est la vérité terrain. Le graphe est une vue matérialisée.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="Graphe d’exécution en direct ExecWeave" width="100%">
</p>

## Installation

ExecWeave est publié sur PyPI sous forme de wheel/sdist Python standard. Installez la dernière version publiée avec :

```bash
python -m pip install -U execweave
```

La branche `main` peut contenir un correctif plus récent que la version PyPI actuelle. Pour tester directement la dernière version de la branche principale :

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Observez Claude Code, OpenAI Codex ou Gemini CLI en direct :

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

Ou construisez la chaîne complète d’artefacts :

```bash
execweave record --open -- python my_agent.py
```

## Performances et empreinte

ExecWeave inclut un benchmark reproductible de surcharge au niveau du paquet, exécuté à partir d’un wheel installé. Le graphique de référence suit le même type de compromis que ceux couramment utilisés pour comparer qualité et coût des modèles :

- **Axe X :** mémoire RSS maximale supplémentaire de l’arbre de processus, faible → élevée.
- **Axe Y :** surcharge de temps d’exécution, faible → élevée.
- **Surface des bulles :** taille médiane des artefacts par exécution.
- **Zone préférable :** en bas à gauche.

![Compromis de surcharge ExecWeave](docs/benchmarks/v0.6.0-github-actions.svg)

Environnement de référence : runner Ubuntu GitHub Actions, Intel Xeon Platinum 8573C, 4 CPU logiques, Python 3.12.14, `n=7`.

| Profil | Temps médian | Surcharge d’exécution | RSS maximale supplémentaire | Artefacts médians/exécution |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |
