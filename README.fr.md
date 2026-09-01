# ExecWeave

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

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**Voyez ce que les agents IA font réellement sur votre machine.**

ExecWeave est un projet d’observabilité source-available et local-first qui transforme l’activité des agents IA en execution graph interactif, tout en séparant explicitement observed evidence, contenu fourni par le provider et derived inference.

> **L’Event est la ground truth. Le Graph est une materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

Ce README décrit **v0.8.5**.

## Pourquoi ExecWeave

- **Une seule surface d’inspection locale.** Les runs Live, les runs terminés et le `viewer.html` standalone utilisent le même dashboard renderer pour réunir graph, logs, conversations et détails des nœuds.
- **Une conception evidence-aware.** Les direct observations, identity links, inférences conservatrices et causal claims restent distincts au lieu d’être aplatis en une seule relation.
- **Provider-aware sans inventer de comportement caché.** ExecWeave utilise uniquement les routing / identity evidence réellement exposées par le provider ; une preuve absente reste absente.
- **Pas limité à un seul Agent.** La télémétrie OS-runtime peut envelopper n’importe quelle commande locale, et les provider adapters ajoutent des semantic evidence plus riches lorsqu’ils sont disponibles.

## Installation

Installez le dernier package publié depuis PyPI :

```bash
python -m pip install -U execweave
```

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Démarrage en 60 secondes

La télémétrie Live OS-runtime fonctionne avec **n’importe quelle commande locale**. Les noms d’Agent/runtime ci-dessous sont des exemples, pas une whitelist.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Autorisez le Hook lorsqu’il est demandé.** Lors du premier run avec une provider integration, l’Agent/IDE peut demander l’autorisation d’activer le Hook local d’ExecWeave. Choisissez **Allow / Yes**. Sans cette autorisation, la télémétrie OS-runtime peut toujours fonctionner, mais l’observabilité provider-level des tools, models, conversations et supplied content sera réduite ou absente.

Google Antigravity utilise actuellement la commande CLI `agy`. ExecWeave accepte aussi `antigravity` comme friendly alias et le résout vers `agy`. Pour Cursor, `execweave live --open -- cursor` essaie d’abord un launcher normal dans le PATH, puis le binaire standard de l’application Cursor sur macOS et Windows si nécessaire.

Pour produire les finalized run artifacts :

```bash
execweave record --open -- python my_agent.py
```

Pour garder l’Agent interactif dans le terminal de lancement tout en ouvrant une vue d’ensemble détachée :

```bash
execweave top -- codex
```

## Dashboard

ExecWeave ne change pas de viewer à la fin d’un run. Les vues Live, finished et standalone reposent sur le même dashboard model.

- **Execution graph :** affiche agents, processes, files, network endpoints, tools, model/runtime entities et les semantic relations prises en charge.
- **Conversation rounds :** le round le plus récent est immédiatement lisible ; les anciens rounds restent accessibles individuellement au lieu d’être écrasés par les nouvelles réponses.
- **Node details :** un process node montre le contexte command / PID, un file node le contexte path / history et un network node le contexte endpoint / process.
- **Large-run readability :** lorsqu’un type dépasse son budget, les membres récents restent visibles et les plus anciens sont regroupés dans un aggregate inspectable. Le seuil se règle avec `--fold-budget N`.
- **Selection clarity :** le multi-agent layout conserve une hiérarchie root / child stable et atténue les edges sans rapport lorsqu’un agent est sélectionné.

### Changements Dashboard de v0.8.3

v0.8.3 améliore la lisibilité des runs denses et multi-round sans modifier la raw evidence :

- les conversation panels sont organisés par round et n’associent plus un ancien prompt à une nouvelle reply ;
- l’état open / closed explicitement choisi par le lecteur survit au refresh Live de 800 ms ;
- les subagent responses restent attribuées à l’agent qui les a réellement produites ;
- la sélection d’un process, file ou network n’ouvre plus un detail panel vide ;
- les node types à forte cardinalité se replient selon un budget configurable au lieu de saturer le graph ;
- les lifecycle return edges ne déforment plus le rank root / child et le shared tool/model traffic utilise une routed geometry plus claire.

Ces changements concernent uniquement la presentation layer. La raw graph evidence ne change pas, et Live, finished et `viewer.html` continuent de partager un seul renderer.

## Integrations prises en charge

| Integration | OS-runtime observation quand lancé sous ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + exact subagent results lorsque le provider les expose |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + conversation/subagent routing lorsqu’il peut être validé |
| Cursor | Yes | native hooks + exact subagent task/summary routing lorsqu’il est disponible |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Seulement si le process local est lancé sous ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes lorsque le proxy configuré est lancé sous ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Observe le client local, pas le remote service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Des stable provider identifiers comme Cursor `tool_use_id`, l’identité de rollout thread Codex ou OpenCode `sessionID + callID` prouvent une logical provider identity, pas un OS PID. Le cross-agent content n’est montré que lorsque le provider expose une route, delegation ou result explicite. Si un gateway / local runtime ne fournit que du root request/response traffic, ExecWeave reste root-only et n’invente ni subagent ni hidden routing.

