# OpenCode Plugin

<!-- i18n-nav:start -->
<p align="center">
  <a href="opencode-plugin.md">English</a> |
  <a href="opencode-plugin.zh-TW.md">繁體中文</a> |
  <a href="opencode-plugin.zh-CN.md">简体中文</a> |
  <a href="opencode-plugin.ja.md">日本語</a> |
  <a href="opencode-plugin.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="opencode-plugin.de.md">Deutsch</a> |
  <a href="opencode-plugin.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave s'intègre à OpenCode via un plugin local au projet. OpenCode expose des valeurs exactes `sessionID + callID` sur les hooks tool before/after, ce qui permet d'identifier un appel logique sans appariement heuristique. Cette identité reste une preuve fournisseur et n'est pas un PID OS.

## Installation et enregistrement

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Le plugin généré est installé dans `.opencode/plugins/execweave.ts`. ExecWeave refuse d'écraser un plugin existant sauf si `--force` est explicitement fourni.

## Surface d'observation complète

v0.6.5 n'est plus limité à l'ancien contrat minimal-metadata de trois événements. Le chemin plugin/hook peut préserver le contenu exposé par OpenCode via les messages de chat, l'exécution d'outils avant/après, les transformations model-context/system, le texte assistant terminé, les événements provider bus, les headers de requête après filtrage des credentials, les définitions d'outils, les commandes, demandes d'autorisation et contexte de compaction lorsque ces hooks sont déclenchés.

Les relations logiques typiques restent Agent → tool call, tool call → tool, commande/cible déclarée et observations de résultat. Le stockage du contenu ne change pas leur sémantique de preuve.

## Contenu full-fidelity

Les valeurs complètes fournies par le plugin OpenCode sont stockées dans le store local adressé par contenu et référencées depuis le sidecar sémantique JSONL. Les régressions couvrent messages/parts complets, args/résultats d'outils, contexte modèle, prompts système, texte assistant, événements fournisseur, définitions d'outils, arguments/parts de commande, données de permission et prompts/contexte de compaction.

Les credentials de transport connus comme authorization/cookie sont filtrés des headers/projections provider-metadata concernés. Les valeurs applicatives sensibles intégrées aux args, messages, résultats ou autres contenus sont conservées. Ne supposez pas que le full-fidelity a été expurgé.

## Corrélation Tool vers Process

`sessionID + callID` prouve l'identité logique exacte d'un appel dans OpenCode. Il ne prouve pas quel processus OS l'a exécuté. Tool → Process reste un pont dérivé séparé et conservateur, émis uniquement lorsqu'une preuve runtime indépendante soutient un seul processus.

```text
inferred: true
causal: false
```

Les appels ambigus ou non pris en charge ne produisent aucun pont.

## Confidentialité et frontière des preuves

Les preuves d'un run OpenCode peuvent contenir prompts/messages, données system/context, arguments/sorties d'outils, commandes, motifs de permission, contenu d'événements fournisseur, chemins, identifiants et valeurs applicatives sensibles. Examinez le répertoire avant partage.

Le plugin prouve ce qu'OpenCode a exposé au niveau semantic/provider. Les collecteurs runtime établissent indépendamment les observations process/file/network. Le contenu full-fidelity fournisseur ne prouve pas à lui seul l'exécution d'une commande, un accès fichier terminé ou un flux de données au niveau des octets.
