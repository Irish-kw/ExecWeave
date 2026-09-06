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

ExecWeave est un projet d’observabilité local-first pour les agents IA et les outils de développement assistés par IA. Il combine la sémantique fournie par les providers avec les preuves d’exécution observées au niveau du système d’exploitation, puis les présente dans un Execution Graph interactif sans confondre les différents niveaux de preuve.

> **Les events sont les preuves. Le graph est une vue matérialisée à partir de ces preuves.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="Démonstration du dashboard ExecWeave" width="100%">
</p>

## Pourquoi ExecWeave

Un agent peut déclarer qu’il a utilisé un outil, modifié un fichier ou contacté un service. Cette information sémantique est utile, mais elle n’est pas équivalente à ce qui a réellement été observé par le système d’exploitation. ExecWeave permet d’inspecter ces couches ensemble tout en conservant leur différence de force probante.

- **Un même Dashboard pour le Live et le Finished.** La page en cours d’exécution, le run terminé et le `viewer.html` autonome utilisent le même modèle de graph et de conversation.
- **Sémantique aware des providers.** Hooks, rollout transcripts, plugins et runtime APIs sont utilisés lorsqu’ils sont réellement exposés.
- **Preuves OS runtime.** Process, File et Network endpoint peuvent être observés indépendamment de ce que l’agent affirme.
- **Attribution fondée sur les preuves.** Direct observation, exact identity, inférence conservatrice et causal claim restent distincts.
- **Stockage local-first.** Les run artifacts restent sur votre machine tant que vous ne choisissez pas de les partager.
- **Pas limité à un seul agent.** Une commande locale ordinaire peut être observée même sans adapter spécialisé.

## Installation

Depuis PyPI :

```bash
python -m pip install -U execweave
```

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Démarrage rapide

Encapsulez n’importe quelle commande locale avec `execweave live` :

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

Pour produire surtout des artifacts finalisés :

```bash
execweave record --open -- python my_agent.py
```

Pour garder le programme interactif dans le terminal courant tout en ouvrant une vue séparée :

```bash
execweave top -- codex
```

### Autorisation de l’intégration Provider

Certains agents et IDE demandent une autorisation avant d’activer un hook ou un plugin local. Autorisez l’intégration ExecWeave si vous souhaitez obtenir des preuves Provider-level sur les Prompt, Response, Tool, Model et Conversation. Sans cette autorisation, l’observation OS runtime peut toujours fonctionner, mais la couverture sémantique peut être réduite.

Google Antigravity utilise actuellement la commande CLI `agy`. ExecWeave accepte aussi `antigravity` comme alias plus lisible.

Sous Windows, un simple `cursor` suit l’installation de Cursor indiquée par le PATH de l’utilisateur. Un chemin de launcher explicite est conservé tel quel.

## Ollama

ExecWeave prend en charge deux workflows locaux courants avec Ollama.

### Managed server capture

Démarrez le serveur Ollama via ExecWeave :

```bash
execweave live --open -- ollama serve
```

Puis utilisez Ollama normalement dans un autre terminal :

```bash
ollama run deepseek-r1:1.5b
```

Les appels SDK, requêtes locales OpenAI-compatible et requêtes `curl` envoyées au managed local endpoint peuvent être associés au même run ExecWeave. Le second terminal n’a pas besoin d’un autre wrapper ExecWeave.

Le managed relay est volontairement limité aux endpoints loopback locaux et ne réécrit pas les listeners wildcard ou exposés à l’extérieur.

### Direct client capture

Si un serveur Ollama est déjà disponible, vous pouvez encapsuler directement le client :

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

Ce mode ne démarre pas le serveur Ollama ; un upstream server accessible reste nécessaire.

## Dashboard

Le Dashboard est conçu pour garder les runs volumineux et multi-agents lisibles sans modifier les preuves sous-jacentes.

- **Execution graph :** Agent, Process, File, Network endpoint, Tool, Model/runtime entity et relations prises en charge.
- **Conversation rounds :** les rounds récents et historiques restent attachés au bon agent au lieu d’être écrasés par des messages plus récents.
- **Node details :** inspection de l’identité Process, de l’historique File, des Network endpoints, des Tools et du contenu de conversation fourni par les providers.
- **Stable live updates :** la même page se met à jour au fil du run au lieu d’être remplacée entièrement.
- **Large-run folding :** les anciens membres des types très nombreux peuvent être repliés tout en restant inspectables.
- **Selection-focused layout :** les éléments sans rapport avec la sélection courante sont visuellement atténués.