OpenRouter `exchange` est une caller-supplied request+response evidence, pas une transparent wire interception. LiteLLM Proxy reste une integration metadata-oriented plus étroite dans le baseline actuel. Les legacy Gemini CLI entry points restent fournis pour compatibilité, mais les nouveaux usages Google CLI doivent utiliser Antigravity (`agy`).

## Evidence model

ExecWeave conserve les evidence layers séparées au lieu d’aplatir tous les signaux dans une seule trace :

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Une relationship n’est causal que si la télémétrie sous-jacente soutient réellement ce claim. Les ponts Tool → Process conservateurs restent marqués comme derived evidence :

```text
inferred: true
causal: false
```

Une exact shared request identity entre Gateway et Model Runtime est une identity evidence, pas une causal evidence :

```text
identity_exact: true
inferred: false
causal: false
```

En cas d’ambiguïté, aucun edge n’est créé.

### Full-fidelity supplied content

Depuis **v0.6.9**, les integration points pris en charge peuvent conserver la valeur complète explicitement fournie par le provider / hook / API dans un content-addressed store SHA-256 local, tandis que le semantic event stream ne conserve qu’une reference :

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Selon l’integration, les valeurs préservées peuvent inclure prompt/message, request/response object, tool input/result, assistant response, reasoning/thinking text explicitement exposé, shell/MCP output et file content fourni par des provider hooks.

`complete_from_source: true` signifie uniquement qu’ExecWeave a stocké la valeur complète livrée par cet integration point. Cela **ne signifie pas** qu’ExecWeave a observé un hidden model state, des provider-side stages jamais exposés, une final wire request non observée ou des bytes qu’il n’a pas interceptés.

## Commandes courantes

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways et model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` est une response-only evidence. `exchange` conserve un caller-supplied request+response object et ne prétend pas effectuer une transparent interception. Les runtime catalog relations gardent leur sens source-specific : `LOADED_MODEL`, `SERVES_MODEL` et `ADVERTISES_MODEL` ne sont pas interchangeables. La catalog visibility de LM Studio reste `ADVERTISES_MODEL`, pas la preuve que les weights étaient resident en memory.

### Runtime, graph, security et integrity

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Le evidence grade d’un security finding est indépendant de sa severity. Les grades actuels sont `A`, `B`, `C`, `D` et `U` ; ce sont des evidence-strength categories, pas des probabilities ni des trust scores. Les rule packs sont des single-edge observation policies bornées et explicables ; ils n’exécutent pas de third-party code et ne prouvent pas une byte-level exfiltration.

## Run artifacts

Un provider-integrated run peut contenir :

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # after an explicit seal
```

La derived correlation ne réécrit jamais la raw runtime evidence ni la provider sidecar evidence.

## Limites et confidentialité

- Le portable collector fonctionne sous Linux, macOS et Windows. La portable filesystem observation est session-correlated plutôt que process-causal, et le polling peut manquer des activités suffisamment courtes.
- Linux dispose aussi d’un backend de référence `strace` basé sur les syscalls, qui fournit une process-attributed syscall evidence plus forte pour les executions prises en charge.
- Les collectors natifs Linux eBPF, Windows ETW et macOS Endpoint Security restent du planned work, pas des capacités actuellement revendiquées.
- Le full-fidelity provider content peut préserver des secrets présents dans prompts, tool values, model responses, shell output ou supplied files. ExecWeave **n’est pas** un secret scanner ni un content redactor généraliste.
- Conversation isolation est une attribution/display rule, pas une redaction boundary. Si un provider route explicitement du contenu vers un autre agent, ce contenu peut légitimement apparaître aux endpoints participants.
- Commands, paths, endpoints, identifiers, model metadata, prompts, tool values et content blobs peuvent tous être sensibles. Vérifiez le run directory complet avant de le partager.
- Un local integrity seal détecte les changements de fichiers par rapport à son manifest, mais il n’est pas adversary-resistant lorsque l’evidence et le manifest restent dans la même writable trust boundary.

## Performance

ExecWeave inclut bounded filesystem/viewer protection, incremental Live JSONL tailing, large-graph safety guard, detached Top et des provisional live sidecars pour les provider integrations configurées.

Le résultat de référence reproductible du `GraphAccumulator` incrémental atteint **164,273 ev/s** sur 1M synthetic events avec le workload GitHub Actions documenté. Il s’agit d’un graph-accumulation benchmark, pas d’un throughput end-to-end collector / browser.

Exécutez les benchmarks package-level sur un host/workload représentatif :

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Les reference data et la methodology se trouvent dans [`docs/benchmarks/`](docs/benchmarks/).

## Documentation

| Domaine | Documents |
| --- | --- |
| Runtime et graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways et runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust et analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| Performance | [`Benchmarks`](docs/benchmarks/README.md) |

## Contribution

Les contributions sont bienvenues, notamment autour des native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, méthodes evidence/correlation, privacy/redaction, graph UX, multi-agent conversation attribution et performance evaluation.

## Licence

Depuis v0.6.8, ExecWeave est distribué sous **PolyForm Noncommercial License 1.0.0**. L’utilisation, la modification et la redistribution non commerciales sont autorisées selon ses termes. L’usage commercial nécessite une separate written commercial license du licensor. Voir [`LICENSE`](LICENSE).
