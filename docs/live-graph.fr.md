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

La couche runtime en direct utilise volontairement le backend multiplateforme `portable`. Avec v0.6.4, la session live peut aussi ingérer un second flux append-only de preuves spécialisées via un sidecar sémantique propre à l’exécution.

ExecWeave exporte le chemin du sidecar vers la commande lancée sous la forme :

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Les hooks Claude Code, OpenAI Codex, Gemini CLI et Cursor déjà configurés héritent automatiquement de cette variable. Le plugin OpenCode installé fait de même. Leurs événements sémantiques peuvent donc apparaître dans le même Live Viewer sans passer à une commande `*-record` distincte.

Cela ne signifie **pas** que `live` modifie silencieusement les paramètres du fournisseur. L’intégration hook/plugin doit avoir été configurée une fois au préalable. Les métadonnées model-runtime et inference-gateway nécessitent encore leurs émetteurs explicites tant que ces intégrations ne disposent pas d’un chemin d’observation automatique.

Le backend Linux `strace` analyse actuellement les fichiers de trace après la fin de la commande. Il fournit une attribution plus forte fondée sur les appels système, mais ce n’est pas une source d’événements en direct dans l’implémentation actuelle. ExecWeave n’étiquette pas des preuves post-traitées comme télémétrie en direct.

Pour une attribution Linux post-exécution plus forte, utilisez :

```bash
execweave record --backend strace --open -- claude
```

## Flux de données v0.6.4

```text
                         ┌─ hook / plugin fournisseur ─→ semantic.jsonl ─┐
commande ─→ portable ─→ events.jsonl ───────────────────────────────────┤
                                                                      ↓
                                                      normaliseur live incrémental
                                                                      ↓
                                                           GraphAccumulator
                                                                      ↓
                                                        serveur HTTP localhost
                                                                      ↓
                                                          deltas /live.json
                                                                      ↓
                                                        navigateur / Top
```

Les preuves runtime du système d’exploitation restent le flux indépendant de vérité terrain. Les preuves spécialisées sont normalisées provisoirement dans le graphe live ; elles ne peuvent ni réécrire le flux runtime brut ni fabriquer des preuves manquantes.

Le navigateur et le tableau de bord détaché `execweave top` consomment les snapshots/deltas numérotés de `/live.json`. `/graph.json` reste disponible comme endpoint de snapshot courant. L’ingestion incrémentale ne lit que les nouveaux octets JSONL ajoutés et met en tampon une dernière ligne incomplète jusqu’à l’arrivée de son saut de ligne.

Lorsque la commande se termine, ExecWeave :

1. valide le flux runtime terminé ;
2. si des preuves spécialisées existent, effectue la fusion canonique runtime + semantic dans `events.semantic.jsonl` ;
3. reconstruit le graphe final à partir de ce flux canonique au lieu de faire confiance à l’état live provisoire ;
4. écrit `graph.json` et le `viewer.html` autonome ;
5. marque le graphe live comme terminé et sert brièvement le visualiseur final avant d’arrêter le serveur local.

Si aucun événement spécialisé n’arrive, la matérialisation finale reste runtime-only.

## Intégrations Agent automatiquement visibles

| Intégration | Livraison automatique dans le Live Viewer v0.6.4 |
| --- | --- |
| Claude Code | **Oui**, après configuration des hooks ExecWeave |
| OpenAI Codex | **Oui**, après configuration des hooks ExecWeave |
| Gemini CLI | **Oui**, après configuration des hooks ExecWeave |
| Cursor | **Oui**, après configuration des hooks ExecWeave |
| OpenCode | **Oui**, après installation du plugin ExecWeave |

Les cinq intégrations utilisent le même contrat de sidecar par exécution. La couverture de régression CI invoque chaque adaptateur fournisseur avec un même `EXECWEAVE_SEMANTIC_SIDECAR` et vérifie que les preuves fournisseur obtenues sont matérialisées dans le graphe live.

## Terminal Top

`top` ne s’affiche plus par-dessus le terminal de l’Agent. Le terminal d’origine reste interactif pour l’Agent, tandis que le tableau de bord s’attache à la même session live localhost dans une fenêtre de terminal séparée :

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` ajoute le Viewer navigateur. Le tableau de bord détaché est uniquement un client attach et ne lance jamais un second Agent. Son URL attach interne est limitée à HTTP sur localhost.

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
├── semantic.jsonl
├── events.semantic.jsonl      # matérialisé uniquement si des preuves spécialisées existent
├── graph.json
└── viewer.html
```

`events.jsonl` reste runtime-only. `semantic.jsonl` est le sidecar spécialisé brut. Le `graph.json` final est construit depuis `events.semantic.jsonl` lorsque des preuves spécialisées existent, sinon directement depuis `events.jsonl`.

Choisissez un autre répertoire avec :

```bash
execweave live --output-dir my-live-run --open -- claude
```

Les artefacts existants et non vides sont refusés plutôt qu’écrasés.

## Normalisation live provisoire

Pendant une exécution live, les deux flux JSONL peuvent être incomplets puisque la session n’est pas encore terminée.

Le normaliseur live fonctionne donc de manière incrémentale et conservatrice. L’identité de processus runtime déjà observée peut servir à résoudre les références de processus spécialisées, mais une identité absente n’est jamais devinée. Les événements spécialisés qui ne peuvent pas encore être normalisés ne deviennent pas des preuves plus fortes simplement parce qu’ils ont été vus en direct.

Une troncature du sidecar réinitialise la matérialisation provisoire et rejoue les fichiers courants. Les enregistrements JSONL finaux incomplets sont mis en tampon au lieu d’être traités comme des événements complets. Le graphe final est toujours reconstruit à partir de la fusion canonique après réussite de la validation runtime.

## Limites du backend portable

La couche runtime live actuelle hérite des garanties du collecteur portable :

- la découverte des processus repose sur l’interrogation périodique ;
- les processus très courts peuvent être manqués ;
- les modifications du système de fichiers sont corrélées à la session plutôt qu’attribuées aux processus ;
- l’inspection réseau par processus dépend de la visibilité et des permissions du système d’exploitation.

Ces limites restent visibles dans les métadonnées d’attribution des événements. Le Live Viewer ne transforme pas une observation non causale en arête causale.

## Sécurité des grandes sessions

Les mises à jour live utilisent un historique borné de deltas au lieu de relire tout le flux d’événements à chaque interrogation. Lorsque le graphe dépasse le budget de sécurité du Viewer, l’endpoint live passe à une charge compacte contenant uniquement les compteurs afin que la collecte et la génération de l’artefact canonique final puissent continuer sans forcer le navigateur à matérialiser un graphe SVG dangereux.

## Futurs backends live natifs

Les collecteurs prévus comprennent :

- Linux eBPF ;
- Windows ETW ;
- macOS Endpoint Security.

L’objectif est de préserver la même sémantique d’événements ExecWeave tout en améliorant l’exhaustivité, l’attribution aux processus et la surcharge d’exécution.

## Couverture CI

La configuration CI du dépôt couvre :

- le démarrage d’une session live localhost et la génération des artefacts finaux ;
- le comportement snapshot/delta numéroté et la resynchronisation ;
- les derniers enregistrements JSONL incomplets ;
- l’arrivée du sidecar sémantique avant que l’identité runtime ne soit prête ;
- la troncature et le rejeu du sidecar sémantique ;
- la reconstruction canonique finale runtime + semantic ;
- la livraison automatique par sidecar partagé pour Claude, Codex, Gemini, Cursor et OpenCode ;
- le comportement Top détaché sans lancement d’un second Agent ;
- les URL attach Top limitées à localhost.
