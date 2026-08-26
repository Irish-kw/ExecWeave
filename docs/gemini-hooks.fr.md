<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Hooks Gemini CLI

ExecWeave peut ingérer les hooks de cycle de vie/outils de Gemini CLI comme preuves sémantiques fournisseur et les combiner avec des preuves runtime OS collectées indépendamment.

L’adaptateur est volontairement conservateur : les preuves de hook Gemini décrivent ce que le fournisseur rapporte au niveau Agent / Tool. Elles ne prouvent pas à elles seules quel processus OS a effectué le travail.

## Événements de hook pris en charge

L’adaptateur actuel consomme :

- `SessionStart`
- `BeforeTool`
- `AfterTool`

Gemini CLI envoie l’entrée de hook en JSON sur `stdin`. Un hook de commande réussi doit retourner un JSON valide sur `stdout` ; ExecWeave renvoie donc exactement `{}` en cas de succès et envoie les avertissements uniquement sur `stderr`.

Générez un fragment de paramètres avec :

```bash
execweave-gemini-hook --print-config
```

Fusionnez l’objet `hooks` obtenu dans le `settings.json` de Gemini CLI.

La configuration générée observe tous les outils avec des matchers `BeforeTool` / `AfterTool` et ne bloque ni ne réécrit l’appel d’outil.

## Enregistrement en une commande

Après configuration des hooks :

```bash
execweave-gemini-record --open -- gemini
```

L’enregistreur associe le processus enfant Gemini à un sidecar sémantique propre à l’exécution via `EXECWEAVE_SEMANTIC_SIDECAR`, puis utilise la chaîne provider-record partagée :

```text
preuve runtime
      +
preuve de hook Gemini
      ↓
fusion sémantique validée
      ↓
corrélation conservatrice
      ↓
graphe + visualiseur
```

Une exécution intégrée au fournisseur peut produire :

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

Les preuves runtime brutes et sidecar fournisseur restent séparées. La corrélation crée un flux dérivé plutôt que de réécrire les preuves d’entrée observées.

## Mappage des événements

### Démarrage de session

`SessionStart` devient une preuve de session fournisseur :

```text
Gemini CLI --STARTED_PROVIDER_SESSION--> provider_session
```

ExecWeave conserve les métadonnées de session nécessaires à l’attribution mais ne lit ni ne copie le transcript référencé par `transcript_path`.

### BeforeTool

Un hook `BeforeTool` produit des relations sémantiques telles que :

```text
Gemini CLI --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Pour l’outil intégré `run_shell_command`, `tool_input.command` est représenté comme :

```text
tool_call --DECLARED_COMMAND--> command
```

Cette preuve de commande peut participer à la même corrélation conservatrice Tool → Process que les autres adaptateurs fournisseur.

Pour certains outils fichier comme `read_file`, `write_file` et `replace`, ExecWeave peut enregistrer le chemin cible déclaré comme métadonnée sémantique. Il ne capture pas le contenu du fichier.

### Outils MCP

Lorsque Gemini CLI fournit `mcp_context`, ExecWeave utilise l’identité serveur/outil explicitement signalée par le fournisseur :

```text
tool_call --VIA_MCP--> mcp_server
mcp_server --EXPOSES_TOOL--> tool
```

L’adaptateur ne persiste pas la commande de lancement MCP, ses arguments ni son URL depuis `mcp_context`, car ces champs peuvent contenir des métadonnées de connexion ou des identifiants sensibles.

### AfterTool

`AfterTool` est enregistré comme une observation distincte `tool_result`.

Si `tool_response.error` n’est pas vide, l’adaptateur enregistre un signal d’erreur signalé par le fournisseur. Sinon, il enregistre un signal neutre de résultat retourné.

ExecWeave ne stocke **pas** le `llmContent`, le `returnDisplay` ni le corps d’erreur brut du fournisseur.

## Aucun identifiant unique d’appel d’outil Gemini

Le schéma d’entrée de hook Gemini CLI actuel fournit `tool_name`, `tool_input` et un contexte MCP optionnel, mais n’expose pas d’identifiant unique d’appel d’outil partagé entre `BeforeTool` et `AfterTool`.

ExecWeave n’affirme donc **pas** d’arête d’identité directe BeforeTool → AfterTool.

Chaque requête `BeforeTool` reçoit une identité locale limitée par l’horodatage. `AfterTool` crée un nœud de résultat indépendant. Les deux peuvent porter un `tool_fingerprint` déterministe dérivé du nom de l’outil + entrée normalisée comme indication de diagnostic, mais cette empreinte n’est **pas traitée comme une identité d’appel**. Des commandes identiques répétées doivent rester distinguables.

## Corrélation Tool → Process

Les hooks Gemini ne fournissent pas le PID enfant OS nécessaire pour prouver l’attribution Tool → Process.

Un graphe corrélé peut contenir :

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

uniquement lorsque le matcher borné existant trouve un seul candidat de processus soutenu de manière unique par des preuves runtime indépendantes.

Chaque pont reste :

```text
inferred: true
causal: false
```

Les commandes ambiguës, non appariées, composées, builtins shell ou non prises en charge ne produisent aucun pont.

Le Viewer corrélé expose les nombres matched / ambiguous / no-match / unsupported afin qu’une arête manquante ne soit pas silencieusement interprétée comme « rien ne s’est passé ».

## Limite de confidentialité

L’adaptateur Gemini natif évite volontairement :

- le contenu des prompts
- le contenu des transcripts
- le contenu brut des résultats d’outil
- les corps d’erreur fournisseur bruts
- les détails de commande / arguments / URL MCP
- le contenu des fichiers

Il peut néanmoins conserver des métadonnées telles que le texte de commande, les chemins de fichiers déclarés, les noms d’outils, les identifiants de session et les noms serveur/outil MCP. Examinez les artefacts avant de les partager.

## Comportement en cas d’échec

`execweave-gemini-hook` est fail-open par défaut. Les erreurs de télémétrie sont écrites sur `stderr` et ne bloquent pas intentionnellement l’appel d’outil Gemini.

Utilisez `--strict` uniquement lorsqu’un code de sortie non nul pour la télémétrie est souhaité.

## Contrat amont actuel

Cet adaptateur suit la référence de hooks Gemini CLI actuelle :

- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
- https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/index.md

Les schémas de hooks fournisseur peuvent évoluer. ExecWeave n’enregistre que les champs réellement délivrés par le fournisseur et maintient utile la collecte runtime OS indépendante même lorsque les hooks sémantiques sont indisponibles.

Voir aussi [`Télémétrie sémantique`](semantic-telemetry.fr.md).
