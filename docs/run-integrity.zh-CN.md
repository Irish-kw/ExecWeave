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


## 仅限本地的一致性与信任边界

<!-- ew:trust:local-only -->

本地 `seal` / `verify` 可以检测意外损坏和未重新封存的修改。**具有写入权限的进程可以同时重写执行记录和 `integrity.json`，重新计算哈希后再次 seal。** `valid: true` 只表示本地一致性，并不意味着具有防篡改审计能力。

<!-- ew:trust:privileged -->

具有 root、sudo 权限的 Agent，或任何可以写入输出目录的进程，都可能修改事件和 manifest。应使用操作系统权限和进程隔离保护数据；仅改变路径而保留同样权限并不构成隔离。

<!-- ew:compat:no-downgrade -->

**不支持使用 v0.8.34 reader 降级读取 v0.8.35 及更新版本的记录。** 旧版本可能在没有警告的情况下丢弃 `observation_assessment`，错误呈现观测完整性。只有 v0.8.35 及以上 reader 得出的结论才可信。回滚 recorder 并不意味着可以回滚 reader。

只对已完成的 run 进行 seal，使用归档证据前先 verify。检查失败代表本地内容不一致，但不能单独证明恶意行为。工具不会上传执行内容或摘要，也不提供独立的权限边界。
