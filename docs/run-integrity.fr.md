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


## Limites de la vérification purement locale

<!-- ew:trust:local-only -->

Le couple local `seal` / `verify` détecte une corruption accidentelle ou une modification sans nouveau scellement. **Tout acteur pouvant réécrire le run et `integrity.json` peut recalculer les empreintes et resceller des données cohérentes.** `valid: true` atteste uniquement la cohérence locale, sans garantie d'audit inviolable.

<!-- ew:trust:privileged -->

Root, un Agent disposant de sudo et tout processus pouvant écrire dans le dossier de sortie peuvent modifier ensemble les données et le manifeste. Protégez-les par des droits système et l'isolation des processus ; déplacer des fichiers sans changer les droits n'isole rien.

<!-- ew:compat:no-downgrade -->

**Il n'est pas pris en charge de rétrograder le reader v0.8.35+ vers v0.8.34.** L'ancien reader peut supprimer silencieusement `observation_assessment` et fausser le jugement sur l'observation. Seules les conclusions des readers v0.8.35 et ultérieurs sont recevables. Revenir à un ancien recorder ne justifie pas la rétrogradation du reader.

Ne scellez que les runs terminés et vérifiez les archives avant emploi. Un échec indique une incohérence locale, pas nécessairement une attaque. Cet outil ne publie ni données ni empreintes et ne fournit aucune frontière de permissions indépendante.
