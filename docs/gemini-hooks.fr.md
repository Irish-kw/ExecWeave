<!-- i18n-nav:start -->
<p align="center">
  <a href="gemini-hooks.md">English</a> |
  <a href="gemini-hooks.zh-TW.md">繁體中文</a> |
  <a href="gemini-hooks.zh-CN.md">简体中文</a> |
  <a href="gemini-hooks.ja.md">日本語</a> |
  <a href="gemini-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="gemini-hooks.de.md">Deutsch</a> |
  <a href="gemini-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Hooks Gemini CLI

ExecWeave ingère les hooks Gemini CLI comme preuves semantic/content fournisseur et conserve cette couche séparée des preuves d'exécution OS collectées indépendamment. Les hooks Gemini expliquent ce que le fournisseur a exposé ; ils ne prouvent pas à eux seuls quel processus OS a effectué une action.

## Surface de hooks actuelle

`execweave-gemini-hook --print-config` enregistre actuellement :

- `SessionStart`
- `SessionEnd`
- `BeforeAgent`
- `AfterAgent`
- `BeforeModel`
- `AfterModel`
- `BeforeToolSelection`
- `BeforeTool`
- `AfterTool`
- `PreCompress`
- `Notification`

Les hooks outil utilisent la surface de matcher du fournisseur et la commande générée est fail-open par défaut. Configurez puis enregistrez un run :

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

## Contenu full-fidelity

v0.6.5 stocke les valeurs complètes explicitement fournies par le hook Gemini dans un store local adressé par contenu. Selon l'événement, cela peut inclure le prompt utilisateur, l'objet complet de requête modèle, l'objet réponse/chunk modèle, l'entrée outil, la réponse outil avec `llmContent` / `returnDisplay` / champs d'erreur fournisseur, la réponse finale de l'Agent et d'autres valeurs provider exposées par le hook.

Le sidecar sémantique JSONL stocke des références plutôt que de grandes copies inline. Des valeurs identiques sont dédupliquées par SHA-256.

Les projections de métadonnées fournisseur excluent les champs de transport reconnus tels que les headers d'autorisation. Ce filtrage ne nettoie pas les valeurs applicatives dans le contenu complet. Par exemple, une valeur sensible incluse dans une entrée outil ou une requête modèle reste dans le contenu conservé.

`content_complete_from_source: true` signifie qu'ExecWeave a stocké l'intégralité du champ/de la valeur reçue. Cela n'affirme pas que Gemini a exposé une requête wire finale cachée, un état interne du modèle ou une étape absente du payload du hook.

## Identité des outils et corrélation

Gemini ne fournit pas un identifiant unique partagé entre `BeforeTool` et `AfterTool`. ExecWeave ne fabrique donc pas d'arête directe d'identité before/after. Une empreinte déterministe d'outil peut être conservée comme indice diagnostique, mais des appels identiques répétés restent des observations distinctes.

Les hooks Gemini ne fournissent pas non plus le PID enfant OS. Les ponts Tool → Process ne sont donc dérivés que lorsqu'une preuve runtime indépendante soutient un seul candidat :

```text
inferred: true
causal: false
```

Les commandes ambiguës, non appariées, composées, shell builtin ou non prises en charge ne produisent aucun pont.

## Confidentialité et frontière des preuves

Les artefacts de contenu Gemini peuvent contenir prompts, requêtes/réponses modèle complètes, entrées/résultats d'outils, contenu de fichiers renvoyé par des outils, champs MCP/applicatifs, réponses finales, identifiants, commandes, chemins et valeurs sensibles intégrées. Examinez le répertoire du run avant partage.

ExecWeave ne lit pas automatiquement `transcript_path` simplement parce que le hook l'indique. Une valeur fournisseur stockée ne prouve pas non plus une exécution OS, un accès fichier terminé ou un flux de données au niveau des octets. Les preuves runtime indépendantes et les corrélations explicitement marquées restent des couches séparées.
