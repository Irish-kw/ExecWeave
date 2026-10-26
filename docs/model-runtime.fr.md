# Model Runtime Integrations

<!-- i18n-nav:start -->
<p align="center">
  <a href="model-runtime.md">English</a> |
  <a href="model-runtime.zh-TW.md">繁體中文</a> |
  <a href="model-runtime.zh-CN.md">简体中文</a> |
  <a href="model-runtime.ja.md">日本語</a> |
  <a href="model-runtime.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="model-runtime.de.md">Deutsch</a> |
  <a href="model-runtime.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Les model runtimes sont séparés des adaptateurs semantic Agent/IDE et des inference gateways. Ils décrivent ce qu'un point d'intégration d'inférence local ou self-hosted rapporte ; ils ne prouvent pas quel Agent a initié une requête.

Le baseline actuel prend en charge **Ollama**, **llama.cpp**, **vLLM** et **LM Studio**.

## CLI

Capturer une réponse finale runtime fournie sur stdin :

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Capturer un échange request+response fourni par l'appelant :

```bash
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
```

`exchange` accepte les quatre runtimes et exige des objets JSON `request` et `response`. Il enregistre des preuves explicitement fournies par l'appelant ; ce n'est pas une interception réseau transparente.

L'état runtime et les catalogues de modèles restent disponibles via `probe`. Les endpoints localhost par défaut sont Ollama `11434`, llama.cpp `8080`, vLLM `8000` et LM Studio `1234`.

## Contenu full-fidelity

v0.6.5 stocke le contenu complet exposé par le point d'intégration model-runtime sélectionné dans un store local SHA-256 adressé par contenu. `event` conserve la réponse finale complète fournie sans prétendre voir la requête. `exchange` peut conserver requête et réponse fournies, y compris messages/prompts, définitions/appels/résultats d'outils, contenu assistant généré, champs reasoning/thinking lorsqu'ils sont explicitement présents, configuration de génération et autres valeurs de réponse prises en charge par le payload runtime.

Le sidecar sémantique JSONL contient des références plutôt que de grandes copies inline. Les métadonnées compactes de usage/timing/model restent disponibles pour les graphes et requêtes.

`content_complete_from_source: true` signifie qu'ExecWeave a stocké toute la valeur fournie à la CLI/au point d'intégration. Cela ne signifie pas que le runtime a exposé un état caché du modèle, que la requête correspond nécessairement à la requête wire finale après réécriture, ni qu'ExecWeave a observé des octets qui ne lui ont pas été fournis.

Les valeurs applicatives sensibles incluses dans request/response sont conservées. L'assainissement endpoint/path et le filtrage provider-metadata ne constituent pas une redaction générale du contenu.

## Preuves propres au runtime

Ollama peut également rapporter l'état des modèles chargés via `/api/ps`. llama.cpp peut exposer timing/throughput, `/v1/models` et éventuellement des métriques agrégées `/metrics` ; les lignes Prometheus étiquetées susceptibles de contenir des identifiants locaux sensibles restent limitées par l'adaptateur metadata. vLLM et LM Studio partagent le parsing OpenAI-compatible pour responses/catalogues tout en conservant des sémantiques de relation propres au runtime.

Les relations de catalogue restent volontairement distinctes : selon ce que la source prouve, un runtime peut `LOADED_MODEL`, `SERVES_MODEL` ou `ADVERTISES_MODEL`. La visibilité catalogue LM Studio reste `ADVERTISES_MODEL` ; un élément de catalogue ne prouve pas automatiquement que les poids sont résidents en mémoire.

## Confidentialité et frontière des preuves

Le contenu model-runtime peut contenir prompts/messages complets, données d'outils, réponses générées, texte reasoning/thinking, paramètres de modèle, configuration, chemins, identifiants et valeurs applicatives sensibles. Examinez tout le répertoire du run avant partage.

Une réponse runtime ou un exchange prouve seulement ce que ce point d'intégration a fourni. Il ne prouve pas à lui seul quel Agent a initié la requête, quelle gateway l'a routée, quel processus OS l'a causée ou que des octets de fichier ont circulé vers un endpoint modèle/réseau. L'identité cross-layer nécessite des identifiants partagés explicites ou une corrélation conservatrice explicitement marquée.
