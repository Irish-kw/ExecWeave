# Inference Gateway Integrations

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

Les inference gateways constituent une couche de preuve distincte entre un Agent/client et un fournisseur/runtime de modèle. ExecWeave modélise actuellement **OpenRouter** et **LiteLLM Proxy** tout en gardant séparés requested model, resolved model, routed provider et deployment identity.

## CLI

Capturer une réponse finale de gateway fournie sur stdin :

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
```

Pour OpenRouter uniquement, capturer un objet request+response fourni par l'appelant :

```bash
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

`exchange` exige des champs JSON-object `request` et `response` sur stdin. Il s'agit de preuves explicitement fournies par l'appelant, **pas** d'une interception transparente du trafic réseau.

Les métadonnées de génération OpenRouter restent disponibles via `generation`.

## Frontière full-fidelity OpenRouter

Pour `event --gateway openrouter`, v0.6.5 stocke la réponse finale complète fournie dans le store local adressé par contenu tout en émettant le résumé compact routing/usage. Pour `exchange --gateway openrouter`, la requête et la réponse complètes fournies par l'appelant peuvent être conservées.

`content_complete_from_source: true` signifie que toute la valeur fournie à ce point d'intégration a été stockée. Cela ne prétend pas voir une requête avant réécriture côté fournisseur, des étapes cachées de routage, des états internes du modèle ou des octets réseau non observés par ExecWeave.

Les valeurs applicatives sensibles incluses dans le contenu request/response fourni sont conservées. L'identité de l'endpoint est assainie séparément ; le retrait de query parameters/fragments et le filtrage d'identifiants de transport reconnus ne remplacent pas la redaction du contenu.

## Frontière LiteLLM

LiteLLM reste une intégration orientée métadonnées dans le baseline v0.6.5. Le parser de réponse et le callback personnalisé optionnel conservent les champs routing/usage via un contrat strict ; le fait qu'OpenRouter prenne en charge le full-fidelity ne transforme pas automatiquement le callback LiteLLM en capture de contenu complet.

Le callback s'active en imprimant sa configuration puis en lançant le proxy configuré dans le run ExecWeave courant :

```bash
execweave-litellm-callback --print-config
execweave live --open -- litellm --config config.yaml
```

Sans `EXECWEAVE_SEMANTIC_SIDECAR`, le callback est no-op. L'identité provider/deployment n'est émise que lorsque des preuves autoritatives sont disponibles ; ExecWeave ne la déduit pas d'un préfixe de nom de modèle ou d'une URL fournisseur.

## Identité exacte gateway ↔ model-runtime

Si l'appelant dispose déjà d'un identifiant de requête explicitement partagé, `execweave-inference-link` peut connecter les nœuds gateway et runtime sans fusionner les couches. L'identifiant brut n'est pas persisté ; le lien utilise un hash d'identité dérivé par SHA-256.

```text
identity_exact: true
inferred: false
causal: false
```

Il s'agit d'une identité logique exacte de requête, pas d'une preuve qu'un Agent ou processus OS précis a causé l'inférence.

## Confidentialité et frontière des preuves

Les artefacts full-fidelity OpenRouter peuvent contenir les contenus request/response complets et des valeurs applicatives sensibles. Les artefacts LiteLLM suivent leur contrat metadata/callback plus étroit. Traitez les preuves gateway comme sensibles et examinez-les avant partage.

Les observations gateway prouvent uniquement ce que le point d'intégration a rapporté ou les données de routage autoritatives fournies avec lui. Elles ne prouvent pas à elles seules quel Agent local a initié la requête, quel processus runtime l'a servie ni quel processus OS l'a causée. En l'absence d'identité partagée, il ne faut pas la remplacer par un rapprochement de timestamp ou de nom de modèle.
