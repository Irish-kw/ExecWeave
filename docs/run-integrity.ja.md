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


## ローカル整合性検証の限界

<!-- ew:trust:local-only -->

ローカルの `seal` / `verify` は偶発的な破損や、再 seal を伴わない変更を検知します。**記録と `integrity.json` を書き換えられる主体は、ハッシュを再計算して整合する記録を再 seal できます。** `valid: true` が示すのはローカルの整合性のみで、改ざん耐性の監査ではありません。

<!-- ew:trust:privileged -->

root、sudo 権限を持つ Agent、または出力ディレクトリに書き込めるプロセスは、記録と manifest の両方を変更できます。OS 権限とプロセス分離で保護してください。同じ権限のまま保存先だけ変えても分離にはなりません。

<!-- ew:compat:no-downgrade -->

**v0.8.35 以降の記録を v0.8.34 reader で開くダウングレードには対応しません。** 古い reader は `observation_assessment` を警告なく破棄し、観測の完全性を誤表示する場合があります。結論には v0.8.35 以降の reader を使用してください。recorder のロールバックは reader のロールバックを意味しません。

完了した run のみ seal し、保存済みの証拠を使う前に verify してください。検証失敗はローカル不整合を示しますが、悪意の証明ではありません。本ツールは記録やダイジェストを送信せず、独立した権限境界も提供しません。
