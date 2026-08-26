<!-- i18n-nav:start -->
<p align="center">
  <a href="claude-code-hooks.md">English</a> |
  <a href="claude-code-hooks.zh-TW.md">繁體中文</a> |
  <a href="claude-code-hooks.zh-CN.md">简体中文</a> |
  <a href="claude-code-hooks.ja.md">日本語</a> |
  <a href="claude-code-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="claude-code-hooks.de.md">Deutsch</a> |
  <a href="claude-code-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Hooks Claude Code

ExecWeave inclut un adaptateur natif de hooks de commande Claude Code qui enregistre la télémétrie sémantique du fournisseur dans un sidecar JSONL local distinct.

L’adaptateur complète la collecte runtime OS. Il ne remplace **pas** le collecteur portable ni le collecteur Linux `strace`.

## Ce qui est enregistré

L’adaptateur actuel consomme les événements de hook Claude Code suivants :

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `SubagentStart`
- `SubagentStop`

Il peut matérialiser des entités sémantiques telles que :

```text
Claude Code
  |
  +--REQUESTED_TOOL_CALL--> tool_call
  |                           |
  |                           +--USES_TOOL-------> Bash / Read / Edit / Write / ...
  |                           +--DECLARED_COMMAND-> command
  |                           +--DECLARED_TARGET--> file metadata
  |                           +--VIA_MCP----------> MCP server
  |
  +--SPAWNED_SUBAGENT-------> subagent
  +--USED_MODEL-------------> model        when SessionStart exposes one
```

Les noms d’outils MCP suivant la convention Claude Code `mcp__<server>__<tool>` sont normalisés en nœuds `mcp_server` et `tool` séparés.

## Installer la configuration des hooks

Installez d’abord ExecWeave afin que les scripts console soient disponibles :

```bash
python -m pip install -e ".[dev]"
```

Générez le fragment de configuration :

```bash
execweave-claude-hook --print-config
```

Fusionnez l’objet `hooks` généré dans l’un des fichiers de paramètres JSON pris en charge par Claude Code :

- `~/.claude/settings.json` pour les hooks utilisateur globaux
- `.claude/settings.json` pour une configuration de projet partageable
- `.claude/settings.local.json` pour une configuration locale au projet qui ne doit pas être commitée

N’écrasez pas les paramètres Claude Code sans rapport lors de l’ajout du fragment.

Le menu `/hooks` de Claude Code permet d’inspecter les hooks actuellement configurés.

L’adaptateur utilise des hooks de commande et est fail-open par défaut : une erreur d’analyse de télémétrie ou de système de fichiers est écrite sur stderr mais renvoie un succès, afin que l’observabilité ExecWeave ne bloque pas un appel d’outil de l’Agent. `--strict` est disponible pour déboguer le hook lui-même, et non comme politique de sécurité runtime.

## Recommandé : enregistrement runtime + sémantique + corrélation en une commande

Une fois les hooks installés, utilisez le workflow lié à l’exécution :

```bash
execweave-claude-record --open -- claude
```

Sous Linux, `--backend auto` continue de préférer le backend `strace` plus fort lorsqu’il est disponible. Sous macOS et Windows, il utilise le backend portable.

`execweave-claude-record` associe un chemin sidecar unique à cette exécution ExecWeave **dans le processus CLI dédié**. Claude et ses commandes de hook héritent de ce chemin ; deux processus ExecWeave Claude-record lancés indépendamment n’ont donc pas besoin de deviner quel sidecar sémantique appartient à quelle capture runtime.

Si Claude émet des événements de hook sémantiques, l’enregistreur exécute trois étapes de preuve explicites :

```text
preuve runtime
    ↓ fusion sémantique
preuve runtime + sémantique
    ↓ corrélation conservatrice
runtime + sémantique + corrélation inférée
```

Le répertoire d’exécution garde chaque étape séparée :

```text
.execweave/runs/<run-id>/
├── events.jsonl              # preuve runtime uniquement
├── graph.json                # graphe runtime uniquement
├── viewer.html               # visualiseur runtime uniquement
├── semantic.jsonl            # preuve sémantique des hooks Claude uniquement
├── events.semantic.jsonl     # flux runtime + sémantique validé
├── graph.semantic.json       # graphe runtime + sémantique
├── viewer.semantic.html      # visualiseur runtime + sémantique
├── events.correlated.jsonl   # runtime + sémantique + ponts inférés
├── graph.correlated.json     # graphe incluant ponts inférés
└── viewer.correlated.html    # visualiseur avec arêtes inférées stylées séparément
```

`--open` ouvre `viewer.correlated.html` lorsqu’une preuve sémantique a été observée. Si les hooks ne sont pas installés ou si aucun événement pris en charge ne se déclenche, ExecWeave indique `semantic_status: "no_events"`, `correlation_status: "not_run_no_semantic_events"` et revient au visualiseur runtime uniquement.

Si des preuves sémantiques existent mais qu’aucun candidat Tool → Process unique et sûr ne subsiste, ExecWeave produit quand même les artefacts corrélés avec `correlation_status: "completed_no_matches"`. Aucune arête inférée n’est fabriquée.

La fenêtre de corrélation maximale par défaut est de 3000 ms. Elle peut être modifiée explicitement :

```bash
execweave-claude-record \
  --correlation-window-ms 1500 \
  --open \
  -- claude
```

Choisissez explicitement un répertoire si nécessaire :

```bash
execweave-claude-record \
  --output-dir my-claude-run \
  --open \
  -- claude
```

