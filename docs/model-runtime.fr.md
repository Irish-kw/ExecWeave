# Intégrations de runtime de modèle

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

Les runtimes de modèle sont séparés des adaptateurs sémantiques Agent/IDE et des passerelles d’inférence. Ils décrivent ce qu’un serveur d’inférence local ou auto-hébergé rapporte ; ils ne prouvent pas quel Agent a initié une requête.

Le baseline actuel prend en charge **Ollama**, **llama.cpp**, **vLLM** et **LM Studio**.

## CLI

Convertir les métadonnées de réponse finale en événements d’inférence :

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

Interroger l’état du runtime ou les catalogues de modèles :

```bash
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime llamacpp --metrics --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime lmstudio --sidecar model-runtime.jsonl
```

Les endpoints par défaut sont :

- Ollama : `http://localhost:11434`
- llama.cpp : `http://localhost:8080`
- vLLM : `http://localhost:8000`
- LM Studio : `http://localhost:1234`

## Couche partagée compatible OpenAI

llama.cpp, vLLM et LM Studio réutilisent un analyseur compatible OpenAI pour l’usage des réponses finales et les métadonnées de catalogue `/v1/models`. La couche partagée normalise `prompt_tokens` / `completion_tokens` de style Chat Completions et `input_tokens` / `output_tokens` de style Responses, tout en ne conservant que des métadonnées de tokens sur liste blanche telles que les nombres de tokens en cache et de raisonnement.

Les preuves spécifiques au runtime restent hors de l’analyseur commun. llama.cpp conserve ses champs de timing et son adaptateur de métriques Prometheus au lieu d’imposer cette sémantique à vLLM ou LM Studio.

## Modèle de graphe

La couche runtime peut produire :

```text
model_runtime --SERVED_INFERENCE--> inference_request
inference_request --USED_MODEL--> model
model_runtime --LOADED_MODEL--> model
model_runtime --SERVES_MODEL--> model
model_runtime --ADVERTISES_MODEL--> model
model_runtime --REPORTED_METRICS--> model_runtime_snapshot
```

Ces relations ont volontairement des significations différentes.

## Ollama

Les métadonnées de réponse finale peuvent inclure le nombre de tokens de prompt/complétion, la durée de chargement, la durée d’évaluation du prompt, la durée de génération et la raison de fin.

Les instantanés `/api/ps` peuvent exposer des métadonnées de modèles chargés telles que la taille VRAM, la longueur de contexte, le format, la famille, le nombre de paramètres et la quantification. Cela est représenté comme `LOADED_MODEL` car l’endpoint rapporte les modèles actuellement chargés.

## llama.cpp

Les réponses compatibles OpenAI contribuent un usage normalisé ainsi que des métadonnées de timing/débit propres à llama.cpp. `/v1/models` est représenté comme `SERVES_MODEL`, et `/metrics` facultatif contribue des métriques runtime agrégées.

Les lignes Prometheus avec labels sont ignorées, car les labels peuvent contenir des chemins de modèles locaux sensibles ou d’autres identifiants.

Les identifiants de modèles llama.cpp ressemblant à des chemins locaux ou fichiers GGUF sont caviardés : l’identifiant natif complet est hashé pour l’identité d’entité, tandis que seul le nom de base est affiché.

## vLLM

vLLM réutilise la couche de réponse compatible OpenAI et de catalogue de modèles. `/v1/models` est représenté comme `SERVES_MODEL` car il décrit les modèles exposés par cet endpoint de service.

Aucun prompt, réponse, texte de raisonnement, choice, logprob ou token généré n’est copié dans les événements ExecWeave.

## LM Studio

LM Studio réutilise le même analyseur de réponse compatible OpenAI, mais son résultat `/v1/models` est représenté comme `ADVERTISES_MODEL`, et non `LOADED_MODEL`.

Cette distinction est volontaire : LM Studio peut rendre visibles au serveur des modèles téléchargés, y compris dans des configurations où un modèle est chargé à la demande. Une entrée de catalogue ne prouve donc pas à elle seule que les poids du modèle résidaient en mémoire au moment de l’observation.

## Limite de confidentialité

ExecWeave exclut volontairement de cette couche le texte des prompts, le contenu des réponses, le texte de pensée/raisonnement, les choices, logprobs et tokens générés bruts.

Les métadonnées sur liste blanche peuvent inclure l’identité du modèle, l’identité de la requête, les nombres de tokens prompt/entrée et complétion/sortie, le total de tokens, les nombres de tokens en cache et de raisonnement ainsi que les métadonnées de timing spécifiques au runtime. Les chemins absolus de modèles locaux sont caviardés pour les runtimes locaux compatibles OpenAI pris en charge ; llama.cpp conserve un caviardage plus strict des chemins GGUF.

Les métriques runtime agrégées ne sont pas automatiquement attribuées à un Agent ou à une requête d’inférence spécifique.

## Limite de preuve

Une API runtime prouve seulement ce que ce serveur d’inférence a rapporté. Elle ne prouve pas à elle seule quel Agent a initié la requête, quelle passerelle l’a routée ni quel processus OS l’a causée.

L’identité inter-couches nécessite des identifiants partagés explicites ou un mécanisme de corrélation conservateur défini séparément. Une corrélation dérivée doit rester marquée comme inférence plutôt que preuve causale.
