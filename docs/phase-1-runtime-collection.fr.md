<!-- i18n-nav:start -->
<p align="center">
  <a href="phase-1-runtime-collection.md">English</a> |
  <a href="phase-1-runtime-collection.zh-TW.md">繁體中文</a> |
  <a href="phase-1-runtime-collection.zh-CN.md">简体中文</a> |
  <a href="phase-1-runtime-collection.ja.md">日本語</a> |
  <a href="phase-1-runtime-collection.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="phase-1-runtime-collection.de.md">Deutsch</a> |
  <a href="phase-1-runtime-collection.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Phase 1 — Collecte à l’exécution

La Phase 1 établit un flux local d’événements d’exécution prêt à être transformé en graphe par la Phase 2.

## État

**La Phase 1 est terminée pour le chemin de référence Linux et le mécanisme de repli portable.**

ExecWeave fournit maintenant deux backends de collecte :

- `strace` — collecte Linux fondée sur les appels système. Capture les descendants de courte durée ainsi que les actions système de fichiers/réseau attribuées aux processus à partir des preuves d’appels système.
- `portable` — mécanisme de repli psutil + watchdog pour Linux, macOS et Windows. Les événements processus/réseau sont interrogés périodiquement ; les modifications du système de fichiers sont corrélées à la session et explicitement non causales.

`auto` préfère `strace` sous Linux lorsqu’il est installé et sélectionne sinon `portable`.

```bash
execweave doctor
execweave run --backend auto -- claude
```

## Installation

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Sous Debian/Ubuntu, installez le backend Linux de référence avec :

```bash
sudo apt-get install strace
```

Puis :

```bash
execweave run -- claude
execweave run -- codex
execweave run -- gemini
execweave run -- opencode
execweave run -- python my_agent.py
```

Les événements sont écrits localement dans :

```text
.execweave/runs/<session-id>.jsonl
```

Les fichiers `strace` bruts sont supprimés par défaut après l’analyse. Conservez-les uniquement pour le débogage :

```bash
execweave run --keep-native-trace -- claude
```

## Vérification de bout en bout de la Phase 1

Une exécution Phase 1 peut être vérifiée sans encore construire le graphe Phase 2 :

```bash
execweave doctor
execweave run --output run.jsonl -- python my_agent.py
execweave validate run.jsonl
execweave benchmark --backend auto --iterations 5
```

`execweave validate` vérifie le contrat du flux d’événements, notamment :

- des enregistrements JSONL valides ;
- un identifiant de session par fichier ;
- des identifiants d’événement uniques ;
- des numéros de séquence contigus commençant à 1 ;
- des horodatages valides ;
- les champs événement/entité requis ;
- exactement un `session.started` et un `session.finished` pour une exécution terminée.

Pour une exécution interrompue qui ne contient légitimement pas `session.finished` :

```bash
execweave validate --allow-incomplete run.jsonl
```

ExecWeave refuse aussi, par défaut, de réutiliser un fichier de sortie existant et non vide. Cela empêche une seconde exécution d’ajouter silencieusement une nouvelle session avec un compteur de séquence redémarré dans le même flux d’événements.

## Modèle de capacités des backends

### Backend Linux `strace`

Le backend natif de référence de la Phase 1 suit les descendants avec `strace -ff` et enregistre des arêtes fondées sur les appels système.

