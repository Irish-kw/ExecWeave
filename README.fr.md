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

ExecWeave est un projet d’observabilité open source et local-first qui transforme l’activité des agents d’IA en graphe d’exécution interactif tout en maintenant une séparation explicite entre observed evidence et inference.

> **L’Event est la ground truth ; le Graph est une materialized view.**

<p align="center">
  <img src="docs/assets/execweave-launch-demo-v5-x.gif" alt="ExecWeave Live execution graph" width="100%">
</p>

<!-- execweave-demo:start -->
## Reproduire cette démo

La capture ci-dessus provient d'une véritable session live ExecWeave v0.6.3. Ce workload provoque volontairement assez d'activité pour rendre l'execution graph parlant : plusieurs modules Python, des fichiers JSON/CSV, des tests, l'inspection de fichiers et des requêtes HTTP sortantes.

Exécutez un Agent CLI local sous ExecWeave, par exemple :

```bash
execweave live --open -- claude
```

Puis collez ce workload prompt dans l'Agent :

```text
Create a small Python project in ./execweave-demo with 8 modules,
generate sample JSON and CSV data, run the program and tests,
inspect the generated files, and fetch example.com plus the GitHub API.
```

Le même workload fonctionne avec `codex`, `gemini`, `cursor` ou `opencode`. Le nombre exact de nodes, edges, events, processes et endpoints dépend de l'OS, de la version de l'Agent et de l'environnement. ExecWeave enregistre le runtime evidence réellement observé ; la capture montre une exécution concrète, pas un graph attendu fixe.
<!-- execweave-demo:end -->

## Installation

ExecWeave est publié sur PyPI sous forme de wheel/sdist Python standard. Installez la dernière release avec :

```bash
python -m pip install -U execweave
```

La branche `main` peut contenir un correctif plus récent que la release PyPI actuelle. Pour tester directement le dernier build mainline :

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

La télémétrie OS-runtime Live fonctionne avec **n’importe quelle commande locale**. Les noms ci-dessous sont des exemples, pas une whitelist :

```bash
# Agent / IDE CLIs
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# Any local program
execweave live --open -- python my_agent.py

# A local model runtime launched under ExecWeave
execweave live --open -- ollama serve
```

`execweave live` diffuse les preuves process, file et network de l’arbre de commandes qu’il lance. Depuis v0.6.4, les hooks Claude/Codex/Gemini/Cursor configurés et le plugin OpenCode alimentent automatiquement le live sidecar du run ; les serveurs Ollama, llama.cpp et vLLM lancés sous ExecWeave reçoivent aussi un probe local automatique du catalogue de modèles.

#### Matrice des capacités Live

| Integration | Direct OS-runtime live | Specialized metadata | Automatiquement dans le Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Oui | `execweave-claude-record` / hooks | Oui (hook/plugin configuré) |
| OpenAI Codex | Oui | `execweave-codex-record` / hooks | Oui (hook/plugin configuré) |
| Gemini CLI | Oui | `execweave-gemini-record` / hooks | Oui (hook/plugin configuré) |
| Cursor | Oui | `execweave-cursor-record` / hooks | Oui (hook/plugin configuré) |
| OpenCode | Oui | `execweave-opencode-record` / plugin | Oui (hook/plugin configuré) |
| Ollama | Oui, lorsqu’il est lancé sous ExecWeave, par exemple `ollama serve` | `execweave-model-runtime event/probe --runtime ollama` | Oui (probe local automatique) |
| llama.cpp | Oui, lorsque son serveur local est lancé sous ExecWeave | `execweave-model-runtime event/probe --runtime llamacpp` | Oui (probe local automatique) |
| vLLM | Oui, lorsque son serveur local est lancé sous ExecWeave | `execweave-model-runtime event/probe --runtime vllm` | Oui (probe local automatique) |
| LM Studio | Oui uniquement pour un processus local lancé sous ExecWeave ; un serveur déjà actif n’est pas attaché | `execweave-model-runtime event/probe --runtime lmstudio` | Oui (probe auto après démarrage réussi avec `--port`) |
| LiteLLM Proxy | Oui, lorsque le proxy local est lancé sous ExecWeave | `execweave-inference-gateway event --gateway litellm` / configured callback | Oui (callback configuré) |
| OpenRouter | Pas de processus de service distant à lancer directement ; exécutez plutôt le client/Agent local sous `live` | `execweave-inference-gateway event/generation --gateway openrouter` | Non |

