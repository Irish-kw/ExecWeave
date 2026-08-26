<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Télémétrie sémantique

ExecWeave peut combiner des événements sémantiques de fournisseur/framework avec des preuves d’exécution du système d’exploitation sans réécrire la capture d’exécution originale.

L’objectif est de placer dans le même graphe les preuves logiques Agent/Tool/MCP et les preuves machine de processus/fichier/réseau, tout en conservant quelle source a établi chaque relation.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Un hook fournisseur peut expliquer *quelle action logique a été demandée*. Le collecteur d’exécution explique *ce que la machine a réellement fait*. ExecWeave ne transforme pas silencieusement la proximité temporelle entre les deux en preuve causale.

## Workflow

Capturez d’abord une exécution ExecWeave normale :

```bash
execweave run --output run.jsonl -- claude
```

Un adaptateur ou hook fournisseur écrit un sidecar sémantique distinct, par exemple `semantic.jsonl`.

Fusionnez le sidecar dans un **nouveau** flux d’événements validé :

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl \
  --output run.semantic.graph.json
execweave view run.semantic.graph.json \
  --output run.semantic.html \
  --open
```

`run.jsonl` n’est jamais modifié par `semantic-merge`.

## Contrat des enregistrements sidecar

Un enregistrement sidecar sémantique est un objet JSON par ligne. L’adaptateur fournit uniquement l’observation sémantique :

```json
{
  "timestamp": "2026-08-25T10:00:02.123Z",
  "event_type": "semantic.tool.called",
  "relation": "REQUESTED_TOOL_CALL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool_call",
    "id": "tool-call:provider:session:call-id",
    "name": "Bash",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "evidence_source": "provider_hook",
    "causal": false
  }
}
```

Le sidecar n’a **pas** besoin de fournir :

- le `session_id` ExecWeave
- le `schema_version` ExecWeave
- une `sequence` contiguë
- `event_id` (facultatif ; ExecWeave en crée un s’il est omis)

`semantic-merge` injecte l’identifiant de session d’exécution, utilise le schéma d’événements ExecWeave courant, trie les événements sémantiques/d’exécution par horodatage, réattribue une séquence contiguë, conserve `session.started` en premier et `session.finished` en dernier, puis valide le résultat fusionné avant d’écrire le fichier de sortie.

## Entités sémantiques recommandées

Le schéma d’entités générique d’ExecWeave prend déjà en charge des types de nœuds supplémentaires.

| Type | Exemple d’ID | Signification |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Agent/client logique |
| `tool_call` | `tool-call:claude:session:tool-use-id` | Une invocation logique concrète d’un outil |
| `tool` | `tool:claude:Bash` | Outil visible par l’agent |
| `mcp_server` | `mcp-server:claude:github` | Serveur/intégration MCP |
| `model` | `model:claude:claude-sonnet` | Identité du modèle lorsque le fournisseur l’expose |
| `command` | `command:sha256:...` | Métadonnées de commande déclarée provenant d’un hook sémantique |
| `process_reference` | `process-pid:1234` | Pont facultatif lorsqu’une source amont fournit réellement un PID |

Les identifiants d’entité doivent être suffisamment stables pour dédupliquer les observations sémantiques répétées au sein d’une exécution.

## Pont facultatif de référence de processus

Certains adaptateurs fournisseur/framework peuvent connaître un PID enfant sans connaître l’identifiant d’entité de processus ExecWeave complet. Ils peuvent alors émettre un `process_reference` avec le PID observé.

Pendant la fusion, ExecWeave résout ces références par rapport aux entités de processus réellement observées dans le flux d’exécution. La résolution est conservatrice :

1. un `create_time` explicite peut identifier le processus de façon unique ;
2. un PID avec un seul candidat d’exécution est résolu directement ;
3. en cas de réutilisation de PID, ExecWeave peut choisir l’unique dernière heure de création de processus qui n’est pas postérieure à l’horodatage sémantique ;
4. sinon le nœud reste `process_reference` avec `unresolved: true` au lieu de deviner.

Un événement résolu enregistre le mappage original-vers-processus-runtime dans `attributes.resolved_process_references`.

**N’émettez pas de `process_reference` si le fournisseur n’a pas exposé de PID.** Une chaîne de commande et un horodatage de processus proche ne suffisent pas pour affirmer une relation exacte Tool → Process.

L’adaptateur natif Claude Code suit cette règle : l’entrée de hook Claude identifie les appels d’outil mais n’expose pas le PID du processus enfant, donc l’adaptateur n’invente pas d’arêtes `tool_call --SPAWNED_PROCESS--> process`.

## Limite entre preuve et causalité

Les adaptateurs fournisseur actuels marquent les arêtes sémantiques `causal: false` même lorsqu’un hook fournisseur signale avec autorité qu’un événement logique d’outil a eu lieu. Dans ExecWeave, `causal: true` est réservé à une attribution plus forte au niveau de l’exécution, et non au simple fait que deux objets logiques soient liés.

Cela maintient séparées des affirmations comme :

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       preuve sémantique fournisseur
process     --OPENED_READ---------> ~/.ssh/id_ed25519 preuve runtime OS
```

Ces deux observations ne prouvent **pas** à elles seules :

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

Toute future couche de corrélation sémantique/runtime devra exposer explicitement sa méthode et sa confiance, et rester distinguable de l’attribution OS observée.

## Limite de session

Chaque horodatage sémantique doit se trouver dans l’intervalle de la session d’exécution capturée. Les événements hors de cet intervalle sont rejetés. Cela évite d’attacher silencieusement une télémétrie fournisseur sans rapport à la mauvaise exécution.

## Confidentialité

Les sidecars sémantiques peuvent contenir des métadonnées sensibles même lorsque ExecWeave lui-même ne collecte pas le contenu des fichiers. Les auteurs d’adaptateurs doivent préférer des identifiants et des métadonnées bornées aux prompts complets, arguments d’outil, sorties d’outil, identifiants d’accès ou valeurs secrètes.

L’adaptateur Claude Code ne persiste volontairement ni le contenu `Write` ni `tool_response`. Les commandes shell déclarées sont conservées car elles sont centrales pour expliquer l’exécution, mais leur taille est bornée et elles doivent toujours être considérées comme des métadonnées potentiellement sensibles.

La couche générique de fusion sémantique est indépendante du fournisseur. Les adaptateurs spécifiques au fournisseur sont des intégrations distinctes et doivent documenter exactement quels champs amont ils consomment et quelles affirmations ces champs autorisent.

Voir [`Claude Code Hooks`](claude-code-hooks.fr.md) pour le premier adaptateur fournisseur natif.
