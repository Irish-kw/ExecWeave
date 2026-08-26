<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Hooks de cycle de vie OpenAI Codex

ExecWeave possède un adaptateur natif pour les hooks de cycle de vie OpenAI Codex afin d’ajouter des preuves sémantiques au niveau du fournisseur à la même exécution locale que la télémétrie runtime OS.

Cette intégration est volontairement conservatrice. Les hooks de cycle de vie Codex peuvent indiquer à ExecWeave quel appel d’outil logique a été demandé et, pour l’exécution shell, quelle commande a été déclarée. Ils ne fournissent **pas** de PID enfant OS ; ExecWeave ne présente donc jamais l’attribution Tool → Process issue du hook fournisseur comme une preuve directement observée ou causale.

## Prise en charge actuelle

ExecWeave consomme actuellement les événements de cycle de vie Codex suivants :

- `SessionStart`
- `PreToolUse`
- `PostToolUse`

L’adaptateur n’enregistre que les hooks réellement délivrés par Codex. Les événements inconnus sont ignorés plutôt que devinés.

### `SessionStart`

Lorsqu’un nom de modèle est présent, ExecWeave enregistre :

```text
OpenAI Codex --USED_MODEL--> model
```

L’adaptateur ne lit ni ne copie le contenu des fichiers de transcript.

### `PreToolUse`

ExecWeave utilise le `tool_use_id` du fournisseur comme identité stable de l’appel logique :

```text
OpenAI Codex --REQUESTED_TOOL_CALL--> tool_call
tool_call --USES_TOOL--> tool
```

Pour l’outil de hook Codex canonique `Bash`, un `tool_input.command` de type chaîne produit également :

```text
tool_call --DECLARED_COMMAND--> command
```

La commande déclarée constitue une preuve sémantique du fournisseur. Elle est utile pour une corrélation conservatrice ultérieure, mais ne prouve pas qu’un processus OS particulier a exécuté cette commande.

### `PostToolUse`

ExecWeave enregistre actuellement une relation neutre de fin :

```text
tool_call --TOOL_CALL_RETURNED--> tool
```

Il ne traduit volontairement **pas** `PostToolUse` en `TOOL_CALL_SUCCEEDED` ou `TOOL_CALL_FAILED`. Le payload de hook Codex actuel ne fournit pas de discriminateur succès/échec suffisamment fiable pour qu’ExecWeave puisse faire cette affirmation en toute sécurité.

ExecWeave ne stocke pas le `tool_response` brut dans la télémétrie sémantique. Pour les réponses de type chaîne, il ne conserve que le type de réponse et le nombre de caractères.

## Configurer Codex

Après installation d’ExecWeave, générez le fragment de configuration de hooks pris en charge :

```bash
execweave-codex-hook --print-config
```

Fusionnez l’objet `hooks` imprimé dans votre configuration Codex `hooks.json`.

La configuration générée enregistre `execweave-codex-hook` pour `SessionStart`, `PreToolUse` et `PostToolUse`.

L’adaptateur de hook est fail-open par défaut : les problèmes de télémétrie affichent un avertissement mais ne bloquent pas intentionnellement Codex. Pour déboguer l’adaptateur lui-même, utilisez :

```bash
execweave-codex-hook --strict
```

## Enregistrer une exécution Codex

Une fois Codex configuré pour invoquer le hook, exécutez :

```bash
execweave-codex-record --open -- codex
```

`execweave-codex-record` ne modifie pas la configuration Codex. Il associe uniquement le processus enfant Codex à un sidecar sémantique propre à l’exécution via une variable d’environnement héritée.

Lorsque les hooks de cycle de vie se déclenchent, le répertoire d’exécution contient des artefacts en couches :

```text
.execweave/runs/<run-id>/
├── events.jsonl              # preuve runtime uniquement
├── graph.json                # graphe runtime uniquement
├── viewer.html               # visualiseur runtime uniquement
├── semantic.jsonl            # preuve des hooks de cycle de vie Codex uniquement
├── events.semantic.jsonl     # flux runtime + sémantique validé
├── graph.semantic.json       # graphe runtime + sémantique
├── viewer.semantic.html      # visualiseur runtime + sémantique
├── events.correlated.jsonl   # flux dérivé ; preuves observées inchangées
├── graph.correlated.json     # graphe avec ponts inférés + métadonnées de corrélation
└── viewer.correlated.html    # visualiseur avec résumé de corrélation
```

Si aucun événement de hook Codex n’arrive, l’enregistreur revient sans risque aux artefacts runtime uniquement.

## Corrélation Tool → Process

Pour une déclaration `Bash` telle que :

```text
tool_call --DECLARED_COMMAND--> "python task.py"
```

ExecWeave peut comparer cette déclaration sémantique avec des preuves runtime de processus dans une fenêtre bornée. Il émet :

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

uniquement lorsqu’un seul candidat de processus est soutenu de manière unique par le matcher conservateur existant.

Chaque pont reste :

```text
inferred: true
causal: false
```

Les appels ambigus, non appariés, builtins shell, composés ou autrement non pris en charge ne produisent aucun pont. Le graphe corrélé stocke un résumé de corrélation au niveau de l’exécution afin que le Viewer puisse distinguer `matched`, `ambiguous`, `no match` et `unsupported` au lieu de traiter toutes les arêtes absentes de la même manière.

Le Viewer fournit également **observed only**, qui supprime les arêtes inférées avant le parcours de focus et la mise en page.

## Limite de preuve et de confidentialité

L’adaptateur Codex d’ExecWeave stocke actuellement les métadonnées sémantiques nécessaires à la construction du graphe, notamment :

- l’identifiant de session Codex
- l’identifiant de tour lorsqu’il est fourni
- le nom du modèle
- le nom de l’outil
- l’identifiant d’utilisation de l’outil
- les noms des clés d’entrée
- la commande `Bash` déclarée
- le type / la longueur de réponse pour `PostToolUse`

Il ne collecte pas intentionnellement :

- le texte du prompt
- le contenu des fichiers de transcript
- le contenu brut de `tool_response`
- le contenu des fichiers
- des PID Tool → Process dérivés du fournisseur

Les commandes peuvent tout de même contenir des secrets ou des chemins sensibles. Examinez les artefacts avant de les partager.

## Limites amont actuelles

Les hooks de cycle de vie Codex évoluent. ExecWeave traite donc cette intégration comme un adaptateur sémantique natif, et non comme la preuve que tous les modes d’exécution Codex offrent une couverture complète du cycle de vie.

Contraintes connues :

1. `PostToolUse` ne donne actuellement pas à ExecWeave un signal de succès/échec fiable ; la relation reste donc neutre `TOOL_CALL_RETURNED`.
2. La distribution des hooks de cycle de vie a connu récemment des lacunes dans certains chemins `codex exec`. La CLI Codex interactive est la cible initiale la plus sûre pour cette télémétrie.
3. Certains chemins d’exécution de commandes Windows ont connu des lacunes de couverture de hooks en amont.
4. Les hooks fournisseur ne fournissent pas le PID enfant OS nécessaire à une attribution Tool → Process directement observée.

Ces limites affectent la couverture sémantique, pas le collecteur runtime OS indépendant. Les preuves runtime restent disponibles même si aucun hook fournisseur ne se déclenche.

## Règle de conception

L’intégration Codex suit la même règle de preuve que le reste d’ExecWeave :

> La sémantique fournisseur décrit ce que l’agent a déclaré faire ; la télémétrie OS décrit ce que la machine a réellement observé ; une corrélation ne peut relier les deux que sous forme d’inférence explicite et non causale lorsque les preuves sont uniques.