Il peut produire des relations telles que :

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --EXECUTED--> executable
process --OPENED_READ--> file
process --OPENED_WRITE--> file
process --DELETED--> file
process --RENAMED_TO--> file
process --CHANGED_CWD_TO--> directory
process --CONNECTED_TO--> network_endpoint
process --CONNECT_ATTEMPTED--> network_endpoint
process --EXITED--> ...
```

Ces événements incluent :

```json
{
  "attribution": "syscall",
  "causal": true,
  "backend": "strace"
}
```

`OPENED_READ` et `OPENED_WRITE` décrivent le mode d’accès prouvé par l’appel système d’ouverture. Ils n’affirment volontairement **pas** qu’un `read()` ou `write()` ultérieur au niveau des octets a eu lieu. Le suivi du flux de données au niveau des octets appartient à un collecteur ultérieur.

### Backend portable

Le backend portable lance directement la commande et utilise psutil/watchdog.

Il peut produire :

```text
session --LAUNCHED--> process
process --SPAWNED--> process
process --CONNECTED_TO--> network_endpoint
session --OBSERVED_FILE_CHANGE--> file
```

Les modifications du système de fichiers restent des observations explicites de session :

```json
{
  "attribution": "session_observation",
  "causal": false
}
```

Cela empêche ExecWeave de présenter une corrélation temporelle comme une attribution causale.

## Ordre et identité des événements

Le sink JSONL ajoute un numéro `sequence` croissant de manière monotone à chaque événement d’une exécution. Les horodatages sont conservés séparément.

Les identifiants de processus portables utilisent PID + heure de création du processus, car les systèmes d’exploitation réutilisent les PID.

Le backend Linux fondé sur les appels système limite les identifiants de processus à la session ExecWeave :

```text
process:<session-id>:<pid>
```

L’identité d’un processus n’est donc jamais déduite globalement à partir du seul PID.

L’analyseur strace effectue également une pré-passe parent-processus avant d’émettre les événements de graphe. Cela évite qu’un processus enfant soit étiqueté à tort comme racine de session lorsque l’enregistrement de trace de l’enfant et l’enregistrement `clone()`/`fork()` du parent ont le même horodatage dans des fichiers de trace distincts.

## Processus de courte durée

Le backend portable peut manquer un processus qui démarre et se termine entièrement entre deux intervalles d’interrogation.

Le backend Linux de référence supprime cette lacune de Phase 1 en traçant les appels système de processus et en suivant les descendants avec `strace -ff`. La CI inclut un test d’intégration qui lance un enfant de courte durée et vérifie qu’une arête `SPAWNED` est émise.

## Attribution des chemins du système de fichiers

L’analyseur Linux suit les répertoires de travail par processus et gère les appels système courants de la famille `*at`. Les chemins relatifs sont résolus à partir des meilleures preuves d’appel système disponibles.

L’attribution de chemin peut encore être imparfaite pour certains motifs dirfd rares. Les noms d’appels système et chemins bruts sont conservés comme attributs d’événement afin que les consommateurs en aval puissent auditer la manière dont une arête a été produite.

## Attribution réseau

Le backend Linux enregistre les preuves d’appel système `connect()` pour :

- IPv4
- IPv6
- sockets de domaine Unix

Les appels réussis produisent :

```text
process --CONNECTED_TO--> endpoint
```

Les appels échoués ou asynchrones, y compris le cas courant non bloquant `EINPROGRESS`, sont conservés comme :

```text
process --CONNECT_ATTEMPTED--> endpoint
```

L’événement conserve le résultat de l’appel système et errno. ExecWeave ne présente donc pas à tort une tentative de connexion asynchrone comme une connexion confirmée, ni comme une absence totale de comportement réseau.

Le backend portable utilise l’inspection des sockets par processus lorsque le système d’exploitation l’expose à l’utilisateur courant.

L’absence d’événement ne doit jamais être interprétée comme la preuve qu’aucune action réseau n’a eu lieu sur un backend dépourvu des permissions ou de la couverture nécessaires.

## Confidentialité

La télémétrie d’exécution peut contenir des chemins sensibles, des noms d’exécutables, des arguments de commande et des endpoints.

La Phase 1 suit ces valeurs par défaut :

- toutes les données d’événements restent locales ;
- les fichiers de trace d’appels système bruts sont supprimés après analyse sauf si `--keep-native-trace` est demandé ;
- le contenu des fichiers n’est pas tracé ;
- les buffers d’octets de `read()`/`write()` ne sont pas collectés ;
- les arguments `execve` ne sont pas copiés dans les événements de graphe au-delà d’un nombre d’arguments.

Le wrapper de session enregistre toutefois la commande fournie à ExecWeave ; les utilisateurs doivent donc éviter de placer des secrets directement dans les lignes de commande.

## Diagnostic

```bash
execweave doctor
```

Exemple :

```json
{
  "auto_selected": "strace",
  "platform": "linux",
  "portable": true,
  "strace": true
}
```

## Harnais de benchmark de surcharge

La Phase 1 inclut un benchmark smoke reproductible :

```bash
execweave benchmark --backend portable --iterations 5
execweave benchmark --backend strace --iterations 5
```

ou :

```bash
python benchmarks/phase1_overhead.py
```

Il rapporte les temps bruts de référence/instrumentés, les médianes et un ratio de surcharge. Il s’agit de mesures spécifiques à l’environnement, et non d’une affirmation publiée de performance.

## Contrat CI

La matrice GitHub Actions s’exécute sous Linux, macOS et Windows avec les versions Python prises en charge.

En plus des tests unitaires et du linting, la CI exécute maintenant :

1. `execweave doctor` ;
2. une exécution portable de bout en bout ;
3. `execweave validate` sur ce flux portable ;
4. une exécution Linux `strace` de bout en bout ;
5. la validation du flux Linux natif ;
6. un test smoke du benchmark Phase 1.

Cela signifie que la Phase 1 est testée comme un véritable workflow CLI, et pas seulement comme un ensemble de fonctions Python isolées.

## Critères d’acceptation

- [x] Wrapper de session ExecWeave explicite
- [x] Schéma d’événements prêt pour le graphe
- [x] Numéros de séquence d’événements monotones
- [x] Capture du processus racine
- [x] Capture des relations parent/enfant
- [x] Observation portable du système de fichiers
- [x] Observation réseau portable par processus
- [x] Capture fiable des processus Linux de courte durée
- [x] Télémétrie Linux des appels système de fichiers attribuée aux processus
- [x] Télémétrie Linux des appels système réseau attribuée aux processus
- [x] Conservation des tentatives de connexion réseau asynchrones/échouées
- [x] Attribution parent stable entre enregistrements de trace de même horodatage
- [x] Sélection automatique du backend et diagnostic des capacités
- [x] Nettoyage par défaut des traces natives brutes
- [x] Mécanisme de repli portable multiplateforme
- [x] Validateur d’intégrité du flux d’événements
- [x] Protection contre l’ajout accidentel de plusieurs sessions
- [x] Tests unitaires de l’analyseur, du validateur et de la sélection de backend
- [x] Test d’intégration Linux natif dans la CI
- [x] Validation smoke CLI de bout en bout dans la CI
- [x] Harnais de benchmark de surcharge

## Explicitement hors de la Phase 1

Les éléments suivants restent des travaux futurs au lieu d’être faussement marqués comme terminés :

- backend Windows ETW attribuant le système de fichiers aux processus
- backend macOS Endpoint Security attribué aux processus
- backend Linux eBPF pour réduire la surcharge ptrace
- corrélation DNS vers domaine
- suivi de flux de données au niveau des octets en lecture/écriture
- télémétrie sémantique agent/tool/MCP
- matérialisation du graphe et visualisation interactive

Ces capacités peuvent alimenter le même modèle d’événements sans modifier le contrat de Phase 1.

## Pourquoi `strace` avant eBPF ?

La Phase 1 a besoin d’une implémentation de référence axée sur la correction de l’attribution processus/fichier/réseau et de la sémantique des événements. `strace` est simple à inspecter, facile à tester et capture les descendants de courte durée sans inventer de causalité.

Un backend eBPF est une optimisation naturelle à venir pour réduire la surcharge et permettre une collecte permanente, mais il doit implémenter la même sémantique d’événements de graphe au lieu de la définir implicitement.

## Contribuer

Les contributions particulièrement utiles incluent Linux eBPF, Windows ETW, macOS Endpoint Security, la résolution des chemins/entités, l’évaluation de la surcharge, la confidentialité/caviardage et des charges de travail d’agents reproductibles.

Pour tout nouveau backend de collecte, veuillez préserver la distinction entre attribution causale prouvée et observation au niveau de la session.
