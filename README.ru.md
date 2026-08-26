# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <strong>Русский</strong>
</p>

**Посмотрите, что ИИ-агенты на самом деле делают на вашем компьютере.**

ExecWeave — это открытый локальный проект для наблюдаемости, который превращает активность ИИ-агентов в интерактивный граф выполнения, сохраняя чёткое разделение между наблюдаемыми доказательствами и выводами.

> **Событие — это источник истины. Граф — материализованное представление.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="Граф выполнения ExecWeave в реальном времени" width="100%">
</p>

## Установка

ExecWeave публикуется в PyPI как стандартный Python wheel/sdist. Установите последнюю опубликованную версию:

```bash
python -m pip install -U execweave
```

В ветке `main` может находиться более свежий патч, чем в текущем релизе PyPI. Чтобы напрямую протестировать последнюю основную сборку:

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Для разработки:

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Наблюдайте за Claude Code, OpenAI Codex или Gemini CLI в реальном времени:

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

Или создайте полный набор артефактов:

```bash
execweave record --open -- python my_agent.py
```

## Производительность и ресурсы

ExecWeave включает воспроизводимый пакетный benchmark накладных расходов, который запускается из установленного wheel. Референсный график использует тот же стиль компромисса, который часто применяется при сравнении качества и стоимости моделей:

- **Ось X:** дополнительный пиковый RSS дерева процессов, от низкого к высокому.
- **Ось Y:** накладные расходы времени выполнения, от низких к высоким.
- **Площадь пузырька:** медианный размер артефактов на запуск.
- **Предпочтительная область:** нижний левый угол.

![Компромисс накладных расходов ExecWeave](docs/benchmarks/v0.6.0-github-actions.svg)

Референсная среда: Ubuntu runner в GitHub Actions, Intel Xeon Platinum 8573C, 4 логических CPU, Python 3.12.14, `n=7`.

| Профиль | Медианное время | Накладные расходы | Дополнительный пиковый RSS | Медианные артефакты/запуск |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |
