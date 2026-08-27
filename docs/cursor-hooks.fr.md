# Cursor Hooks

<!-- i18n-nav:start -->
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
<!-- i18n-nav:end -->

ExecWeave utilise la surface de hooks native de Cursor pour ajouter des preuves semantic/content fournisseur à un run sans les traiter comme causalité OS.

## Démarrage rapide

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Le recorder lié au run conserve séparément les artefacts runtime, semantic et correlated.

## Surface d'observation

La configuration v0.6.5 couvre une surface de cycle de vie Cursor plus large lorsque Cursor l'expose : session start/end, tool before/after/failure, subagents, exécution shell et MCP, lectures/éditions de fichiers, soumission de prompt, compaction/stop, événements Agent response/thought et événements tab file read/edit.

Cursor fournit une identité logique stable pour ses appels d'outils. Cette identité n'est pas un PID OS.

## Contenu full-fidelity

Quand Cursor fournit explicitement une valeur de contenu, v0.6.5 stocke la valeur complète dans le store local adressé par contenu et n'inscrit qu'une référence dans le JSONL sémantique.

Les régressions couvrent notamment le prompt complet, les entrées/sorties d'outils et textes d'échec, commandes/sorties shell, commandes/entrées/résultats MCP, contenu de fichier fourni par les hooks de lecture, structures d'édition, réponses finales de l'Agent, texte étiqueté thought par le fournisseur et résumés de subagents.

Ces champs restent des observations fournisseur avec leurs limites. Par exemple, un contenu fourni par `beforeReadFile` ne prouve pas qu'une lecture OS a été menée à terme, et une structure d'édition ne prouve pas un snapshot complet post-édition si le fournisseur ne l'a pas fourni.

Les identifiants de transport connus sont filtrés de la projection provider-metadata là où le contrat le prévoit. Les valeurs sensibles intégrées au contenu sont conservées. Le full-fidelity n'est pas une couche générale de redaction.

## Corrélation Tool vers Process

Les hooks Cursor ne fournissent pas le PID enfant OS. Un appel Shell ne devient donc un pont vers un processus que lorsqu'une preuve runtime indépendante soutient un seul candidat :

```text
inferred: true
causal: false
```

Les appels ambigus ou non pris en charge ne produisent aucun pont. L'identité stable d'un tool call dans Cursor prouve seulement une identité logique côté fournisseur, pas une attribution machine-level.

## Confidentialité et frontière des preuves

Les preuves d'un run Cursor peuvent contenir prompts, arguments/résultats d'outils, sorties shell, contenu de fichiers, données d'édition, réponses assistant, texte thought étiqueté par le fournisseur, commandes, chemins, identifiants, valeurs MCP et valeurs applicatives sensibles. Examinez le run complet avant partage.

Un hook Cursor prouve uniquement ce que Cursor a rapporté ou fourni au niveau fournisseur. Il ne prouve pas à lui seul qu'une commande déclarée a été exécutée, qu'un fichier a été accédé par un processus précis ou que des octets ont circulé entre ressources.
