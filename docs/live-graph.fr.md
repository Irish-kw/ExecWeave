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

Le collecteur runtime live utilise volontairement le backend multiplateforme `portable`. Avec v0.6.4, chaque exécution live peut également ingérer un second flux append-only de preuves spécialisées via un sidecar propre à l’exécution.

ExecWeave exporte le chemin du sidecar vers la commande lancée sous la forme :

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Les preuves spécialisées peuvent arriver automatiquement par plusieurs chemins sûrs pour l’attribution :

- hooks Claude Code, OpenAI Codex, Antigravity et Cursor déjà configurés ;
- plugin OpenCode installé ;
- probes loopback de catalogue de modèles lorsque ExecWeave lance des serveurs locaux Ollama, llama.cpp ou vLLM reconnus ;
- probe LM Studio post-lancement conditionné au succès pour `lms server start --port <port>`, uniquement si aucun endpoint compatible n’existait avant le lancement ;
- callback personnalisé ExecWeave pour LiteLLM Proxy, après configuration unique et lorsque le proxy est lancé dans l’environnement `execweave live` courant.

Cela ne signifie **pas** que `live` modifie silencieusement les paramètres provider, gateway ou runtime. Les intégrations hook/plugin/callback doivent être configurées une fois lorsque nécessaire. Le probing automatique de model-runtime est limité aux commandes de lancement locales reconnues et aux endpoints loopback. Les métadonnées de routage OpenRouter restent non automatiques, car l’observation HTTPS/réseau distante ne révèle pas les détails de routage provider faisant autorité.

Le backend Linux `strace` analyse actuellement les fichiers de trace après la fin de la commande. Il fournit une attribution plus forte fondée sur les appels système, mais ce n’est pas une source d’événements live dans l’implémentation actuelle. ExecWeave n’étiquette pas des preuves post-traitées comme télémétrie live.

Pour une attribution Linux post-exécution plus forte :

```bash
execweave record --backend strace --open -- claude
```

## Flux de données v0.6.4

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
commande ─→ portable ─→ events.jsonl ─────→ incremental live normalizer
                                                         ↓
                                                  GraphAccumulator
                                                         ↓
                                              localhost HTTP server
                                                         ↓
                                                 /live.json deltas
                                                         ↓
                                                   browser / Top
```

Les preuves OS runtime restent le flux indépendant de vérité terrain. Les preuves spécialisées sont normalisées provisoirement dans le graphe live ; elles ne peuvent ni réécrire le flux runtime brut ni fabriquer des preuves manquantes.

Le navigateur et le tableau de bord détaché `execweave top` consomment les snapshots/deltas numérotés de `/live.json`. `/graph.json` reste disponible comme endpoint de snapshot courant. L’ingestion incrémentale ne lit que les nouveaux octets JSONL ajoutés et met en tampon une dernière ligne incomplète jusqu’à son saut de ligne.

Lorsque la commande se termine, ExecWeave :

1. valide le flux runtime terminé ;
2. termine toute observation spécialisée post-commande, sûre pour l’attribution, préparée pour la commande lancée ;
3. si des preuves spécialisées existent, effectue la fusion canonique runtime + specialized dans `events.semantic.jsonl` ;
4. reconstruit le graphe final depuis ce flux canonique plutôt que de faire confiance à l’état live provisoire ;
5. écrit `graph.json` et le `viewer.html` autonome ;
6. marque le graphe live comme terminé et sert brièvement le viewer final avant d’arrêter le serveur local.

Si aucun événement spécialisé n’arrive, la matérialisation finale reste runtime-only.

## Intégrations spécialisées automatiquement visibles

| Intégration | Livraison automatique dans le Live Viewer v0.6.4 |
| --- | --- |
| Claude Code | **Oui**, après configuration des hooks ExecWeave |
| OpenAI Codex | **Oui**, après configuration des hooks ExecWeave |
| Antigravity | **Oui**, après configuration des hooks ExecWeave |
| Cursor | **Oui**, après configuration des hooks ExecWeave |
| OpenCode | **Oui**, après installation du plugin ExecWeave |
| Ollama | **Oui**, pour les lancements locaux `ollama serve` reconnus |
| llama.cpp | **Oui**, pour les lancements locaux `llama-server` reconnus |
| vLLM | **Oui**, pour les lancements locaux de serveur vLLM reconnus |
| LM Studio | **Oui**, après succès de `lms server start --port <port>` si l’endpoint était absent avant le lancement |
| LiteLLM Proxy | **Oui**, après configuration du callback et héritage du sidecar live par le proxy |
| OpenRouter | **Non** pour les métadonnées de routage automatiques ; l’activité OS/réseau du client local reste observable |

Ces intégrations partagent le même contrat de sidecar spécialisé par exécution, tout en conservant leurs couches et sémantiques de preuve. Un catalogue de modèles ne prouve pas qu’un Agent a causé une requête ; une réponse de gateway ne prouve pas quel processus OS l’a causée ; une identité absente n’est jamais inventée.

## Terminal Top

`top` ne s’affiche pas par-dessus le terminal de l’Agent. Le terminal d’origine reste interactif, tandis que le tableau de bord s’attache à la même session live localhost dans une fenêtre de terminal séparée :

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` ajoute le Viewer navigateur. Le dashboard détaché est uniquement un client attach et ne lance jamais un second Agent. Son URL attach interne est limitée à HTTP sur localhost.

## Exposition réseau

Le serveur live se lie uniquement à :

```text
127.0.0.1
```

Il n’est pas exposé sur `0.0.0.0` et n’est pas destiné à être accessible depuis d’autres hôtes du LAN.

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

`events.jsonl` reste runtime-only. `semantic.jsonl` est le sidecar spécialisé brut et peut contenir des preuves Agent/IDE, model-runtime ou inference-gateway. Le `graph.json` final est construit depuis `events.semantic.jsonl` lorsque des preuves spécialisées existent, sinon directement depuis `events.jsonl`.

Choisissez un autre répertoire :

```bash
execweave live --output-dir my-live-run --open -- claude
```

Les artefacts existants et non vides sont refusés plutôt qu’écrasés.

## Normalisation live provisoire

Pendant une exécution live, les deux flux JSONL peuvent être incomplets puisque la session n’est pas terminée.

Le normaliseur live fonctionne donc de manière incrémentale et conservatrice. L’identité de processus runtime déjà observée peut servir à résoudre les références de processus spécialisées, mais une identité absente n’est jamais devinée. Un événement spécialisé qui ne peut pas encore être normalisé ne devient pas une preuve plus forte simplement parce qu’il a été vu live.

Une troncature du sidecar réinitialise la matérialisation provisoire et rejoue les fichiers actuels. Les enregistrements JSONL finaux incomplets sont mis en tampon au lieu d’être traités comme des événements complets. Le graphe final est toujours reconstruit à partir de la fusion canonique après réussite de la validation runtime.

## Limite des probes model-runtime automatiques

L’observation automatique model-runtime est volontairement étroite. ExecWeave ne probe que les commandes de lancement de serveur local reconnues et les endpoints local/loopback. Les échecs de probe sont fail-open et ne modifient jamais le résultat de la commande lancée.

Pour Ollama, llama.cpp et vLLM, l’état/catalogue local des modèles peut être échantillonné pendant l’exécution du serveur. LM Studio est différent : `lms server start` est un launcher court pour un serveur persistant. ExecWeave prépare donc l’observation avant le lancement, refuse d’attribuer un endpoint compatible déjà existant à la session courante, puis ne matérialise le catalogue post-lancement qu’après une sortie réussie du launcher.

Les relations de catalogue conservent leur sémantique propre au runtime. Par exemple, la visibilité du catalogue LM Studio est `ADVERTISES_MODEL`, et non la preuve que les poids étaient résidents en mémoire.

## Limite du callback LiteLLM

LiteLLM Proxy peut charger une fois `execweave.litellm_callback.execweave_litellm_callback` via sa configuration de callback personnalisé. Lorsque le proxy s’exécute dans `execweave live`, il hérite de `EXECWEAVE_SEMANTIC_SIDECAR` et écrit uniquement les métadonnées routing/usage autorisées dans cette exécution.

Le callback ne persiste ni messages, ni contenu de réponse, ni paramètres modèle, ni métadonnées arbitraires, ni métadonnées de clé API, ni `api_base` provider. L’identité provider n’est pas inférée depuis le nom du modèle ou l’URL. Sans variable sidecar propre à l’exécution, le callback est un no-op.

Afficher le fragment de configuration LiteLLM :

```bash
execweave-litellm-callback --print-config
```

## Limites du backend portable

La couche runtime live actuelle hérite des limites du collecteur portable :

- la découverte des processus repose sur l’interrogation périodique ;
- les processus très courts peuvent être manqués ;
- les modifications du système de fichiers sont corrélées à la session plutôt qu’attribuées aux processus ;
- l’inspection réseau par processus dépend de la visibilité et des permissions du système d’exploitation.

Ces limites restent visibles dans les métadonnées d’attribution des événements. Le Live Viewer ne transforme pas une observation non causale en arête causale.

## Sécurité des grandes sessions

Les mises à jour live utilisent un historique borné de deltas au lieu de relire tout le flux d’événements à chaque interrogation. Lorsque le graphe dépasse le budget de sécurité du Viewer, l’endpoint live passe à une charge compacte contenant uniquement les compteurs afin que la collecte et la génération de l’artefact canonique final puissent continuer sans forcer le navigateur à matérialiser un grand graphe SVG dangereux.

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
- l’arrivée du sidecar avant que l’identité runtime soit prête ;
- la troncature et le rejeu du sidecar ;
- la reconstruction canonique finale runtime + specialized ;
- la livraison automatique via sidecar partagé pour Claude, Codex, Antigravity, Cursor et OpenCode ;
- les probes model-runtime locaux automatiques pour Ollama, llama.cpp, vLLM et la gestion LM Studio sûre pour l’attribution ;
- la confidentialité du callback LiteLLM, son comportement fail-open et la matérialisation finale dans le graphe live ;
- le comportement Top détaché sans lancement d’un second Agent ;
- les URL attach Top limitées à localhost ;
- l’installation clean-wheel de la commande de configuration du callback LiteLLM.
