<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-2-execution-graph.md">English</a> |
  <a href="phase-2-execution-graph.zh-TW.md">繁體中文</a> |
  <a href="phase-2-execution-graph.zh-CN.md">简体中文</a> |
  <a href="phase-2-execution-graph.ja.md">日本語</a> |
  <a href="phase-2-execution-graph.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="phase-2-execution-graph.de.md">Deutsch</a> |
  <a href="phase-2-execution-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 2 — Graphe d’exécution

La Phase 2 transforme un flux d’événements JSONL Phase 1 validé en un graphe d’exécution persistant qui peut être interrogé puis visualisé par l’interface locale.

## État actuel

Le premier noyau de graphe de la Phase 2 est implémenté.

```bash
execweave validate run.jsonl
execweave graph run.jsonl
execweave graph-summary run.graph.json
```

Le constructeur de graphe ne réinterprète pas la télémétrie brute. Il consomme les sémantiques d’attribution et de causalité produites par la Phase 1.

## Schéma du graphe

La version actuelle du schéma est :

```text
0.1
```

Un document JSON de graphe contient :

```json
{
  "graph_schema_version": "0.1",
  "session_id": "...",
  "event_count": 100,
  "node_count": 24,
  "edge_count": 31,
  "nodes": [],
  "edges": []
}
```

## Nœuds

Chaque identifiant d’entité Phase 1 distinct devient un nœud du graphe.

Exemples :

```text
agent:Claude Code
session:<session-id>
process:<session-id>:1234
file:/repo/src/app.py
network_endpoint:1.2.3.4:443
executable:/usr/bin/python
```

L’identité d’un nœud repose sur l’identifiant d’entité du flux d’événements, et non sur les noms d’affichage.

Chaque nœud accumule :

- `type`
- `name`
- les attributs de l’entité
- le premier horodatage observé
- le dernier horodatage observé
- le nombre d’événements observés
- les types d’événements dans lesquels l’entité est apparue

La Phase 2 utilise actuellement une fusion conservatrice des attributs : un attribut de nœud existant n’est pas silencieusement écrasé par une valeur ultérieure en conflit.

## Arêtes

Un événement possédant une source et une cible peut produire une arête dirigée :

```text
source --RELATION--> target
```

Par exemple :

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

L’identité d’une arête est le tuple :

```text
(source, relation, target)
```

Les événements répétés pour le même tuple sont agrégés en une seule arête au lieu d’être rendus comme des lignes dupliquées.

Une arête agrégée enregistre :

- le `count` exact d’occurrences
- le premier/dernier horodatage
- le premier/dernier numéro de séquence
- les identifiants des événements de support
- les types d’événements contributeurs
- le ou les backends
- la ou les méthodes d’attribution
- l’état de causalité

Exemple :

```text
process:p1 --OPENED_READ--> file:a.txt
count = 17
```

signifie que 17 événements Phase 1 soutiennent la même relation dans le graphe.

## Agrégation de la causalité

Si tous les événements de support sont causaux :

```json
{"causal": true}
```

S’ils sont tous explicitement non causaux :

```json
{"causal": false}
```

Si les preuves sont mixtes ou ne fournissent pas une valeur de causalité uniforme :

```json
{"causal": null}
```

La couche graphe ne doit pas promouvoir une télémétrie non causale en relation causale.

## Événements de cycle de vie

Certains événements Phase 1 ont une source mais pas de cible, par exemple :

```text
process EXITED
session FINISHED_SESSION
```

La Phase 2 **ne fabrique pas** de faux nœud cible ni d’auto-arête pour ces événements.

Ils contribuent plutôt aux métadonnées d’événements observés du nœud source. Le graphe reste ainsi relationnel au lieu de transformer chaque événement de log en nœud artificiel.

## Limite de validation du graphe

Par défaut, la construction du graphe exige un flux d’événements Phase 1 valide et complet :

```bash
execweave graph run.jsonl
```

Pour la récupération après incident ou une session d’agent interrompue :

```bash
execweave graph --allow-incomplete interrupted.jsonl
```

Le flux doit rester structurellement valide ; seule l’exigence de session terminée est assouplie.

## Résumé du graphe

```bash
execweave graph-summary run.graph.json
```

Le résumé rapporte :

- le nombre d’événements
- le nombre de nœuds
- le nombre d’arêtes
- les nombres par type de nœud
- les nombres par relation
- le nombre d’arêtes causales
- le nombre d’arêtes non causales
- le nombre de causalités mixtes/inconnues

## Filtrage

Créez un graphe plus petit sans modifier le graphe source :

```bash
execweave graph-filter run.graph.json \
  --output causal.graph.json \
  --causal-only
```

Filtrer par relation :

```bash
execweave graph-filter run.graph.json \
  --output network.graph.json \
  --relation CONNECTED_TO \
  --relation CONNECT_ATTEMPTED
```

Filtrer par type de nœud :

```bash
execweave graph-filter run.graph.json \
  --output process-network.graph.json \
  --node-type process \
  --node-type network_endpoint
```

Filtrer par backend :

```bash
execweave graph-filter run.graph.json \
  --output syscall.graph.json \
  --backend strace
```

Les filtres peuvent être combinés.

## Requêtes de chemins dirigés

La Phase 2 peut interroger des chemins d’exécution dirigés :

```bash
execweave path run.graph.json \
  'session:abc' \
  'network_endpoint:1.2.3.4:443'
```

Restreindre aux arêtes dont les preuves agrégées sont causales :

```bash
execweave path run.graph.json SOURCE TARGET --causal-only
```

Restreindre les relations :

```bash
execweave path run.graph.json SOURCE TARGET \
  --relation LAUNCHED \
  --relation SPAWNED \
  --relation CONNECTED_TO
```

La recherche de chemin est actuellement :

- dirigée
- en largeur d’abord
- limitée aux chemins simples (un nœud ne peut pas se répéter dans un même chemin retourné)
- bornée par `--max-depth`
- bornée par `--max-paths`

Cela empêche un graphe d’exécution cyclique de produire un nombre illimité de résultats.

## Critères d’acceptation actuels de la Phase 2

- [x] Valider l’entrée Phase 1 avant la construction du graphe
- [x] Matérialiser les entités en nœuds
- [x] Dédupliquer les nœuds par identifiant d’entité stable
- [x] Agréger les événements répétés `(source, relation, target)`
- [x] Conserver les preuves d’événement sur les arêtes
- [x] Conserver la sémantique de causalité
- [x] Conserver les métadonnées temporelles premier/dernier
- [x] Éviter les fausses arêtes pour les événements de cycle de vie avec source seulement
- [x] Résumé du graphe
- [x] Filtrage du graphe
- [x] Requête de chemin dirigé
- [ ] Meilleure résolution d’entités entre identifiants de ressources sémantiquement équivalents
- [ ] Instantanés temporels / filtrage par fenêtre de temps
- [ ] Indexation compacte des preuves pour les très grandes exécutions
- [ ] Tests de migration/versionnement du format de graphe
- [ ] Interface locale interactive du graphe

L’interface interactive relève de la Phase 3. Elle doit consommer ce contrat de graphe plutôt que lire directement les logs bruts du collecteur.
