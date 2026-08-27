# Run Integrity（実行整合性）

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <a href="run-integrity.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 は、完了した run を deterministic な SHA-256 inventory として seal し、後から同じ inventory を verify できます。この機能の目的は、ローカル環境で seal 後に発生した破損や変更を検出することです。manifest と evidence が同一の書き込み可能な trust boundary にある場合、攻撃者に耐える tamper evidence とは表現しません。

## スコープ

`execweave-integrity seal` は、指定した run directory 配下の regular file を再帰的に列挙します。ただし `integrity.json` 自身は除外します。entry は relative POSIX path で決定的にソートされ、path、byte size、SHA-256 digest を記録します。Symbolic link は追跡や暗黙の正規化を行わず、明示的に拒否します。

seal は capture と必要な derived artifacts がすべて完成した後にのみ実行する想定です。seal 後に追加された file は unsealed として報告され、sealed file の変更、置換、削除はいずれも verification failure になります。

## Seal と verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` は既存の integrity contract を上書きしません。`verify` は manifest schema が正しく、manifest body digest が一致し、すべての sealed file の size と SHA-256 が一致し、seal 後の追加 regular file が存在しない場合にだけ成功します。

## Manifest contract

| フィールド | 意味 |
| --- | --- |
| `schema_version` | Integrity schema の版。v0.6.5 は `0.1` から開始します。 |
| `files` | 決定的な順序の sealed file inventory。 |
| `manifest_body_sha256` | digest field 自身を除いた canonical manifest content の SHA-256。 |
| `trust_model` | local seal が証明する範囲と証明しない範囲を明記します。 |

manifest は `malicious_writer_resistance: false` と `external_trust_anchor: false` を必ず記録します。これは任意の説明文ではなく schema contract の一部です。

## Trust boundary

local digest は accidental corruption、不完全な copy、seal 時点からの post-seal change の検出に有用です。しかし run evidence と `integrity.json` の両方を書き換えられる process を防ぐことはできません。その process は hash を再計算し、内部的に整合する新しい manifest を作成できます。

より強い保証が必要な場合は、`manifest_body_sha256` または manifest 全体を observed process の書き込み境界外へコピーするか、その process が利用できない key で保護または署名してください。trust anchor はその外部操作によって成立します。ExecWeave は同一 directory 内の manifest だけで trust anchor が成立するとは主張しません。

## 運用ルール

完了した run だけを seal してください。archive または transfer された evidence を利用する前に verify してください。verification error は directory が sealed inventory と完全一致しなくなったことを示すだけで、悪意ある行為そのものを証明しません。seal 後に新しい artifact が必要な場合は、それらを先に生成し、finalized copy を新たに seal してください。元の manifest を黙って書き換えてはいけません。
