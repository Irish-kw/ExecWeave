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

**Voyez ce que les agents IA font réellement sur votre machine.**

ExecWeave est un projet d’observabilité source-available et local-first qui transforme l’activité des agents IA en execution graph interactif, tout en séparant explicitement observed evidence, provider content et derived inference.

> **L’Event est la ground truth. Le Graph est une materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Installation

Installez le dernier wheel/sdist publié depuis PyPI :

```bash
python -m pip install -U execweave
```

La version courante est **v0.8.1**.

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Démarrage rapide

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

> **Autorisez le Hook lorsqu’il est demandé.** Lors du premier lancement avec une provider integration, l’Agent/IDE peut demander l’autorisation d’activer le Hook local d’ExecWeave. Choisissez **Allow / Yes**. Sans cette autorisation, la télémétrie OS-runtime peut toujours fonctionner, mais l’observabilité provider-level des tools, models et supplied content sera réduite ou absente.

Google Antigravity utilise actuellement la commande CLI `agy`. ExecWeave accepte également `antigravity` comme alias convivial et le résout vers `agy`. Pour Cursor, `execweave live --open -- cursor` essaie d’abord un launcher normal dans le PATH, puis utilise le binaire standard de l’application Cursor sur macOS et Windows si nécessaire.

Pour produire le pipeline d’artefacts finalisé :

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` garde l’Agent interactif dans le terminal de lancement tout en ouvrant ou en attachant le dashboard Top détaché selon l’environnement hôte.

**v0.8.1 — chaque tour, et chaque nœud, dit ce qu'il contient.** Un run se limite rarement à une seule question, et le panneau n'avait de place que pour une : il associait la plus ancienne question à la plus récente réponse, si bien qu'un run de deux tours montrait la première question à côté de la réponse de la seconde, tandis que la réponse propre au premier tour restait inaccessible. Le tour est désormais l'unité — le plus récent est ouvert, les plus anciens se replient en une ligne nommant leur propre moment et leur propre question, et le repli d'un subagent porte l'horodatage et la formulation du tour racine dont il provient. Deux subagents perdaient aussi leur Réponse : la règle qui empêche le préambule partagé d'un provider d'être lu comme l'assignation d'un agent correspondait à tout texte long apparaissant sous deux agents, or la réponse d'un enfant apparaît à la fois dans son propre enregistrement et dans celui de son parent. Cette règle ne touche plus que les messages entrants, de sorte que ce qu'un agent a écrit reste le sien, quel que soit le nombre de fois où le run le répète. Sélectionner un processus, un fichier ou un point de terminaison réseau ne dessine plus un panneau vide : chacun dit ce qu'il est — une ligne de commande avec son pid et son parent, un chemin avec l'historique qui l'a touché, une adresse avec le processus qui l'a atteinte. Et un type encombré au-delà de son budget garde ses membres les plus récents dessinés tandis que les plus anciens se replient en un seul nœud qui nomme encore chacun de ceux qu'il contient, si bien qu'un run touchant mille chemins reste lisible sans en perdre un seul. Les conversations multi-agent provider-neutral et agent-local que chaque agent possède sont les mêmes enregistrements qu'auparavant ; ce qui a changé, c'est qu'un lecteur peut désormais les atteindre toutes plutôt qu'une seule. Le seuil à partir duquel un type se replie est `--fold-budget N`, disponible sur chaque commande qui produit un tableau de bord : un déploiement dont les agents écrivent des centaines de fichiers choisit son propre nombre au lieu de modifier le paquet.

Le dashboard unifié rassemble execution graph, logs et conversation records dans le même flux d’inspection. Les runs finalisés génèrent `conversations.md` et `conversations.json`, et les transcripts provider validés sont copiés dans le content store SHA-256 local au run. Claude Code, OpenAI Codex, Cursor, OpenCode et Google Antigravity exploitent chacun le niveau de multi-agent evidence réellement exposé par leur integration. Lorsqu’un gateway ou un local runtime n’expose que des request/response root, ExecWeave affiche uniquement cette root conversation et n’invente ni subagent ni hidden routing.

## v0.6.9 : full-fidelity observability avec des evidence boundaries explicites

v0.6.9 étend l’observabilité provider/runtime au-delà des metadata compactes. Lorsqu’un integration point supporté fournit explicitement du contenu, ExecWeave peut préserver la **valeur complète fournie** dans un content-addressed store SHA-256 local, tout en ne conservant qu’une reference dans le semantic event stream.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Selon l’adapter et la surface hook/API upstream, le contenu préservé peut inclure prompts/messages, model request/response objects, tool inputs/results, assistant responses, reasoning/thinking text lorsqu’il est explicitement exposé, shell/MCP output et file content fourni par les provider hooks.

`complete_from_source: true` signifie qu’ExecWeave a stocké la valeur complète remise par cet integration point. Cela **ne signifie pas** qu’ExecWeave a observé un hidden model state, des étapes provider-side jamais exposées, une requête wire finale non observée ou des bytes qu’il n’a pas interceptés.

Le full fidelity modifie aussi la privacy boundary : les application-level secrets présents dans le contenu sont préservés. Les transport credentials connus ne sont filtrés que dans certaines provider-metadata projections lorsque l’adapter définit explicitement ce comportement. ExecWeave **n’est pas** un secret scanner ni un content redactor généraliste.

### Surfaces semantic / inference supportées

| Integration | OS-runtime observation quand lancé sous ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + subagent result lorsque le provider l’expose |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + routing agent-local task/message/final-response |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + conversation/subagent routing lorsqu’il peut être validé |
| Cursor | Yes | native hooks + exact subagent task/summary routing lorsqu’il est disponible |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | Seulement si le process local est lancé sous ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes si le proxy configuré est lancé sous ExecWeave | metadata-oriented gateway callback/event integration |
| OpenRouter | Observe le client local, pas le process du service distant | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` correspond à une caller-supplied request+response evidence, pas à une transparent wire interception. LiteLLM Proxy reste une integration plus étroite et metadata-oriented dans le baseline actuel. La projection provider-neutral des conversations ne transforme jamais une evidence provider absente en agent relationship fabriquée.

