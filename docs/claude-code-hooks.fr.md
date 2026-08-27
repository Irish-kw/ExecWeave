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

# Claude Code Hooks

ExecWeave inclut un adapter command-hook natif pour Claude Code. Il enregistre les preuves semantic/content fournies par le provider dans un sidecar local tout en les gardant distinctes des preuves OS runtime indépendantes. Les hooks provider expliquent ce que Claude Code a effectivement exposé ; ils ne remplacent pas le collector portable ou Linux `strace` et n’établissent pas, à eux seuls, une causalité vers un process OS.

**Surface de hooks actuelle.** `execweave-claude-hook --print-config` enregistre actuellement :

- `SessionStart`
- `UserPromptSubmit`
- `MessageDisplay`
- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PostToolBatch`
- `SubagentStart`
- `SubagentStop`
- `Stop`
- `StopFailure`

La configuration est fail-open par défaut : les erreurs de télémétrie ou de stockage sont signalées sans bloquer intentionnellement une opération de l’Agent. Utilisez `--strict` en mode debug si vous voulez un code non-zero en cas d’erreur de télémétrie.

## Configuration et enregistrement

Installez ExecWeave, générez le fragment de settings pris en charge, fusionnez-le dans les settings Claude Code, puis utilisez le recorder lié au run :

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

`execweave-claude-record` lie un sidecar semantic unique au run via l’environnement du child process. Les preuves runtime, semantic et correlated restent dans des artefacts séparés.

```text
runtime evidence
    ↓ semantic merge
runtime + semantic evidence
    ↓ conservative correlation
runtime + semantic + inferred correlation
```

Si aucun hook Claude pris en charge n’arrive, le recorder retombe sur les artefacts runtime-only. Si des preuves semantic existent mais qu’aucun candidat Tool → Process unique et suffisamment supporté ne subsiste, aucun bridge n’est fabriqué.

## Contenu full-fidelity en v0.6.5

L’adapter Claude n’est plus limité à des résumés de metadata bornés. Lorsqu’un hook fournit explicitement du contenu, v0.6.5 stocke la valeur complète fournie par la source dans le store local SHA-256 content-addressed et ne met qu’une référence dans le sidecar semantic.

Les régressions couvertes incluent :

- le `UserPromptSubmit.prompt` complet, y compris de grandes valeurs ;
- l’entrée tool complète, y compris le contenu `Write`/`Edit` et les valeurs applicatives présentes dans l’objet d’entrée ;
- le `PostToolUse.tool_response` structuré complet lorsqu’il est fourni ;
- la sérialisation du résultat tool visible par le modèle fournie par `PostToolBatch` ;
- le texte/delta assistant de `MessageDisplay` avec les metadata d’ordre disponibles ;
- les messages assistant finaux du main Agent et des subagents fournis par les événements stop.

Les transport credentials connus sont filtrés uniquement dans la projection provider-metadata séparée lorsque l’adapter les reconnaît. Ce filtrage **ne nettoie pas** la valeur full content elle-même. Un secret intégré dans un prompt, une entrée tool, un body de fichier, un résultat tool ou un message assistant reste dans la preuve full-fidelity conservée.

`content_complete_from_source: true` signifie qu’ExecWeave a stocké la valeur complète fournie par le hook Claude. Cela n’affirme pas qu’ExecWeave a lu un transcript non fourni, observé un hidden model state ou capturé une étape provider absente du hook payload.

## Entités logiques et identité des tools

Les événements hook Claude peuvent matérialiser des relations provider-level telles que :

```text
Claude Code --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL-------------> tool
tool_call --DECLARED_COMMAND------> command
tool_call --DECLARED_TARGET-------> file metadata
tool_call --VIA_MCP---------------> mcp_server
Claude Code --SPAWNED_SUBAGENT----> subagent
```

L’entrée hook peut identifier une invocation logique avec `tool_use_id`, mais cet identifiant n’est pas un PID OS. Les noms MCP suivant la convention provider `mcp__<server>__<tool>` sont normalisés, lorsqu’ils sont présents, en entités MCP-server/tool distinctes.

## Frontière de corrélation Tool → Process

Le command-hook Claude ne fournit pas le PID réel du child process créé par une invocation Bash/PowerShell. ExecWeave ne crée donc pas d’edge process causal observé à partir des seules données du hook provider.

Un bridge dérivé ne peut être émis que si le matcher runtime borné trouve exactement un candidat process supporté :

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Chaque bridge reste :

```json
{
  "causal": false,
  "inferred": true,
  "confidence_semantics": "heuristic_score_not_probability"
}
```

La proximité temporelle seule est insuffisante. Les candidats ambigus, commandes composées non prises en charge, shell builtins ou déclarations sans correspondance ne produisent aucun bridge. Une inference n’est jamais promue en attribution process observée.

## Artefacts en couches

Une capture Claude liée au run peut produire :

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
└── viewer.correlated.html
```

La corrélation ne réécrit pas les preuves runtime ou provider originales.

## Sidecar standalone

En dehors du recorder lié au run, le sidecar Claude par défaut est scoped par session :

```text
<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl
```

`EXECWEAVE_SEMANTIC_SIDECAR` ou `--sidecar` peuvent remplacer cet emplacement. Pour des captures parallèles, préférez un chemin propre à la session ou au run.

## Confidentialité et frontière de preuve

Les artefacts Claude full-fidelity peuvent contenir prompts, commandes, chemins de fichiers, bodies `Write`/`Edit`, arguments/résultats d’outils, texte assistant, réponses de subagents, identifiants et secrets applicatifs. Considérez tout le run directory comme sensible et vérifiez-le avant partage.

Le contenu provider reste une preuve provider. Une entrée tool stockée ne prouve pas que le tool a été exécuté ; un body de fichier stocké ne prouve pas qu’un process OS particulier l’a lu ou écrit ; un résultat tool stocké ne prouve pas un data flow au niveau byte. Les claims plus forts exigent les collectors OS et les preuves de corrélation explicitement marquées.

## Merge et corrélation manuels

Le pipeline générique reste disponible si vous avez déjà des fichiers runtime et semantic :

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave correlate run.semantic.jsonl --output run.correlated.jsonl
execweave validate run.correlated.jsonl
```

Voir [`Semantic Telemetry`](semantic-telemetry.fr.md) pour le contrat générique evidence/content et les règles de process-reference.
