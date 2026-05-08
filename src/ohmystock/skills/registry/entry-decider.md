---
name: entry-decider
description: LLM 進場決策節點（PM 角色，Opus 4.7，輸出結構化 JSON）
category: decider
cited_specs:
  - entry-decider
  - confirm-gate
---
# Purpose
作為 entry decision swarm 的最終 PM 節點：接收 Phase 2B 候選 + sub-scorer 證據 + Trend Template 結果，輸出 `{action, confidence, thesis, sizing, citations}` 結構化 JSON。永不直接下單 — 結果寫入 Confirm Gate `pending_confirm` 等人類同意（或 Phase 3.5 auto-execute breaker 驗證）。

# Inputs
- `candidate_pack: dict`（symbol、bars、indicators、chip、RS、SEPA stage / template、scores）
- `model: "claude-opus-4-7"`（預設）/ `"fake://..."`（測試）

# Outputs
- `DecisionResult{action: "enter" | "reduce_size" | "skip", confidence: 0..1, thesis: str, sizing_hint_pct: float, cited_skills: list[str]}`
- 系統覆寫層會驗證 §2.1 違規欄位並可降權重

# See also
- `openspec/specs/entry-decider/spec.md`
- `openspec/specs/confirm-gate/spec.md`
- `docs/llm-decision-schema.md` §2.1
