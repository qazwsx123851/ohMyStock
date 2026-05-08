---
name: phase-2b-scoring
description: Phase 2B 加權打分（SEPA / RS / 法人 / pattern 子分數合成）
category: signal
cited_specs:
  - phase-2b-scoring-engine
  - swarm-input-assembler
---
# Purpose
將 screener 候選的多面向訊號合成單一 0-100 分數，對 LLM Decider 提供「值得 swarm 跑一輪」的初篩。子分數由「scoring registry」的 sub-scorers 註冊；Phase 2B Swarm Input Assembler 負責把分數高的候選打包成 LLM prompt。

# Inputs
- `candidates: list[ScreenerHit]`
- `weights: dict[str, float]`（子分數權重，總和 1.0）

# Outputs
- 排序後 list：`{symbol, total_score, subscores: dict[str, float], reasons: list[str]}`

# See also
- `openspec/specs/phase-2b-scoring-engine/spec.md`
- `openspec/specs/swarm-input-assembler/spec.md`
- 評分閾值 ≥ 65 才送入 entry-decider
