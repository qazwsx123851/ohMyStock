## ADDED Requirements

### Requirement: Proposal Re-validate 按鈕

Proposal 詳情頁 SHALL 在可重驗狀態提供 `[Re-validate]` 按鈕，點擊帶入 localStorage `ohmystock.admin.lastValidation` 的上次參數重開 ValidationDialog。無後端改動（沿用既有 validate endpoint）。

#### Scenario: 帶入上次參數重開驗證

- **WHEN** 使用者在可重驗的提案點擊 Re-validate
- **THEN** ValidationDialog 開啟並預填上次驗證參數

#### Scenario: 無上次參數

- **WHEN** localStorage 無 lastValidation 紀錄
- **THEN** ValidationDialog 開啟並使用預設值
