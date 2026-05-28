# workflow — 個人專案協作工作流

## 核心原則

- **避免過度工程**：不要建議 CI lint、自動 schema sync 測試、跨團隊 owner table、合規部門角色分離。這是 solo dev 個人專案，不是企業 SaaS。
- **拆檔動機**：主要是「LLM 讀單檔太貴 / 自己找東西要快」，**不是**「合規分權」。
- **單一權威 (SSOT)**：個人專案最怕「自己改一處忘另一處」，公式 / schema 重複是首要問題。改公式請只改 `ssot-pointers.md` 表中「唯一權威」一欄。
- **不為 hypothetical 團隊規模設計**：目錄、流程、角色分離保持精簡。

## Git

- **直接 push main**：solo dev 不開 PR，commit 完直接 `git push origin main`。
- **不要建 feature branch**。
- **不要開 PR**。

## OpenSpec 流程

- 每個新 capability 開一個 `openspec/changes/<slug>/`（含 `proposal.md` + `design.md` + `tasks.md` + `specs/`）。
- 完工後 `/opsx:archive` 搬到 `openspec/changes/archive/`，這是 capability 級別的歷史紀錄。
- 對應的 spec delta 同步到 `openspec/specs/<capability>/spec.md`。
- 完成後要在 `capability-map.md` 加一列指向新的 archive 路徑。

## 跑月度復盤

```
uv run ohmystock review --from <YYYY-MM-DD> --to <YYYY-MM-DD>
```

先試 `--dry-run --json` 估 token / cost。