Pour un serveur Ollama déjà actif, utilisez `execweave-model-runtime probe --runtime ollama` afin de prendre un snapshot de l’état des modèles chargés. Pour OpenRouter, `live` peut observer le client local et son activité réseau, tandis que les métadonnées de routage/usage du gateway restent une couche de preuve distincte.

<!-- v0.6.4-live -->
### Observabilité Live v0.6.4

`top` garde l’Agent interactif dans le Terminal d’origine et ouvre le dashboard dans une fenêtre Terminal séparée :

```bash
execweave top -- codex
execweave top --open -- codex
```

Les mises à jour Live utilisent des snapshots/deltas incrémentaux avec un historique borné. Les Viewers Live et standalone conservent le choix Dark/Light. Sous Linux, les très grands scopes filesystem récursifs sont pré-évalués et basculent automatiquement d’inotify vers le polling si nécessaire.

v0.6.4 crée un specialized-evidence sidecar partagé pour chaque run live. Les hooks Claude/Codex/Gemini/Cursor configurés et le plugin OpenCode arrivent automatiquement dans le même Live Graph ; les serveurs Ollama, llama.cpp et vLLM lancés sous ExecWeave sont interrogés automatiquement via leur API loopback pour le catalogue de modèles. Ces événements spécialisés live sont provisoires ; après la fin de la commande, le graphe final est reconstruit depuis le merge canonical runtime + semantic. Aucune preuve absente n’est inventée.

Lancez `execweave-scalability` pour reproduire le benchmark de scalabilité ; la CI couvre 10k, 100k et 1M événements synthétiques.

#### Benchmark de scalabilité

Résultat GitHub Actions de référence pour le workload synthétique du `GraphAccumulator` incrémental (`retain_event_ids=False`) :

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

À **1 000 000 d’événements**, le graphe incrémental en mémoire ne duplique aucun raw event ID ; les raw evidence restent séparées du materialized graph. Ce benchmark mesure l’accumulation du graphe et la matérialisation des snapshots, et non le débit end-to-end du collector ou du navigateur.

Ou construisez la chaîne complète d’artefacts :

```bash
execweave record --open -- python my_agent.py
```

## Performances et empreinte

ExecWeave inclut un benchmark reproductible de surcharge au niveau du paquet, exécuté à partir d’un wheel réellement installé. Le graphique de référence suit le même type de compromis que ceux souvent utilisés pour comparer qualité et coût des modèles :

- **Axe X :** RSS maximale supplémentaire de l’arbre de processus, faible → élevée.
- **Axe Y :** surcharge de temps d’exécution, faible → élevée.
- **Surface des bulles :** taille médiane des artefacts par exécution.
- **Zone préférable :** en bas à gauche.

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Environnement de référence : runner Ubuntu GitHub Actions, Intel Xeon Platinum 8573C, 4 CPU logiques, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

Le même build a produit un wheel d’environ **113 KB** et un sdist d’environ **198 KB**. L’installation ExecWeave elle-même occupait environ **849 KB**, sans compter Python ni les dépendances.

Il s’agit volontairement d’un **reference microbenchmark** très court et fortement orienté file/process, et non d’une affirmation universelle sur tous les workloads. Comme le baseline non instrumenté ne dure que quelques centaines de millisecondes, le pourcentage de surcharge est amplifié. Relancez `execweave-overhead` sur l’hôte cible et avec un workload représentatif avant toute décision de capacité.

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Données brutes de référence et méthodologie : [`docs/benchmarks/`](docs/benchmarks/).

