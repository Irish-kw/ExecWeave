<!-- i18n-nav:start -->
<p align="center">
  <a href="codex-hooks.md">English</a> |
  <a href="codex-hooks.zh-TW.md">繁體中文</a> |
  <a href="codex-hooks.zh-CN.md">简体中文</a> |
  <a href="codex-hooks.ja.md">日本語</a> |
  <a href="codex-hooks.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="codex-hooks.de.md">Deutsch</a> |
  <a href="codex-hooks.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Hooks de cycle de vie OpenAI Codex

ExecWeave enregistre les preuves issues des hooks de cycle de vie Codex à côté d'une télémétrie d'exécution OS indépendante. Les hooks fournisseur décrivent l'activité logique Agent/outil ; ils ne fournissent pas le PID enfant OS nécessaire pour affirmer une causalité directe Tool → Process.

## Surface de hooks actuelle

`execweave-codex-hook --print-config` enregistre actuellement :

- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `PreCompact`
- `PostCompact`
- `SessionStart`
- `SessionEnd`
- `UserPromptSubmit`
- `SubagentStart`
- `SubagentStop`
- `Stop`

ExecWeave n'invente pas les événements absents ou indisponibles côté fournisseur. Les schémas et la couverture peuvent changer selon les versions de Codex.

Configurez le hook puis enregistrez un run :

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

Le recorder lie un sidecar sémantique spécifique au run et conserve séparément les artefacts runtime, semantic et correlated.

## Contenu full-fidelity

v0.6.5 stocke les valeurs complètes effectivement fournies par le hook Codex dans un store local adressé par contenu. Le sidecar JSONL contient des références plutôt que de grandes copies inline.

Le contenu observé peut inclure le `UserPromptSubmit.prompt` complet, le `tool_input` complet, le `PostToolUse.tool_response` complet, l'entrée outil d'une demande d'autorisation et les messages finaux assistant/subagent lorsque ces champs sont fournis. Les valeurs applicatives présentes dans ces payloads sont conservées ; ne supposez pas qu'elles ont été expurgées.

Les identifiants de transport reconnus sont exclus de la projection séparée de métadonnées lorsque l'adaptateur les reconnaît. Ce filtrage ne réécrit ni ne nettoie le contenu lui-même.

`content_complete_from_source: true` signifie que la valeur complète fournie au point d'intégration Codex a été stockée. Cela ne signifie pas qu'ExecWeave a lu un transcript absent du hook, intercepté une requête fournisseur invisible ou observé un état caché du modèle.

## Identité des outils et corrélation

Lorsque Codex fournit `tool_use_id`, ExecWeave l'utilise comme identité logique d'appel outil. Les commandes déclarées restent des preuves sémantiques fournisseur. Le hook ne fournit toujours pas le PID enfant OS ; un pont Tool → Process n'est donc émis par la corrélation conservatrice que lorsqu'une seule candidature runtime est soutenue de manière unique.

```text
inferred: true
causal: false
```

Les commandes ambiguës, non appariées, shell builtin, composées ou non prises en charge ne produisent aucun pont. Une ressemblance temporelle ou textuelle ne suffit jamais à transformer une preuve fournisseur en attribution OS.

## Confidentialité et frontière des preuves

Les artefacts Codex semantic/content peuvent contenir prompts, commandes, arguments/résultats d'outils, réponses finales, chemins, identifiants et valeurs applicatives sensibles. Traitez le répertoire du run comme sensible et examinez-le avant partage.

L'adaptateur ne prétend pas que tous les modes d'exécution Codex offrent une couverture lifecycle complète. Des hooks manquants réduisent la visibilité sémantique sans désactiver le collecteur OS indépendant. Un hook fournisseur ne prouve pas non plus qu'une commande déclarée a été exécutée, qu'une action fichier s'est produite ou que des octets ont circulé entre ressources.
