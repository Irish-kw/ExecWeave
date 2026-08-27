<!-- i18n-nav:start -->
<p align="center">
  <a href="runtime-threat-model.md">English</a> |
  <a href="runtime-threat-model.zh-TW.md">繁體中文</a> |
  <a href="runtime-threat-model.zh-CN.md">简体中文</a> |
  <a href="runtime-threat-model.ja.md">日本語</a> |
  <a href="runtime-threat-model.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="runtime-threat-model.de.md">Deutsch</a> |
  <a href="runtime-threat-model.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Modèle de menace Runtime et limites d'évasion connues

Ce document définit les limites d'observation qu'ExecWeave v0.6.5 considère comme faisant partie de son contrat testable. Il s'agit d'un **modèle de menace d'observabilité**, et non d'une garantie de sandbox : la commande observée peut être non fiable et tenter de rendre son activité difficile à observer, tandis que le noyau du système et l'installation d'ExecWeave sont supposés ne pas être compromis au niveau kernel.

## Portable backend

Le portable backend utilise des snapshots psutil pour les activités process/network et watchdog pour les changements filesystem.

- **Process de courte durée :** un child qui démarre et se termine entièrement entre deux process samples peut être manqué. Le poll interval configuré n'est pas une borne maximale garantie du blind window, car le scheduler peut allonger l'intervalle réel.
- **Sockets de courte durée :** une connexion créée puis disparue entre deux socket observations peut être manquée. Les permissions ou les limites des API de la plateforme peuvent aussi masquer le socket state.
- **Descendants survivant au root command :** si un child est encore vivant lorsque la root observation se termine, ExecWeave n'invente pas d'exit event. Toutefois, un portable run n'est pas un always-on monitor ; l'activité ultérieure d'un descendant survivant ou reparented est hors de la fenêtre d'observation du run terminé.
- **Filesystem attribution :** les changements watchdog sont des observations session-correlated, volontairement `causal=false`. Ils ne prouvent pas qu'un PID particulier a effectué l'écriture.
- **Negative evidence :** l'absence d'un process/network/filesystem event portable ne prouve pas que l'activité n'a pas eu lieu.

## Linux strace backend

Le strace backend suit la lineage de la commande tracée avec `strace -ff` et un ensemble sélectionné de syscall classes.

- Dans cette traced lineage, les preuves clone/fork peuvent conserver des descendants de courte durée que le portable polling pourrait manquer.
- Lorsqu'une preuve syscall prise en charge existe, les filesystem/network events peuvent être attribués au traced process.
- Il ne s'agit **pas d'une visibilité OS-wide**. Les activités hors de la traced lineage, les syscall patterns non pris en charge ou non analysés, les restrictions permission/ptrace et le kernel behavior hors des evidence classes sélectionnées sont hors de la portée revendiquée.
- Le read/write access mode d'un open n'établit pas un byte-level data flow. ExecWeave ne prétend pas connaître les octets effectivement lus ou écrits ensuite.

## Specialized hooks et direct API integrations

Claude, Codex, Gemini, Cursor, OpenCode, model-runtime, gateway, proxy et les direct-API integrations peuvent fournir une semantic content evidence plus forte à leurs integration points explicites, mais ne révèlent pas le provider-hidden state.

- Une response-only integration ne prouve que les response fields fournis à ExecWeave.
- Un caller-supplied request+response exchange ne prouve que l'exchange fourni et n'affirme pas une transparent wire interception.
- La hook coverage est limitée à ce que l'agent ou l'IDE upstream expose réellement au hook.
- Full-fidelity storage signifie la conservation complète du contenu exposé à l'integration point, pas une visibilité complète sur le model provider ou le système d'exploitation.

## Regression contract

`tests/test_threat_model.py` rend les limites suivantes exécutables et déterministes :

1. un portable child présent uniquement entre deux process samples ;
2. un portable socket présent uniquement entre deux socket samples ;
3. un child toujours vivant à la fin de la root-process observation, sans inventer un exit event ;
4. les portable filesystem changes restent session-correlated et non-causal ;
5. le cas strace correspondant conserve l'attribution `SPAWNED` d'un child de courte durée.

Les tests évitent volontairement les timing races du type « sleep N ms et espérer que CI le manque ». Le blind window est modélisé comme un état explicite entre observations afin que le contrat soit reproductible sous Linux, macOS et Windows.

## Signification d'un missing event

Un missing event signifie uniquement que la canonical evidence du run ne contient pas cette observation. Il ne constitue pas une preuve de non-occurrence tant qu'un futur backend n'a pas explicitement défini et démontré un negative-evidence scope complet. Finding severity et evidence fidelity restent deux dimensions indépendantes.
