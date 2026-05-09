## ADDED Requirements

### Requirement: `SkillSpec` model 與 frozen 不變式
系統 SHALL 在 `src/ohmystock/skills/spec.py` 定義 `SkillSpec`（pydantic `BaseModel`，`model_config = ConfigDict(frozen=True, extra="forbid")`），欄位恰為：

- `name: str` — kebab-case, 與檔名 stem 完全相同
- `description: str` — 一行說明（≤ 160 chars 後續可加 validator；本版本不強制）
- `category: Literal["data", "indicator", "signal", "decider", "gate", "tool", "report"]`
- `body: str` — Markdown body（不含 frontmatter，原樣保留換行）
- `cited_specs: list[str]` — 所引用的 deployed spec capability names（kebab-case）；可空 list `[]` 但 SHALL 存在

`SkillSpec` SHALL NOT 暴露 `enabled`、`last_run_at`、`yaml_frontmatter_raw` 等欄位（皆為意圖性 deferred）。

#### Scenario: frozen 不變式
- **GIVEN** 一個合法 `SkillSpec(name="market-data", category="data", description="…", body="…", cited_specs=[])`
- **WHEN** 嘗試 `s.name = "x"`
- **THEN** SHALL 拋 pydantic ValidationError（frozen attempt）

#### Scenario: 缺少必要欄位
- **WHEN** `SkillSpec(name="x")` 被呼叫但缺其他必要欄位
- **THEN** SHALL 拋 pydantic ValidationError，error message 包含缺失欄位名

#### Scenario: 不允許 unknown 欄位
- **WHEN** `SkillSpec(name="x", description="y", category="data", body="z", cited_specs=[], extra="boom")` 被呼叫
- **THEN** SHALL 拋 ValidationError，message 提示 `extra` 不被允許（pydantic `extra="forbid"`）

---

### Requirement: 公開 API（`__init__.py`）
`src/ohmystock/skills/__init__.py` SHALL 公開且僅公開以下名稱：`SkillSpec`、`load_skills`、`load_skill`、`SkillLoadError`。從別處 `from ohmystock.skills import …` 只能匯入這四個名稱；其他模組內部實作（私有 helper、enum 實體等）SHALL NOT 出現在 `__init__.py` 的 `__all__` 或 re-export 列表內。

#### Scenario: 公開符號
- **WHEN** `import ohmystock.skills as s`
- **THEN** `s.SkillSpec`、`s.load_skills`、`s.load_skill`、`s.SkillLoadError` SHALL 皆存在
- **AND** `s.__all__` SHALL 等於 `["SkillSpec", "load_skills", "load_skill", "SkillLoadError"]`（順序不限）

---

### Requirement: 檔案格式 — YAML frontmatter + Markdown body
每個 skill 檔案 SHALL 為 `<skills_dir>/<name>.md`，第一行 SHALL 為 `---`，第二段（直到下一個獨立 `---` 行）為 YAML frontmatter，剩餘為 Markdown body。Frontmatter SHALL 含且僅含 `name`、`description`、`category`、`cited_specs` 四個 key（順序不限）。Body SHALL 從第二個 `---` 之後一行開始；若 body 為空，loader 接受空字串。

#### Scenario: 標準格式
- **GIVEN** 檔案 `market-data.md` 內容為：
  ```
  ---
  name: market-data
  description: 取得 daily bars 與 quote
  category: data
  cited_specs: [market-data-cache, screener-tw-universe]
  ---
  # Purpose
  ...
  ```
- **WHEN** `load_skill(dir, "market-data")` 被呼叫
- **THEN** 回傳 `SkillSpec(name="market-data", category="data", cited_specs=["market-data-cache", "screener-tw-universe"], …)`
- **AND** `body` SHALL 開頭為 `"# Purpose\n..."`（含後續空行）

#### Scenario: 缺 frontmatter delimiter
- **GIVEN** 檔案開頭不是 `---`
- **WHEN** `load_skill` 被呼叫
- **THEN** SHALL 拋 `SkillLoadError`，message 包含 `"missing frontmatter"` 與檔案路徑

#### Scenario: Body 為空
- **GIVEN** 檔案內 frontmatter 後立刻 EOF（無 body）
- **WHEN** `load_skill` 被呼叫
- **THEN** SHALL 成功回傳 `SkillSpec`，`body == ""`

---

### Requirement: `load_skills` 列表載入
`load_skills(skills_dir: Path) -> list[SkillSpec]` SHALL 掃描 `skills_dir` 內所有 `*.md` 檔案，逐一解析，回傳穩定排序（依 `name` 升序）的 `list[SkillSpec]`。SHALL 跳過：

- 檔名以 `_` 開頭的檔案（例如 `_template.md`）
- 子目錄（不遞迴）
- 非 `.md` 副檔名

任一檔案 parse 失敗 SHALL 立刻拋 `SkillLoadError`（fail-fast，不收集多個錯誤、不回部分結果）。

#### Scenario: 空目錄
- **GIVEN** `skills_dir` 內無任何 `.md` 檔
- **WHEN** `load_skills(skills_dir)` 被呼叫
- **THEN** SHALL 回傳空 list `[]`
- **AND** SHALL NOT 拋例外

