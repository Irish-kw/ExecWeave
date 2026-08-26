# Hooks Cursor

<p align="center">
  <a href="cursor-hooks.md">English</a> |
  <a href="cursor-hooks.zh-TW.md">繁體中文</a> |
  <a href="cursor-hooks.zh-CN.md">简体中文</a> |
  <a href="cursor-hooks.ja.md">日本語</a> |
  <a href="cursor-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="cursor-hooks.de.md">Deutsch</a> |
  <a href="cursor-hooks.ru.md">Русский</a>
</p>

ExecWeave utilise la surface de hooks native de Cursor pour ajouter des preuves logiques Agent / Tool / Command au graphe runtime sans traiter les métadonnées fournisseur comme une causalité OS.

## Démarrage rapide

Générez une configuration de hook et ajoutez-la aux paramètres de hooks Cursor :

```bash
execweave-cursor-hook --print-config
```

Puis enregistrez une exécution Cursor :

```bash
execweave-cursor-record --open -- cursor
```

L’enregistreur lié à l’exécution conserve séparément les artefacts runtime, sémantiques et corrélés.

## Événements

Le baseline consomme :

- `sessionStart`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`

Cursor expose un `tool_use_id` stable ; `preToolUse` et le hook post correspondant peuvent donc partager une identité logique exacte de `tool_call`.

Les arêtes sémantiques typiques sont :

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

`postToolUseFailure` est représenté séparément comme `TOOL_CALL_FAILED`.

## Corrélation outil-vers-processus

Les preuves de hook Cursor ne fournissent pas le PID enfant OS. Un appel Shell ne devient donc pas directement une arête de processus.

Lorsque des preuves runtime exposent indépendamment un seul processus soutenu de manière unique, ExecWeave peut dériver :

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

Le pont est toujours :

```text
inferred: true
causal: false
```

Les appels ambigus ou non pris en charge ne produisent aucun pont.

## Limite de confidentialité

L’adaptateur ne persiste volontairement ni le texte des prompts, ni les chemins de transcript, ni l’adresse e-mail utilisateur, ni les messages de l’agent, ni la sortie des outils. Il ne conserve que les identifiants et métadonnées déclarées nécessaires à l’observabilité, comme l’identité du modèle, les identifiants de conversation/génération, le nom/ID d’utilisation de l’outil, la commande et le chemin de fichier déclaré.

Les commandes et chemins peuvent toujours être sensibles. Examinez les artefacts avant de les partager.

## Limite de preuve

Un hook Cursor prouve ce que Cursor a signalé au niveau sémantique. Il ne prouve pas qu’une commande déclarée a été exécutée, qu’un fichier déclaré a réellement été accédé, ni que des données se sont déplacées entre des ressources. Les collecteurs OS restent la source des preuves runtime.