Le workflow lié à l’exécution préserve `events.jsonl`, `semantic.jsonl` et `events.semantic.jsonl`. La corrélation est écrite uniquement dans le flux distinct `events.correlated.jsonl`.

## Emplacement du sidecar pour un hook autonome

Lorsque `execweave-claude-hook` est utilisé hors de l’enregistreur lié à l’exécution, chaque session Claude écrit par défaut dans :

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

L’identifiant de session est nettoyé avant utilisation comme nom de fichier.

Vous pouvez remplacer ce comportement via :

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

ou une commande de hook explicite telle que :

```bash
execweave-claude-hook --sidecar /path/to/semantic.jsonl
```

Pour des sessions autonomes parallèles, préférez le chemin automatique limité à la session plutôt que de faire pointer plusieurs sessions Claude vers un sidecar fixe.

## Avancé : fusion et corrélation manuelles

La chaîne générique sémantique et de corrélation reste disponible si vous disposez déjà d’une capture runtime et d’un sidecar sémantique :

```bash
execweave semantic-merge \
  run.jsonl \
  semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl

execweave correlate run.semantic.jsonl \
  --output run.correlated.jsonl

execweave validate run.correlated.jsonl
execweave graph run.correlated.jsonl \
  --output run.correlated.graph.json
execweave view run.correlated.graph.json \
  --output run.correlated.html \
  --open
```

Le flux runtime original et le sidecar sémantique restent inchangés.

## Limite Tool → Process et corrélation v0.1

L’entrée de hook de commande Claude Code identifie l’invocation logique de l’outil (`tool_name`, `tool_use_id` et l’entrée outil), mais ne fournit pas le PID réel du processus enfant créé par un appel Bash.

L’adaptateur natif n’émet donc volontairement **pas** une relation observée telle que :

```text
Bash tool_call --SPAWNED_PROCESS--> process:1234
```

sans preuve supplémentaire.

Vous pouvez néanmoins voir à la fois les preuves sémantiques et OS dans le même graphe fusionné :

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call --DECLARED_COMMAND--> "npm test"

session --LAUNCHED--> Claude process --SPAWNED--> shell/process ...
```

ExecWeave n’affirme pas que ces chemins appartiennent à la même chaîne causale simplement parce que leurs horodatages ou chaînes de commande se ressemblent.

L’étape de corrélation v0.1 est volontairement conservatrice :

- la fenêtre de recherche est bornée et tronquée par le résultat de l’outil ou le prochain appel d’outil déclaré lorsqu’ils sont disponibles
- l’identité de l’exécutable peut être soutenue par des preuves exactes d’exécutable/processus/cmdline
- les chemins d’exécutable canoniques peuvent résoudre des chemins équivalents sans appariement flou du nom
- les processus lanceurs peuvent utiliser en repli un appariement `argv[1:]` exact, non vide et préservant la longueur
- un pont n’est émis que lorsqu’exactement un candidat de processus subsiste
- des candidats ambigus n’émettent aucun pont
- les commandes shell composées non prises en charge et les builtins shell n’émettent aucun pont
- aucun appariement flou de version/nom n’est utilisé
- la proximité temporelle seule n’est jamais suffisante

Un pont dérivé est représenté comme :

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

et porte toujours une sémantique équivalente à :

```json
{
  "backend": "inference",
  "causal": false,
  "inferred": true,
  "inference_method": "...",
  "confidence": 0.8,
  "confidence_semantics": "heuristic_score_not_probability",
  "supporting_event_ids": ["..."]
}
```

La méthode et le score exacts dépendent des preuves de support. Le champ de confiance est un score heuristique destiné à communiquer la force des preuves ; il n’est explicitement **pas une probabilité calibrée**.

Le Viewer autonome rend les relations inférées séparément des arêtes observées causales et non causales, les étiquette `· inferred` et expose leurs métadonnées de preuve lorsqu’elles sont sélectionnées. Un pont inféré n’est jamais promu en attribution de processus observée.

## Comportement de confidentialité

L’adaptateur natif évite volontairement plusieurs payloads à haut risque :

- le contenu de fichier `Write`/`Edit` n’est pas persisté par l’adaptateur
- `PostToolUse.tool_response` n’est pas persisté
- seuls les noms de clés d’entrée sont conservés pour les métadonnées génériques d’appel d’outil
- les outils orientés fichier conservent le chemin déclaré, pas son contenu
- les commandes Bash/PowerShell sont conservées car elles sont nécessaires pour expliquer l’exécution, mais le texte de commande est limité à 4096 caractères
- le texte d’échec est limité à un résumé d’erreur court

Les chemins et commandes peuvent toujours contenir credentials, tokens, noms de clients, noms d’hôtes internes ou autres informations sensibles. Traitez les sidecars sémantiques comme des métadonnées runtime sensibles et examinez-les avant de les partager.

## Sémantique des preuves

Les arêtes produites directement par l’adaptateur Claude incluent :

```json
{
  "backend": "semantic",
  "attribution": "claude_hook",
  "evidence_source": "provider_hook",
  "provider": "claude",
  "causal": false
}
```

`causal: false` ne signifie pas que le hook Claude a été fabriqué. Cela signifie qu’une relation logique au niveau fournisseur n’est pas promue au niveau d’affirmation plus fort d’attribution d’exécution OS d’ExecWeave.

Les événements de corrélation sont des preuves dérivées distinctes avec `backend: "inference"`, `inferred: true` et `causal: false`. Ils ne modifient pas les preuves runtime brutes ni celles du hook Claude.

Voir [`Télémétrie sémantique`](semantic-telemetry.fr.md) pour le contrat générique de fusion et les règles de référence de processus.