Pour les grands runs :

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## Intégrations prises en charge

| Integration | Observation OS runtime | Evidence spécialisée |
| --- | --- | --- |
| Claude Code | Oui lorsqu’il est lancé sous ExecWeave | native hooks et contenu conversation/tool fourni par le provider |
| OpenAI Codex | Oui | lifecycle hooks, validated rollout transcripts, routage agent/subagent lorsqu’il est exposé |
| Google Antigravity | Oui | passive hooks et routage conversation/subagent lorsqu’il est exposé |
| Cursor | Oui | native hooks et routage task/subagent lorsqu’il est exposé |
| OpenCode | Oui | project plugin, session/task routing, contenu fourni par le plugin |
| Ollama | Oui | managed local relay et model-runtime evidence |
| llama.cpp | Oui | model-runtime event/exchange/probe |
| vLLM | Oui | model-runtime event/exchange/probe |
| LM Studio | Lorsque le process local peut être observé | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | Lorsque le proxy local peut être observé | gateway metadata et event integration |
| OpenRouter | Client local uniquement | caller-supplied gateway event/exchange evidence |

Les identifiants tels qu’un tool-call ID, session ID, rollout thread ID ou subagent route sont des identités logiques du provider. Ce ne sont pas automatiquement des OS PID. ExecWeave ne relie les couches que lorsque les preuves disponibles le permettent.

## Modèle de preuve

ExecWeave sépare plusieurs couches principales :

```text
Agent / IDE semantics et supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

Une relation n’est marquée comme causal que si la télémétrie sous-jacente soutient réellement cette affirmation. Les ponts conservateurs restent explicitement des preuves dérivées :

```text
inferred: true
causal: false
```

Une exact shared request identity peut établir une identité sans établir une causalité :

```text
identity_exact: true
inferred: false
causal: false
```

Si l’attribution reste ambiguë, ExecWeave préfère ne pas créer l’edge plutôt que d’inventer une relation plus forte.

### Full-fidelity supplied content

Les hooks, plugins ou APIs pris en charge peuvent conserver les valeurs complètes explicitement fournies par l’intégration dans un store local adressé par SHA-256 :

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Selon l’intégration, cela peut inclure Prompt, Message, Request/Response object, Tool input/result, Assistant response, reasoning text explicitement exposé, Shell output et supplied file content.

`complete_from_source: true` signifie qu’ExecWeave a conservé la valeur complète reçue à ce point d’intégration. Cela ne signifie pas qu’ExecWeave a observé un état interne du modèle ou des données Provider jamais exposées.

## Commandes courantes

### Agent / IDE recorder

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateway / model runtime

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` représente une preuve unilatérale. `exchange` conserve une paire request/response fournie par le caller et ne prétend pas réaliser une interception transparente du trafic réseau.

### Runtime / Graph / sécurité / intégrité

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

## Run artifacts

Un run avec intégration Provider peut contenir :

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
└── integrity.json
```

Les observations brutes restent séparées des outputs semantic/correlation dérivés.

## Limites et confidentialité

- Le portable collector fonctionne sous Linux, macOS et Windows. L’observation filesystem portable est session-correlated plutôt que systématiquement process-causal, et le polling peut manquer des activités très brèves.
- Linux dispose aussi d’un backend de référence `strace`, qui fournit des preuves syscall-attributed plus fortes pour les exécutions prises en charge.
- La couverture Provider semantic dépend entièrement de ce que chaque intégration expose réellement. Les Prompt non exposés, hidden reasoning, internals de providers distants et routages invisibles ne peuvent pas être reconstruits de manière fiable.
- Le contenu full-fidelity peut contenir Credential, Secret, Source code, Prompt, Tool value, Model response, Shell output et File content.
- Conversation isolation est une règle d’attribution, pas une frontière de redaction. Un contenu explicitement routé peut légitimement apparaître chez plusieurs participants.
- Un local integrity manifest détecte les changements par rapport au manifest, mais n’est pas un système de trusted logging résistant à un adversaire si les preuves et le manifest restent dans la même writable trust boundary.
- Vérifiez l’intégralité du run directory avant de le partager.

## Développement

Tests :

```bash
python -m pytest
```

Lint :

```bash
python -m ruff check .
```

Les Issues et Pull Requests sont les bienvenues. Pour toute nouvelle intégration, distinguez clairement les preuves directement observées, celles fournies par le Provider et celles dérivées.

## Licence

ExecWeave est distribué sous la **PolyForm Noncommercial License 1.0.0**. Consultez [LICENSE](LICENSE) pour les conditions complètes.
