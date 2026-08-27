# Intégrité d’un run

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <strong>Français</strong> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 peut sceller un run terminé sous la forme d’un inventaire SHA-256 déterministe, puis vérifier cet inventaire ultérieurement. Cette fonction sert à détecter les corruptions et modifications locales survenues après le scellement. Lorsque le manifest et les evidence restent dans la même trust boundary inscriptible, elle n’est volontairement pas présentée comme une preuve d’intégrité résistante à un attaquant.

## Portée

`execweave-integrity seal` inventorie récursivement tous les regular files du run directory choisi, à l’exception de `integrity.json`. Les entrées sont triées de manière déterministe par relative POSIX path et enregistrent le path, la taille en octets et le digest SHA-256. Les symbolic links sont refusés au lieu d’être suivis ou normalisés silencieusement.

Le seal doit être créé uniquement après la fin de la capture et de tous les derived artifacts souhaités. Un fichier créé après le scellement est signalé comme unsealed ; toute modification, substitution ou suppression d’un sealed file fait échouer la vérification.

## Seal et verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` refuse d’écraser un integrity contract existant. `verify` ne réussit que si le manifest schema est valide, si le manifest body digest correspond, si chaque sealed file possède la taille et le SHA-256 attendus, et si aucun regular file supplémentaire n’est apparu depuis le scellement.

## Manifest contract

| Champ | Signification |
| --- | --- |
| `schema_version` | Version du integrity schema ; v0.6.5 commence à `0.1`. |
| `files` | Inventaire des sealed files dans un ordre déterministe. |
| `manifest_body_sha256` | SHA-256 du canonical manifest content sans ce champ de digest. |
| `trust_model` | Déclaration explicite de ce que le local seal prouve et ne prouve pas. |

Le manifest enregistre obligatoirement `malicious_writer_resistance: false` et `external_trust_anchor: false`. Ces valeurs font partie du schema contract et ne sont pas une simple réserve documentaire facultative.

## Trust boundary

Un local digest est utile pour détecter une accidental corruption, une copie incomplète ou un post-seal change par rapport au moment du scellement. Il n’empêche pas un process capable de réécrire à la fois les run evidence et `integrity.json` : ce process peut recalculer les hashes et produire un nouveau manifest cohérent en interne.

Pour une garantie plus forte, copiez `manifest_body_sha256` ou le manifest complet vers un emplacement hors de la write boundary du observed process, ou protégez/signez la valeur avec une key indisponible à ce process. C’est cette action externe qui crée le trust anchor ; ExecWeave ne prétend pas qu’un manifest dans le même directory en constitue un à lui seul.

## Règles opérationnelles

Ne scellez qu’un run terminé. Vérifiez les archived ou transferred evidence avant de vous y fier. Toute verification error indique que le directory ne correspond plus exactement au sealed inventory ; elle ne prouve pas une activité malveillante. Si de nouveaux artifacts doivent être produits après le seal, créez-les d’abord puis scellez une nouvelle finalized copy au lieu de réécrire silencieusement le manifest original.
