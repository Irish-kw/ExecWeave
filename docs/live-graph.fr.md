<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Graphe en direct

ExecWeave peut diffuser un graphe d’exécution local pendant qu’un agent d’IA ou une commande arbitraire est encore en cours d’exécution.

```bash
execweave live --open -- claude
```

## Contrat actuel

Le MVP live utilise volontairement le collecteur `portable`.

Le backend Linux `strace` analyse actuellement les fichiers de trace après la fin de la commande. Il fournit une attribution plus forte fondée sur les appels système, mais ce n’est pas une source d’événements en direct dans l’implémentation actuelle. ExecWeave n’étiquette pas des preuves post-traitées comme télémétrie en direct.

Pour une attribution Linux post-exécution plus forte, utilisez :

```bash
execweave record --backend strace --open -- claude
```

## Flux de données

```text
commande
  ↓
collecteur portable
  ↓
events.jsonl
  ↓
matérialisation partielle du graphe
  ↓
serveur HTTP localhost
  ↓
/graph.json
  ↓
visualiseur navigateur
```

Le navigateur interroge `/graph.json` pendant que l’exécution est active. Chaque instantané est construit à partir des mêmes contrats de flux d’événements Phase 1 et de graphe Phase 2 que les artefacts finaux.

Lorsque la commande se termine, ExecWeave :

1. valide le flux d’événements terminé ;
2. écrit `graph.json` ;
3. écrit le `viewer.html` autonome ;
4. marque le graphe en direct comme terminé ;
5. sert brièvement le visualiseur final avant d’arrêter le serveur local.

## Exposition réseau

Le serveur live se lie uniquement à :

```text
127.0.0.1
```

Il n’est pas exposé sur `0.0.0.0` et n’est pas destiné à être accessible depuis d’autres hôtes du réseau local.

Choisissez explicitement un port :

```bash
execweave live --port 8765 --open -- claude
```

Le port `0` est la valeur par défaut et demande au système d’exploitation de choisir un port local disponible.

## Artefacts

Le répertoire d’exécution par défaut est :

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── graph.json
└── viewer.html
```

Choisissez un autre répertoire avec :

```bash
execweave live --output-dir my-live-run --open -- claude
```

Les artefacts existants et non vides sont refusés plutôt qu’écrasés.

## Instantanés incomplets

Pendant une exécution live, `events.jsonl` est volontairement incomplet puisque la session n’est pas encore terminée.

Les instantanés du graphe live utilisent donc le mode `allow_incomplete` du constructeur de graphe. La validation structurelle reste appliquée : JSON mal formé, sessions incohérentes, entités invalides ou ordre de séquence cassé ne sont pas considérés comme des preuves de graphe valides.

Le graphe final n’est construit qu’après réussite de la validation normale de session complète.

## Limites du backend portable

Le MVP live actuel hérite des garanties du collecteur portable :

- la découverte des processus repose sur l’interrogation périodique ;
- les processus très courts peuvent être manqués ;
- les modifications du système de fichiers sont corrélées à la session plutôt qu’attribuées aux processus ;
- l’inspection réseau par processus dépend de la visibilité et des permissions du système d’exploitation.

Ces limites restent visibles dans les métadonnées d’attribution des événements. Le visualiseur live ne transforme pas une observation non causale en arête causale.

## Futurs backends live natifs

Les collecteurs prévus comprennent :

- Linux eBPF ;
- Windows ETW ;
- macOS Endpoint Security.

L’objectif est de préserver la même sémantique d’événements ExecWeave tout en améliorant l’exhaustivité, l’attribution aux processus et la surcharge d’exécution.

## Couverture CI

La configuration CI du dépôt inclut un chemin smoke `live` qui :

- démarre une session live locale ;
- exécute une commande courte ;
- écrit les artefacts finaux ;
- valide `events.jsonl` ;
- résume le graphe obtenu.

Les tests unitaires/d’intégration exercent également directement l’endpoint localhost `/graph.json`.
