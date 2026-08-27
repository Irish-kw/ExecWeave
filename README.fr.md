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

ExecWeave est un projet source-available, local-first, d’observabilité qui transforme l’activité des agents IA en graphe d’exécution interactif tout en séparant explicitement les preuves observées, le contenu fourni par les providers et les inférences dérivées. À partir de v0.6.8, le projet est sous PolyForm Noncommercial 1.0.0 et l’usage commercial n’est pas autorisé.

> **L’événement est la ground truth. Le graphe est une materialized view.**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## Installation

Installez la dernière wheel/sdist publiée sur PyPI :

```bash
python -m pip install -U execweave
```

La version du package sur `main` est actuellement **v0.6.8**. La release publiée peut être en retard sur main ; pour tester exactement le mainline courant :

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

Pour le développement :

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## Démarrage rapide

La télémétrie OS-runtime live fonctionne avec **n’importe quelle commande locale**. Les noms d’agents et de runtimes ci-dessous sont des exemples, pas une liste blanche.

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **Approuvez le hook lorsqu’une autorisation est demandée.** Lors du premier run provider-intégré, l’Agent/IDE peut demander si ExecWeave est autorisé à activer son hook local. Choisissez **Allow / Yes**. Sans cette autorisation, la télémétrie OS-runtime peut continuer à fonctionner, mais l’observabilité provider-level des tools, models et supplied content sera réduite ou indisponible.

Google Antigravity utilise actuellement la commande CLI `agy`; ExecWeave accepte également `antigravity` comme alias et le résout vers `agy`. Pour Cursor, `execweave live --open -- cursor` utilise d’abord un launcher dans le PATH, puis, sous macOS/Windows, le binaire standard de l’application Cursor desktop si nécessaire.

Ou construisez le pipeline d’artefacts finalisé :

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` garde l’Agent interactif dans le terminal de lancement et ouvre ou attache le tableau de bord Top détaché selon l’environnement hôte.

## v0.6.8 : observabilité full-fidelity avec frontières de preuve explicites

v0.6.8 étend l’observabilité au-delà des métadonnées compactes. Lorsqu’un point d’intégration pris en charge fournit explicitement du contenu, ExecWeave peut conserver **la valeur complète fournie par cette source** dans un store local adressé par contenu SHA-256, tout en ne gardant qu’une référence dans le flux d’événements sémantiques.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Selon l’adapter et la surface hook/API amont, le contenu conservé peut inclure prompts/messages, objets request/response du modèle, entrées/résultats d’outils, texte reasoning/thinking lorsqu’il est explicitement exposé, sorties shell/MCP et contenu de fichier fourni par les hooks provider.

`complete_from_source: true` signifie qu’ExecWeave a stocké la valeur complète livrée par ce point d’intégration. Cela **ne signifie pas** qu’ExecWeave a observé un état caché du modèle, des étapes provider jamais exposées, une requête wire finale non vue, ou des octets qu’il n’a pas interceptés.

Le full fidelity modifie aussi la frontière de confidentialité : les secrets applicatifs intégrés au contenu sont conservés. Les transport credentials connus sont filtrés dans certaines projections de provider metadata lorsque l’adapter définit ce comportement, mais ExecWeave **n’est pas** un scanner générique de secrets ni un redactor de contenu.

### Surfaces semantic / inference prises en charge

| Integration | Observation OS-runtime si lancée sous ExecWeave | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + contenu full-fidelity fourni par le hook |
| OpenAI Codex | Yes | lifecycle hooks + contenu full-fidelity fourni par le hook |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks for invocation/tool evidence + full-fidelity values explicitly supplied to those hooks |
| Cursor | Yes | native hooks + contenu full-fidelity fourni par le hook |
| OpenCode | Yes | project plugin + contenu full-fidelity fourni par le plugin |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | uniquement si le process local est lancé par ExecWeave | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | Yes si le proxy configuré est lancé sous ExecWeave | intégration gateway callback/event actuellement orientée metadata |
| OpenRouter | observe le client local, pas le process du service distant | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` est une preuve request+response fournie par l’appelant, pas une interception wire transparente. LiteLLM Proxy reste actuellement une intégration plus étroite, orientée metadata.

## Couches de preuve

ExecWeave garde les couches de preuve séparées au lieu de les aplatir en une seule trace :

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

Une relation n’est causale que lorsque la télémétrie sous-jacente soutient cette affirmation. Les ponts Tool → Process restent des preuves dérivées conservatrices :

```text
inferred: true
causal: false
```

En cas d’ambiguïté, aucun edge n’est créé. Une identité de requête exacte partagée entre Gateway et Model Runtime reste une preuve d’identité, pas une preuve causale :

```text
identity_exact: true
inferred: false
causal: false
```

## Intégrations Agent / IDE

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

Les recorders intégrés aux providers conservent séparément les artefacts runtime bruts, semantic et correlated. Des identifiants provider stables tels que Cursor `tool_use_id` ou OpenCode `sessionID + callID` prouvent une identité logique chez le provider ; ils ne sont pas des PID OS. Les anciens entry points Gemini CLI restent empaquetés pour compatibilité avec les installations existantes ; les nouveaux usages Google CLI doivent utiliser Antigravity (`agy`).

## Inference gateways et model runtimes

Capturez les preuves gateway OpenRouter ou LiteLLM :

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