## Evidence layers

ExecWeave conserve les evidence layers séparées au lieu d’aplatir tous les signaux en une seule trace :

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Une relation n’est causal que si la télémétrie sous-jacente permet réellement cette conclusion. Les bridges Tool → Process restent des derived evidence conservatrices :

```text
inferred: true
causal: false
```

En cas d’ambiguïté, aucun edge n’est créé. Une exact shared request identity entre Gateway et Model Runtime reste une identity evidence plutôt qu’une causal evidence :

```text
identity_exact: true
inferred: false
causal: false
```

## Agent / IDE integrations

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude

execweave-codex-hook --print-config
execweave-codex-record --open -- codex

execweave-antigravity-hook --print-config
execweave-antigravity-record --open -- antigravity

execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor

execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Les recorders provider-integrated conservent séparément les artefacts raw runtime, semantic, correlated et conversation. Des identifiers provider stables comme Cursor `tool_use_id`, la rollout thread identity de Codex ou OpenCode `sessionID + callID` prouvent une logical provider identity ; ce ne sont pas des OS PIDs. Le contenu cross-agent n’est affiché que lorsque le provider expose explicitement une route, une delegation ou un result. Les anciens entry points Gemini CLI restent packagés pour les installations existantes, mais les nouveaux usages Google CLI doivent utiliser Antigravity (`agy`).

## Inference gateways et model runtimes

