# Plugin OpenCode

<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>

ExecWeave s’intègre à OpenCode via un plugin local au projet. OpenCode expose des valeurs exactes `sessionID + callID` sur `tool.execute.before` et `tool.execute.after`, ce qui permet d’identifier un appel d’outil logique sans apparier heuristiquement les événements de cycle de vie.

## Installation

Installez le plugin généré dans le projet courant :

```bash
execweave-opencode-plugin --install
```

Il crée :

```text
.opencode/plugins/execweave.ts
```

OpenCode charge automatiquement les plugins de projet depuis ce répertoire. ExecWeave refuse d’écraser un plugin existant sauf si `--force` est fourni.

Puis enregistrez une exécution :

```bash
execweave-opencode-record --open -- opencode
```

## Preuves sémantiques capturées

Le plugin baseline émet des métadonnées minimales pour :

- `chat.message`
- `tool.execute.before`
- `tool.execute.after`

Les relations typiques du graphe sont :

```text
agent --USED_MODEL--> model
agent --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
tool_call --DECLARED_COMMAND--> command
tool_call --DECLARED_TARGET--> file
tool_call --TOOL_CALL_RETURNED--> tool
```

Le `callID` OpenCode est utilisé directement dans l’identité `tool_call`.

## Limite de confidentialité

Le hook after d’OpenCode peut voir la sortie de l’outil, mais le plugin ExecWeave généré ne transmet volontairement ni `output.output` ni `output.metadata`.

Les arguments sont réduits avant de quitter le plugin :

- `bash` : `command` déclarée
- outils orientés fichier : champs ressemblant à des chemins comme `filePath`, `file_path` ou `path`
- métadonnées facultatives du répertoire de travail

Le contenu brut des écritures, les parties des messages de chat et les sorties d’outil ne sont pas envoyés au hook ExecWeave.

## Corrélation outil-vers-processus

`callID` prouve l’identité logique de l’appel dans OpenCode ; ce n’est pas un PID OS. Tool → Process reste un pont conservateur dérivé, créé uniquement lorsque les preuves runtime produisent un seul processus soutenu de manière unique.

Les ponts dérivés restent `inferred: true` et `causal: false`.

## Limite de preuve

Le plugin rapporte l’intention sémantique d’OpenCode. Les collecteurs runtime établissent indépendamment les observations processus/fichier/réseau. ExecWeave ne traite jamais le plugin fournisseur comme preuve qu’une commande déclarée ou une action fichier a réellement eu lieu.