Capturez les preuves model-runtime pour Ollama, llama.cpp, vLLM ou LM Studio :

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` est une preuve response-only ; `exchange` stocke un objet request+response fourni par l’appelant et ne prétend pas effectuer une interception transparente. Les relations de catalogue gardent leur sémantique propre à la source : `LOADED_MODEL`, `SERVES_MODEL` et `ADVERTISES_MODEL` ne sont pas interchangeables. La visibilité catalogue LM Studio reste `ADVERTISES_MODEL`, sans prouver que les poids sont résidents en mémoire.

## Security analysis, evidence grades et rule packs bornés

Lancez l’analyse intégrée :

```bash
execweave analyze run.graph.json --output analysis.json
```

Les findings exposent un evidence grade indépendant de la severity. Les grades actuels sont `A`, `B`, `C`, `D` et `U`, allant de l’attribution syscall directe à la provenance inferred/unknown. Ces grades sont des catégories de force de preuve, **pas des probabilités ni des trust scores**.

Les rule packs locaux ajoutent des politiques d’observation **single-edge**, bornées et explicables, sans exécuter de code tiers :

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Un rule pack ne peut pas exécuter du code, définir des programmes regex/path, ni affirmer un data flow au niveau byte ou une exfiltration. Les findings issus des rule packs restent observation-only.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Intégrité des runs

Scellez un run terminé puis vérifiez que son inventaire de fichiers réguliers n’a pas changé depuis le seal :

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Le manifest déterministe enregistre taille/SHA-256 et rejette les liens symboliques. Un fichier manquant, modifié, remplacé ou nouvellement ajouté après le seal fait échouer la vérification.

Ce seal local n’est volontairement **pas** décrit comme une preuve anti-altération résistante à un adversaire lorsque les preuves et le manifest restent dans la même frontière writable. Le manifest enregistre `malicious_writer_resistance: false` et `external_trust_anchor: false`. Pour une garantie plus forte, copiez/protégez le digest du manifest en dehors de cette frontière.

## Runtime evidence et opérations de graphe

Le collector portable fonctionne sous Linux, macOS et Windows. Linux dispose aussi d’un backend de référence `strace` fondé sur les syscalls.

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

L’observation filesystem portable est session-correlated et non process-causal ; le polling peut manquer une activité suffisamment brève. Linux `strace` fournit une preuve syscall process-attributed plus forte pour les exécutions prises en charge. Des collectors natifs Linux eBPF, Windows ETW et macOS Endpoint Security restent planifiés.

## Performance et sécurité des grands runs

v0.6.3 a ajouté des protections filesystem/viewer bornées, le tail Live JSONL incrémental et des garde-fous pour les grands graphes. v0.6.4 a ajouté Top détaché et le sidecar live provisoire partagé pour les intégrations provider configurées. Ces capacités restent en v0.6.8. Cette release n’a **pas** migré Live vers SSE, le stockage d’artefacts vers SQLite, le renderer vers Canvas/WebGL, ni les collectors vers Rust simplement pour changer d’architecture.

Le résultat de référence reproductible de l’`GraphAccumulator` incrémental atteint **164,273 ev/s** à 1M d’événements synthétiques sur le workload GitHub Actions documenté. Il s’agit d’un benchmark d’accumulation de graphe, pas d’un débit end-to-end collector/browser.

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Données de référence et méthodologie : [`docs/benchmarks/`](docs/benchmarks/).

## Artefacts en couches

Un run intégré à un provider peut contenir :

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # après un seal explicite
```

La corrélation dérivée ne réécrit jamais les preuves runtime brutes ou le sidecar provider.

## Confidentialité

ExecWeave est local-first : captures, blobs de contenu, graphes, rapports et viewers restent locaux par défaut. Le **collector OS runtime** ne capture pas intentionnellement le contenu des fichiers ni les buffers raw read/write. Cette frontière ne doit pas être confondue avec le **provider full-fidelity content store** de v0.6.8 : si un hook/API pris en charge fournit explicitement prompt, arguments/résultats d’outil, réponse modèle, reasoning/thinking text, sortie shell, contenu de fichier ou autre valeur sensible, ExecWeave peut conserver cette valeur intégralement.

Ne supposez pas que le contenu a été secret-redacted. Commandes, chemins, endpoint metadata, identifiants, model metadata, prompts, valeurs d’outil et content blobs peuvent tous être sensibles. Vérifiez tout le run directory avant partage.

## État actuel

ExecWeave `main` est actuellement en **v0.6.8** et en phase de release hardening. Le dernier package/release public peut être en retard sur main jusqu’à la publication explicite d’une GitHub Release ; le workflow de publication vérifie que le release tag correspond exactement à la package version avant upload sur PyPI.

v0.6.8 combine collection runtime cross-platform, graphes d’exécution matérialisés, viewers standalone/live, corrélation provider↔runtime conservatrice, preuves provider full-fidelity adressées par contenu, evidence grades, rule packs bornés, contrat explicite runtime threat/fidelity et scellement local d’intégrité avec une frontière de confiance honnête. Les preuves observées et l’inférence restent séparées par conception.

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

Les contributions sont bienvenues, notamment pour les collectors OS natifs, adapters Agent/IDE, inference gateways, model runtimes, méthodes evidence/correlation, privacy/redaction, graph UX et évaluation des performances.

## License

ExecWeave v0.6.8 et les versions ultérieures sont sous **PolyForm Noncommercial License 1.0.0**. L’usage, la modification et la redistribution non commerciaux sont permis selon ces termes ; tout usage commercial nécessite une licence commerciale écrite distincte. Les versions antérieures déjà publiées sous MIT restent soumises aux conditions qui les accompagnaient. Voir [`LICENSE`](LICENSE).