Capturez l’evidence d’un gateway OpenRouter ou LiteLLM :

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Capturez l’evidence model-runtime pour Ollama, llama.cpp, vLLM ou LM Studio :

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` est une response-only evidence. `exchange` stocke un caller-supplied request+response object et n’affirme pas une interception transparente. Les runtime catalog relations conservent leur sens propre à la source : `LOADED_MODEL`, `SERVES_MODEL` et `ADVERTISES_MODEL` ne sont pas interchangeables. La catalog visibility de LM Studio reste `ADVERTISES_MODEL`, pas la preuve que les weights étaient resident in memory.

## Security analysis, evidence grades et bounded rule packs

Lancez l’analyse intégrée :

```bash
execweave analyze run.graph.json --output analysis.json
```

Les findings exposent un evidence grade indépendant de la severity. Les grades actuels sont `A`, `B`, `C`, `D` et `U`, depuis la direct syscall attribution jusqu’à la provenance inferred/unknown. Ce sont des catégories de force d’evidence, **pas des probabilités ni des trust scores**.

Les local rule packs ajoutent des policies **single-edge observation** bornées et explicables sans exécuter de code tiers :

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Les rule packs ne peuvent pas exécuter de code, définir des programmes regex/path ni affirmer un byte-level data flow ou une exfiltration. Leurs findings restent observation-only.

Les security findings rendent également explicites les non-claims plus forts :

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

Scellez un run terminé puis vérifiez plus tard que son regular-file inventory n’a pas changé depuis le seal :

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Le manifest déterministe enregistre file size/SHA-256 et refuse les symbolic links. Il détecte les regular files manquants, modifiés, remplacés ou nouvellement ajoutés après le seal.

Ce local seal n’est volontairement **pas** présenté comme adversary-resistant tamper evidence lorsque l’evidence et le manifest restent dans la même writable trust boundary. Le manifest enregistre `malicious_writer_resistance: false` et `external_trust_anchor: false`. Pour une garantie plus forte, copiez ou protégez le digest du manifest en dehors de cette boundary.

## Runtime evidence et graph operations

Le portable collector fonctionne sous Linux, macOS et Windows. Linux dispose également d’un backend de référence `strace` basé sur les syscalls.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

La portable filesystem observation est session-correlated plutôt que process-causal, et le polling peut manquer des activités très courtes. Linux `strace` fournit une evidence syscall plus fortement attribuée au process pour les exécutions supportées. Les futurs collectors natifs restent prévus pour Linux eBPF, Windows ETW et macOS Endpoint Security.

## Performance et sécurité des grands runs

ExecWeave inclut des protections bornées du filesystem/viewer, un tailing Live JSONL incrémental, des large-graph safety guards, un Top détaché et des provisional live sidecars pour les provider integrations configurées.

Le résultat de référence reproductible de l’incremental `GraphAccumulator` atteint **164,273 ev/s** sur 1M synthetic events dans le workload GitHub Actions documenté. Il s’agit d’un benchmark de graph accumulation, pas du throughput end-to-end collector/browser.

Relancez le package-level overhead benchmark sur un host/workload représentatif :

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Consultez [`docs/benchmarks/`](docs/benchmarks/) pour les données de référence et la méthodologie.

## Layered artifacts

Un run provider-integrated peut contenir :

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
└── integrity.json            # après un seal explicite
```

La derived correlation ne réécrit jamais la raw runtime evidence ni les provider sidecars.

## Privacy

ExecWeave est local-first : captures, content blobs, graphs, reports et viewers restent locaux par défaut. Le **OS runtime collector** ne capture pas intentionnellement les file contents ni les raw read/write byte buffers. Cette boundary ne doit pas être confondue avec le **provider full-fidelity content store introduit en v0.6.9** : les hooks/APIs supportés peuvent fournir explicitement prompts, tool arguments/results, model responses, reasoning/thinking text, shell output, file content ou d’autres valeurs sensibles, qu’ExecWeave peut alors préserver complètement.

La conversation isolation est une règle d’attribution et d’affichage, pas une redaction boundary. Si un provider envoie explicitement le contenu d’Agent 1 à Agent 2, cette routed evidence peut légitimement apparaître aux endpoints participants. Ne supposez pas que le contenu a été secret-redacted. Commands, paths, endpoint metadata, identifiers, model metadata, prompts, tool values et content blobs peuvent tous être sensibles. Vérifiez l’intégralité du run directory avant de le partager.

## État actuel

v0.8.1 combine cross-platform runtime collection, materialized execution graphs, standalone/live dashboards, conservative provider↔runtime correlation, full-fidelity content-addressed provider evidence, attributable multi-agent execution traces, accès direct aux conversations run-local, agent-local conversation isolation dans les projections provider-neutral, des panneaux de conversation par tour et des nœuds non-agent qui se décrivent eux-mêmes avec un repli par type dans les dashboards standalone et live. Chaque integration conserve uniquement la meilleure identity/routing evidence réellement exposée par le provider et s’abstient lorsque cette evidence manque. Observed evidence et inference restent séparées par conception.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.fr.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.fr.md)
- [`Live Graph`](docs/live-graph.fr.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.fr.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.fr.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.fr.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.fr.md)
- [`OpenCode Plugin`](docs/opencode-plugin.fr.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.fr.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.fr.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.fr.md)
- [`Evidence Grades`](docs/evidence-grades.fr.md)
- [`Rule Packs`](docs/rule-packs.fr.md)
- [`Run Integrity`](docs/run-integrity.fr.md)
- [`Security Analysis`](docs/security-analysis.fr.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## Contribution

Les contributions sont bienvenues, notamment autour des native OS collectors, Agent/IDE adapters, inference gateways, model runtimes, méthodes evidence/correlation, privacy/redaction, graph UX, attribution des multi-agent conversations et performance evaluation.

## License

Depuis v0.6.8, ExecWeave est distribué sous **PolyForm Noncommercial License 1.0.0**. L’utilisation, la modification et la redistribution non commerciales sont permises selon ses conditions. L’utilisation commerciale nécessite une commercial license écrite distincte du licensor. Voir [`LICENSE`](LICENSE).
