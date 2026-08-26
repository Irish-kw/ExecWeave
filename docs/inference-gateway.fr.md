# Intégrations de passerelle d’inférence

<!-- i18n-nav:start -->
<p align="center">
  <a href="inference-gateway.md">English</a> |
  <a href="inference-gateway.zh-TW.md">繁體中文</a> |
  <a href="inference-gateway.zh-CN.md">简体中文</a> |
  <a href="inference-gateway.ja.md">日本語</a> |
  <a href="inference-gateway.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="inference-gateway.de.md">Deutsch</a> |
  <a href="inference-gateway.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

Les passerelles d’inférence forment une couche distincte entre un Agent/client et le fournisseur/runtime de modèle. Le baseline actuel prend en charge **OpenRouter** et **LiteLLM Proxy**.

ExecWeave conserve le modèle demandé, le modèle résolu, le fournisseur routé et l’identité du déploiement comme preuves distinctes au lieu de les réduire à un seul champ modèle.

## CLI

Convertir une réponse finale OpenRouter :

```bash
execweave-inference-gateway event \
  --gateway openrouter \
  --requested-model openrouter/auto \
  --provider-name OpenAI \
  --sidecar gateway.jsonl
```

Convertir une réponse finale LiteLLM Proxy :

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

Convertir les métadonnées de génération OpenRouter :

```bash
execweave-inference-gateway generation \
  --gateway openrouter \
  --sidecar gateway.jsonl
```

Lorsqu’un appelant dispose d’une identité de requête partagée explicite entre une observation de passerelle et une observation de runtime modèle, reliez les deux nœuds de requête existants :

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

Le JSON de réponse de la passerelle est lu depuis stdin. Les identités d’endpoint par défaut sont :

- OpenRouter : `https://openrouter.ai/api/v1`
- LiteLLM Proxy : `http://localhost:4000`

## Modèle de graphe

```text
inference_gateway --SERVED_INFERENCE--> inference_request
inference_request --REQUESTED_MODEL--> model
inference_request --ROUTED_TO_MODEL--> model
inference_request --ROUTED_TO_PROVIDER--> inference_provider
inference_request --ROUTED_TO_DEPLOYMENT--> inference_deployment
inference_gateway --REPORTED_GENERATION_METADATA--> inference_request
inference_request --SAME_INFERENCE_REQUEST--> inference_request
```

Par exemple, une requête LiteLLM peut conserver :

```text
requested_model = assistant
resolved_model  = azure/gpt-5
provider        = Azure
deployment      = deployment-west
```

Ces faits ne sont pas interchangeables.

## OpenRouter

Les métadonnées de réponse OpenRouter conservent le modèle demandé séparément du modèle de réponse et d’un fournisseur routé explicitement observé. Les métadonnées de génération spécifiques à OpenRouter peuvent aussi rapporter latence, temps de génération, coût, nombres de tokens natifs, état de streaming et état d’annulation.

## LiteLLM Proxy

<!-- litellm-auto-live-v064 -->
### Callback automatique dans Live Viewer

LiteLLM Proxy peut charger une fois le custom callback ExecWeave puis envoyer automatiquement les métadonnées de routage/usage vers le sidecar du run `execweave live` courant. Affichez le fragment de configuration avec :

```bash
execweave-litellm-callback --print-config
```

Ajoutez le callback imprimé à `litellm_settings.callbacks` sans remplacer les callbacks existants. Son import path est `execweave.litellm_callback.execweave_litellm_callback`; ExecWeave doit donc être importable dans l’environnement Python qui exécute LiteLLM Proxy.

Lancez ensuite le proxy local configuré sous ExecWeave :

```bash
execweave live --open -- litellm --config config.yaml
```

`execweave live` transmet `EXECWEAVE_SEMANTIC_SIDECAR` au processus proxy. Sans cette variable propre au run, le callback est un no-op. `EXECWEAVE_LITELLM_ENDPOINT` peut remplacer l’identité de l’endpoint ; sinon le callback utilise `PROXY_BASE_URL`, puis `http://localhost:4000`.

