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

ExecWeave combine les observations sémantiques des fournisseurs/frameworks avec des preuves d'exécution OS indépendantes sans réécrire la capture d'origine. Les preuves fournisseur décrivent ce qu'un Agent, un outil, une passerelle ou un runtime de modèle a exposé ; les preuves OS décrivent ce que le collecteur machine a observé. La corrélation reste une couche dérivée séparée et n'est jamais promue silencieusement en preuve causale.

## Workflow

Un adaptateur fournisseur écrit un sidecar sémantique lié au run, puis ExecWeave valide un nouveau flux fusionné :

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`run.jsonl` n'est jamais modifié par `semantic-merge`. Les recorders liés au run conservent les artefacts runtime, semantic et correlated dans des fichiers séparés.

## Contenu full-fidelity dans v0.6.5

La télémétrie sémantique n'est plus limitée à de petits résumés de métadonnées. Lorsqu'un point d'intégration pris en charge fournit explicitement du contenu, v0.6.5 peut conserver la valeur complète dans un store local adressé par contenu et ne placer qu'une référence dans l'événement JSONL.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Une référence enregistre SHA-256, chemin relatif, type média, taille, nature du contenu, représentation et indication de complétude depuis ce point d'intégration. `complete_from_source: true` signifie qu'ExecWeave a préservé toute la valeur reçue ; cela ne signifie pas qu'un fournisseur a exposé un état caché du modèle, une requête réseau finale non observée ou un champ absent de la source.

Les adaptateurs natifs pris en charge utilisent ce mécanisme pour les contenus réellement exposés : prompts, entrées/résultats d'outils, réponses assistant/modèle, texte de reasoning/thinking lorsqu'il est explicitement fourni, contenu de fichiers fourni par un hook et objets request/response lorsque le contrat de l'adaptateur le permet.

Le résumé sémantique compact reste utilisable pour le graphe même si le content store échoue. Les adaptateurs natifs sont fail-open par défaut afin qu'une erreur de stockage n'empêche pas intentionnellement l'opération de l'Agent.

## Frontière des preuves

Le contenu sémantique est une preuve observée au niveau fournisseur/intégration, pas une causalité OS. Une entrée d'outil stockée ne prouve pas qu'un processus l'a exécutée ; un corps de fichier fourni par un hook ne prouve pas qu'une lecture OS s'est terminée ; une paire request/response fournie à une CLI n'implique pas une interception réseau transparente.

Les ponts Tool → Process sont créés uniquement par la couche de corrélation conservatrice et restent :

```text
inferred: true
causal: false
```

Une attribution inconnue ou ambiguë ne produit aucun pont. Un flux de données au niveau des octets ou une exfiltration ne sont pas déduits simplement parce que des observations fichier et réseau coexistent.

## Confidentialité

Le contenu full-fidelity est volontairement sensible. Ne supposez pas que les prompts, arguments d'outils, sorties, réponses modèle, contenus de fichiers ou valeurs applicatives sensibles ont été expurgés. Le store conserve la valeur complète fournie par le point d'intégration pris en charge.

ExecWeave filtre les identifiants de transport connus dans certaines projections de métadonnées lorsque le contrat de l'adaptateur le prévoit, mais ce n'est ni un scanner général de secrets ni un mécanisme qui supprime les valeurs sensibles incorporées dans le contenu. Les blobs restent locaux par défaut et ne sont pas intégrés directement aux événements de graphe, mais font toujours partie des preuves du run et doivent être examinés avant partage.

Les documents propres à chaque fournisseur définissent exactement quels champs sont observables. Voir la documentation Claude Code, Codex, Gemini, Cursor, OpenCode, Inference Gateway et Model Runtime.
