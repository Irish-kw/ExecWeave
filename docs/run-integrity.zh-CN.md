# Run Integrity（运行完整性）

<!-- i18n-nav:start -->
<p align="center">
  <a href="run-integrity.md">English</a> |
  <a href="run-integrity.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="run-integrity.ja.md">日本語</a> |
  <a href="run-integrity.ko.md">한국어</a> |
  <a href="run-integrity.fr.md">Français</a> |
  <a href="run-integrity.de.md">Deutsch</a> |
  <a href="run-integrity.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

ExecWeave v0.6.5 可以把已完成的 run 封存为 deterministic SHA-256 inventory，并在之后重新验证。此功能用于检测本地封存后的损坏与修改。当 manifest 与 evidence 仍处于同一个可写 trust boundary 内时，我们明确不把它描述为能够抵抗攻击者的 tamper evidence。

## 范围

`execweave-integrity seal` 会递归盘点指定 run directory 下的所有 regular file，但排除 `integrity.json` 本身。条目按 relative POSIX path 确定性排序，并记录 path、byte size 与 SHA-256 digest。Symbolic link 会被拒绝，而不是被跟随或静默规范化。

seal 应只在 capture 和所有需要的 derived artifacts 全部完成后执行。seal 之后新建的文件会被报告为 unsealed；任何 sealed file 如果被修改、替换或删除，验证都会失败。

## Seal 与 verify

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

`seal` 不会覆盖已经存在的 integrity contract。只有 manifest schema 合法、manifest body digest 一致、每个 sealed file 的 size 与 SHA-256 均匹配，并且 seal 后没有出现额外 regular file 时，`verify` 才返回成功。

## Manifest contract

| 字段 | 含义 |
| --- | --- |
| `schema_version` | Integrity schema 版本；v0.6.5 从 `0.1` 开始。 |
| `files` | 以确定顺序保存的 sealed file inventory。 |
| `manifest_body_sha256` | 排除本 digest 字段后 canonical manifest content 的 SHA-256。 |
| `trust_model` | 明确说明此 local seal 能证明和不能证明的内容。 |

manifest 固定记录 `malicious_writer_resistance: false` 和 `external_trust_anchor: false`。这些字段属于 schema contract，而不是可选的文档措辞。

## Trust boundary

local digest 可用于检测 accidental corruption、不完整复制，或相对于 seal 时刻发生的 post-seal changes。但它无法阻止一个同时可以改写 run evidence 与 `integrity.json` 的 process；该 process 可以重新计算 hashes，并构造新的、内部一致的 manifest。

如需更强保证，请把 `manifest_body_sha256` 或完整 manifest 复制到 observed process 无法写入的位置，或使用该 process 无法访问的 key 对其进行保护或签名。真正的 trust anchor 来自这个外部动作；ExecWeave 不声称同目录 manifest 本身能够建立 trust anchor。

## 操作规则

只对已完成的 run 执行 seal。在依赖 archived 或 transferred evidence 前先 verify。任何 verification error 只表示目录已不再精确匹配 sealed inventory，并不等于已经证明存在恶意行为。如果 seal 后仍需生成新的 artifact，应先生成这些 artifact，然后对新的 finalized copy 执行 seal，而不是静默重写原 manifest。
