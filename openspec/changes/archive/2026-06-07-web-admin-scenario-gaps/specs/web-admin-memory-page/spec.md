## ADDED Requirements

### Requirement: 寫入個人偏好表單

Memory 頁 SHALL 提供寫入表單（kind / content / tags / source），提交呼叫 memory write endpoint。成功後 MUST 刷新列表使新筆可見。必填欄位（kind、content）未填 MUST 於前端擋下。

#### Scenario: 成功寫入並刷新

- **WHEN** 填妥 kind + content 並提交
- **THEN** 呼叫 write endpoint，成功後列表刷新並可見新筆

#### Scenario: 必填驗證

- **WHEN** content 為空即提交
- **THEN** 前端擋下、不送出