Le callback ne lit dans `standard_logging_object` qu’une liste blanche : call ID, model group, resolved model, deployment model ID, token counts, reported cost, response time, cache-hit et call type. Il ne conserve ni messages, ni contenu de réponse, ni paramètres de modèle, ni metadata arbitraire, ni metadata de clé API, ni `api_base` provider. `model_group` reste le requested model, `model` le resolved model et `model_id` l’identité de deployment ; aucun provider n’est déduit sans preuve autoritative.


LiteLLM est modélisé comme un `inference_gateway`, et non comme un `model_runtime`. Sa réponse compatible OpenAI contribue les métadonnées de requête/modèle/usage via la même couche de preuves de passerelle.

`--provider-name` et `--deployment-id` ne sont émis que lorsque des métadonnées de routage faisant autorité sont disponibles pour l’appelant ou l’adaptateur. ExecWeave **n’infère pas** un fournisseur ou un déploiement à partir d’une chaîne de modèle telle que `azure/...`. Lorsque ces faits de routage sont indisponibles, les arêtes correspondantes sont omises.

## Identité exacte Gateway ↔ Model Runtime

`execweave-inference-link` est volontairement plus strict qu’une corrélation temporelle. Il crée `SAME_INFERENCE_REQUEST` uniquement lorsque l’appelant possède déjà un identifiant explicite partagé entre les observations de passerelle et de runtime. Il ne devine jamais l’identité à partir des horodatages, noms de modèles, nombres de tokens, latence ou autres signaux de similarité.

Les requêtes passerelle et runtime restent des nœuds distincts, préservant leurs métadonnées propres à chaque couche. L’arête d’identité est marquée :

```text
identity_exact: true
inferred: false
causal: false
```

Cela signifie que les deux observations se rapportent à la même requête logique d’inférence selon l’identité partagée fournie. Cela ne prouve **pas** qu’un Agent ou processus OS particulier a causé la requête. Sans identité partagée explicite, ExecWeave ne crée pas cette arête.

## Métadonnées d’usage

L’analyseur de réponse met sur liste blanche des métadonnées telles que les tokens de prompt/entrée, de complétion/sortie, le total de tokens, les tokens de prompt mis en cache, les tokens d’écriture en cache, les nombres de tokens de raisonnement et le coût rapporté.

## Limite de confidentialité

ExecWeave ne persiste ni le texte des prompts, ni le contenu des réponses/complétions, ni le texte de raisonnement, ni les choices, ni les champs arbitraires du payload fournisseur. Les credentials, paramètres de requête et fragments des endpoints de passerelle sont retirés de l’identité d’endpoint stockée.

Le modèle demandé original n’est jamais deviné à partir de la réponse ; il doit être fourni explicitement par l’appelant lorsque cette preuve existe. Le `--shared-request-id` brut utilisé pour l’identité inter-couches exacte n’est pas persisté ; ExecWeave ne stocke qu’un hash d’identité dérivé de SHA-256 sur l’événement de liaison.

## Limite de preuve

Les métadonnées de réponse d’une passerelle prouvent uniquement ce que cette passerelle a rapporté ou ce que des métadonnées de routage faisant autorité ont fourni avec la réponse. Elles ne prouvent pas quel Agent local a initié la requête, quel processus de runtime modèle l’a servie, ni quel processus OS l’a causée.

Les événements de passerelle restent donc non causaux (`causal: false`) et séparés des preuves sémantiques Agent/IDE, des preuves Model Runtime et des preuves OS Runtime. Une identité de requête partagée exacte peut relier les observations Gateway et Model Runtime sans fusionner leurs couches. Toute corrélation inférée séparément doit rester explicitement inférée et ne jamais être représentée comme preuve causale.
