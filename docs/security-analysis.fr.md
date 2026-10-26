<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <a href="security-analysis.zh-CN.md">简体中文</a> |
  <a href="security-analysis.ja.md">日本語</a> |
  <a href="security-analysis.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="security-analysis.de.md">Deutsch</a> |
  <a href="security-analysis.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Analyse de sécurité

ExecWeave inclut une couche de règles conservatrice et explicable au-dessus d’un graphe d’exécution terminé.

```bash
execweave analyze run.graph.json
```

Écrire le même rapport dans un fichier :

```bash
execweave analyze run.graph.json --output analysis.json
```

Le schéma d’analyse actuel est `0.2`.

## Objectif

La couche d’analyse priorise les preuves du graphe pour examen. Elle n’affirme pas qu’un agent est malveillant simplement parce qu’il a touché une ressource sensible ou contacté le réseau.

La règle centrale est :

> **Ne pas convertir la cooccurrence ou la filiation de processus en affirmations de flux de données.**

## Règles actuelles

### Accès à des fichiers sensibles

La règle recherche les arêtes de fichiers impliquant des emplacements ou noms de fichiers sensibles courants, notamment :

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- configuration Docker
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- noms courants de clés privées SSH

Une arête de processus causale fondée sur un appel système constitue une preuve plus forte qu’une observation de session non causale.

### Contact réseau externe

La règle identifie les arêtes de processus vers des endpoints réseau externes tout en excluant les adresses manifestement loopback/privées/link-local.

La télémétrie runtime actuelle repose principalement sur les endpoints IP. La corrélation DNS/domaine est un travail futur.

### Chemin sensible fichier-vers-réseau possible dans le même processus

Lorsque le **même processus** possède une preuve causale d’accès à un fichier sensible puis une activité réseau externe causale ultérieure, ExecWeave émet un finding de priorisation.

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

Le finding enregistre :

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

Le graphe prouve que le processus a réalisé les deux actions dans cet ordre chronologique. Il ne prouve **pas** que des octets du fichier ont été envoyés sur la connexion.

### Chemin délégué possible fichier-sensible-vers-réseau

Le schéma d’analyse `0.2` suit également les arêtes causales chronologiques `SPAWNED`.

Exemple :

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

Un finding délégué n’est émis que si :

1. l’arête d’accès au fichier sensible est causale ;
2. l’arête ou la chaîne `SPAWNED` est causale ;
3. la séquence de spawn se produit après la séquence d’accès au fichier sensible ;
4. la preuve réseau externe du descendant se produit après la chaîne de spawn ;
5. la profondeur du chemin reste dans la limite conservatrice de parcours de l’analyseur.

Cela prouve un chemin chronologique de filiation de processus. Cela ne prouve toujours **pas** que l’enfant a reçu les données du fichier depuis le parent.

Les findings délégués enregistrent explicitement :

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` est une preuve de création/filiation de processus, pas une preuve d’héritage mémoire, d’écriture dans un pipe, de transfert par socketpair, mémoire partagée, transfert de secret par variable d’environnement ou autre mouvement concret de données.

Les affirmations réelles de flux de données ou d’exfiltration nécessitent des preuves plus fortes, comme le taint tracking, une provenance consciente de l’IPC ou une télémétrie lecture/écriture/réseau au niveau des octets.

## Sévérité

Les valeurs de sévérité sont des niveaux de priorisation et non des scores de vulnérabilité :

- `high`
- `medium`
- `low`
- `info`

Exemples actuels :

- connexion externe seule : informative ;
- accès à un fichier sensible : dépend de la relation et de la force de l’attribution ;
- lecture sensible dans le même processus suivie d’une connexion externe confirmée : signal de haute priorité ;
- chemin délégué via processus enfant : inférieur à un chemin équivalent dans le même processus, car le transfert de données entre processus n’est pas prouvé.

## Dépendance au backend

La qualité de l’analyse est limitée par la qualité du collecteur.

Le backend Linux `strace` de référence peut fournir des preuves d’appels système attribuées aux processus pour les opérations prises en charge. Le backend portable possède une attribution plus faible pour le système de fichiers et ne peut donc pas soutenir les mêmes conclusions au niveau des processus.

L’analyseur respecte les métadonnées `causal` du graphe au lieu de promouvoir des preuves plus faibles.

## Sortie

Le rapport contient :

- la version du schéma d’analyse
- l’identifiant de session
- le nombre total de findings
- les nombres par sévérité
- les limitations explicites
- l’identifiant de règle par finding
- le titre et le résumé
- les identifiants de nœuds associés
- les identifiants d’arêtes associés
- les identifiants d’événements de preuve
- les attributs spécifiques à la règle

Les findings délégués incluent en plus la chaîne de processus, le nombre de sauts de délégation, les séquences de spawn et les garanties négatives explicites concernant l’héritage de données/IPC/flux de données.

## Futures couches d’analyse

Parmi les ajouts possibles :

- résolution d’entités de credentials et secrets
- corrélation DNS/domaine et contexte
- arêtes IPC explicites
- provenance des variables d’environnement et handles hérités
- contexte sémantique agent/tool/MCP
- détection d’anomalies
- classement des chemins d’attaque
- suivi de flux de données / taint au niveau des octets
- politique runtime allow / warn / block

Ces évolutions doivent continuer à préserver la distinction entre preuves observées, risque inféré, filiation de processus et flux de données causal prouvé.