## Evidence layers

ExecWeave modélise volontairement quatre couches de preuves distinctes au lieu de les aplatir dans une seule trace :

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Une relation n’est marquée causal que lorsque la télémétrie sous-jacente soutient réellement cette affirmation.

## Intégrations Agent / IDE

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

### Cursor

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Cursor fournit un `tool_use_id` stable, ce qui permet une identité exacte de logical tool-call entre ses hooks pre/post.

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Le plugin OpenCode local au projet utilise l’identité exacte `sessionID + callID` et ne transmet volontairement pas le tool output.

Les exécutions intégrées à un provider conservent séparément les artefacts runtime, semantic et correlated. Les bridges Tool → Process restent des preuves dérivées conservatrices :

```text
inferred: true
causal: false
```

Une ambiguïté ne produit aucun edge.

## Intégrations Inference gateway

OpenRouter et LiteLLM Proxy sont modélisés comme `inference_gateway`, et non comme des model runtimes locaux.

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave conserve séparément requested model, resolved model, routed provider et deployment identity. Les edges provider/deployment ne sont émis que lorsque des métadonnées faisant autorité sont fournies ; ils ne sont jamais déduits d’un préfixe de nom de modèle.

Lorsque l’appelant possède une identité partagée explicite entre les observations Gateway et Model Runtime, les deux request nodes peuvent être liés sans fusionner les couches :

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` est une preuve d’identité exacte, pas une preuve causale :

```text
identity_exact: true
inferred: false
causal: false
```

Le shared request ID brut n’est pas persisté ; seul un hash d’identité dérivé de SHA-256 est stocké.

## Intégrations Model runtime

Les intégrations model runtime actuelles sont **Ollama**, **llama.cpp**, **vLLM** et **LM Studio**.

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Les runtimes compatibles OpenAI partagent le parsing response/usage et model-catalog tout en conservant leurs sémantiques de preuve propres. Les prompts, contenus générés et contenus de raisonnement ne sont pas stockés. Les chemins locaux sensibles de modèles sont expurgés ; llama.cpp applique une expurgation plus stricte aux chemins GGUF.

La visibilité d’un modèle dans le catalogue LM Studio est représentée par `ADVERTISES_MODEL`, et non comme preuve que les poids sont chargés en mémoire.

## Runtime evidence

Le collector portable fonctionne sous Linux, macOS et Windows. Linux dispose en plus d’un backend de référence `strace` basé sur les syscalls.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

Depuis v0.6.1, les commandes enfants sont résolues par un launcher cross-platform partagé avant leur exécution. Linux et macOS conservent le comportement PATH normal. Windows résout les launchers `.exe`, `.cmd` et `.bat` via PATH/PATHEXT, tandis qu’un launcher `.ps1` explicite est exécuté via PowerShell. Une CI Windows dédiée lance réellement les recorders Codex et Cursor depuis `cmd.exe` et Windows PowerShell ; l’intégration complète Cursor semantic/correlation reste également couverte par la matrice Windows, macOS et Ubuntu standard.

La surveillance filesystem portable est session-correlated plutôt que process-causal, et les processus très courts peuvent être manqués entre deux intervalles de polling. Le chemin Linux `strace` fournit des preuves syscall attribuées aux processus après la fin de la commande.

Des collectors natifs futurs sont prévus pour Linux eBPF, Windows ETW et macOS Endpoint Security.

## Patch de sécurité v0.6.2

v0.6.2 renforce la sécurité des ressources pour les sessions longues ou à forte cardinalité, sans modifier les evidence semantics ni le graph schema 0.1 :

- Les scopes filesystem récursifs trop larges, comme une racine de système de fichiers, le home utilisateur ou le parent des homes utilisateurs, ne sont plus observés récursivement tels quels ; la collecte process, network et semantic peut continuer.
- Les Viewers Standalone et Live arrêtent la SVG materialization au-delà du budget de sécurité (1 500 nodes, 4 000 edges ou environ 5 000 SVG elements) pour éviter l’épuisement de la mémoire du navigateur. L’artefact canonique `graph.json` reste complet.
- Le layout/fit du Viewer n’étale plus des tableaux arbitrairement grands dans `Math.min` / `Math.max`, et le redraw des edges pendant le déplacement des nodes est limité à une fois par animation frame.
- Le serveur Live ne lit que les nouveaux bytes ajoutés à `events.jsonl` à partir d’un byte offset et met à jour incrémentalement un `GraphAccumulator` en mémoire. Le polling de `/graph.json` ne rejoue plus tout l’historique ; une ligne JSONL terminale incomplète est mise en buffer jusqu’à son newline.
- Les changements portant uniquement sur event-count ou aggregate-count mettent à jour les stats/labels sans full topology redraw. Après dépassement du budget Viewer, `/graph.json` en live passe à un payload compact counts-only, tandis que la collecte et la validation canonique finale/full `graph.json` se poursuivent normalement.

Il s’agit d’un patch de sécurité polling + incremental-ingestion, et non d’une migration d’architecture vers SSE, SQLite, Rust ou Canvas.

## Artefacts en couches

Une exécution intégrée à un provider peut produire :

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

La couche de corrélation dérivée ne réécrit jamais les preuves brutes.

## Interactive Viewer

Le Viewer standalone est local et self-contained. Le baseline actuel comprend pan/zoom, nodes déplaçables, inspection node/edge, filtres node-type/relation/causal, **observed only**, recherche, replay selon evidence-sequence, expansion progressive des clusters, voisinages focalisés, Saved Views, sémantique explicite des edges et Correlation Summary.

## Opérations sur le graphe

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Analyse de sécurité

```bash
execweave analyze run.graph.json --output analysis.json
```

Les findings de sécurité restent explicites sur les limites de la preuve. Un possible chemin sensitive-file → network ne signifie pas qu’une exfiltration byte-level est prouvée :

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## État actuel

ExecWeave `main` est actuellement en **v0.6.4** et reste en développement actif.

Le baseline comprend la collecte runtime, la matérialisation/interrogation du graphe, les Viewers standalone/live, les intégrations semantic Claude/Codex/Gemini/Cursor/OpenCode, la corrélation conservatrice Tool → Process, les métadonnées gateway OpenRouter/LiteLLM, les métadonnées runtime Ollama/llama.cpp/vLLM/LM Studio, l’identité exacte Gateway ↔ Model Runtime request, les packages wheel/sdist publiés sur PyPI, un benchmark de surcharge reproductible, la compatibilité cross-platform du launcher, les garde-fous de navigateur pour grands graphes, le tail/cache Live JSONL incrémental et la CI cross-platform sous Python 3.10/3.12.

## Confidentialité

ExecWeave est local-first. Runtime events, semantic sidecars, graphs, reports et Viewers restent locaux par défaut. Les file contents et buffers raw read/write ne sont pas intentionnellement collectés. Les adapters natifs évitent aussi par défaut prompts/transcripts/tool output, mais commands, paths, endpoint metadata, identifiers et model metadata peuvent rester sensibles.

Vérifiez les artefacts avant de les partager.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.fr.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.fr.md)
- [`Live Graph`](docs/live-graph.fr.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.fr.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.fr.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.fr.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.fr.md)
- [`Cursor Hooks`](docs/cursor-hooks.fr.md)
- [`OpenCode Plugin`](docs/opencode-plugin.fr.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.fr.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.fr.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.fr.md)

## Contribution

Les contributions sont les bienvenues, notamment autour des native OS collectors, nouveaux Agent/IDE adapters, inference gateways, model runtimes, méthodes d’entité/corrélation, privacy/redaction, graph UX et évaluation des performances.

## Licence

Voir [`LICENSE`](LICENSE).