#### Scenario: 跳過 `_*.md`
- **GIVEN** `skills_dir` 內有 `market-data.md`（合法）+ `_template.md`（合法格式但底線開頭）
- **WHEN** `load_skills` 被呼叫
- **THEN** 回傳 list 長度 SHALL 為 1
- **AND** 該唯一 element 的 `name` SHALL 為 `"market-data"`

#### Scenario: 排序穩定
- **GIVEN** `skills_dir` 內有 `zebra.md`、`apple.md`、`mango.md`（皆合法）
- **WHEN** `load_skills` 被呼叫
- **THEN** 回傳 list `[name]` 順序 SHALL 為 `["apple", "mango", "zebra"]`

#### Scenario: 一個檔案壞掉就整批失敗
- **GIVEN** `skills_dir` 內有 `good.md`（合法）+ `bad.md`（YAML 語法錯）
- **WHEN** `load_skills` 被呼叫
- **THEN** SHALL 拋 `SkillLoadError`
- **AND** message SHALL 包含 `"bad.md"` 路徑（非 `"good.md"`）

---

### Requirement: `load_skill` 單檔查詢
`load_skill(skills_dir: Path, name: str) -> SkillSpec | None` SHALL 嘗試讀取 `skills_dir / f"{name}.md"`：

- 若檔案不存在 SHALL 回傳 `None`（非例外）
- 若檔案存在但 parse 失敗 SHALL 拋 `SkillLoadError`
- 若檔案存在且合法 SHALL 回傳對應 `SkillSpec`

`name` 參數 SHALL NOT 經 path-normalisation；含 `/`、`\`、`..` 或 path separator 的 `name` SHALL 拋 `SkillLoadError("invalid skill name")` 而不是嘗試讀檔（防止 path traversal）。

#### Scenario: 不存在
- **GIVEN** `skills_dir` 內無 `does-not-exist.md`
- **WHEN** `load_skill(skills_dir, "does-not-exist")` 被呼叫
- **THEN** SHALL 回傳 `None`

#### Scenario: 路徑遊歷防禦
- **WHEN** `load_skill(skills_dir, "../../../etc/passwd")` 被呼叫
- **THEN** SHALL 拋 `SkillLoadError`，message 包含 `"invalid skill name"`
- **AND** SHALL NOT 嘗試開啟任何 `skills_dir` 範圍外的檔案

#### Scenario: 合法名稱含連字號
- **GIVEN** `sepa-trend-template.md` 為合法 skill 檔
- **WHEN** `load_skill(skills_dir, "sepa-trend-template")` 被呼叫
- **THEN** SHALL 回傳對應 `SkillSpec`

---

### Requirement: name = filename stem 不變式
loader SHALL 強制 `frontmatter.name == path.stem`。不一致 SHALL 拋 `SkillLoadError`，message 同時包含檔名與 frontmatter 內 name。

#### Scenario: name 不匹配
- **GIVEN** 檔案 `market-data.md` 但 frontmatter `name: foo-bar`
- **WHEN** `load_skill(skills_dir, "market-data")` 被呼叫
- **THEN** SHALL 拋 `SkillLoadError`
- **AND** message SHALL 同時提到 `"market-data"` 與 `"foo-bar"`

---

### Requirement: category enum 強制
loader SHALL 拒絕 `category` 不在 `{"data", "indicator", "signal", "decider", "gate", "tool", "report"}` 集合內的檔案，拋 `SkillLoadError`，message 同時包含實際值與允許值列表。

#### Scenario: 拼寫錯誤的 category
- **GIVEN** `market-data.md` frontmatter 寫 `category: indicators`（複數，非 enum）
- **WHEN** loader 解析
- **THEN** SHALL 拋 `SkillLoadError`
- **AND** message SHALL 包含 `"indicators"` 與 `"indicator"`（提示正確值）

---

### Requirement: 種子 skill corpus（`registry/`）
`src/ohmystock/skills/registry/` SHALL 包含至少 10 個合法 `.md` 檔，每檔 frontmatter `cited_specs` SHALL 至少有 1 筆。涵蓋以下 10 個 name + category 對應：

| name | category | 主要 cited spec |
|---|---|---|
| `market-data` | `data` | `market-data-cache` |
| `chip-data` | `data` | `chip-data-skill` |
| `technical-indicators` | `indicator` | `technical-indicators` |
| `rs-percentile` | `indicator` | `rs-percentile` |
| `sepa-stage` | `signal` | `sepa-stage-classification` |
| `sepa-trend-template` | `signal` | `sepa-trend-template` |
| `screener` | `signal` | `screener-tw-universe` |
| `phase-2b-scoring` | `signal` | `phase-2b-scoring-engine` |
| `entry-decider` | `decider` | `entry-decider` |
| `exit-engine` | `gate` | `exit-engine` |

每個 body SHALL 含 `# Purpose`、`# Inputs`、`# Outputs`、`# See also` 四個 H1 區塊。

#### Scenario: 種子載入無錯
- **WHEN** `load_skills(Path("src/ohmystock/skills/registry"))` 被呼叫
- **THEN** 回傳 list 長度 SHALL ≥ 10
- **AND** SHALL NOT 拋例外

#### Scenario: 種子 name 唯一
- **WHEN** `load_skills(...)` 對 registry 目錄回傳 list
- **THEN** `[s.name for s in result]` SHALL 無重複
