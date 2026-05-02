# Safety & Simulation — Live/Sim 防線、verify_simulation、Shioaji 限制、對賬

> 本檔從 `design-zh-TW.md` §4.5 拆出（2026-04-26 docs reorg）。
> 對應程式：`src/ohmystock/paper/`、`src/ohmystock/tools/verify_simulation.py`
> SSOT：本檔為 **「Live/Sim 防線設計 + verify_simulation 規格 + Shioaji SDK 限制」** 的唯一權威。

---

## 1. ⚠️ 防誤打真實金錢交易的多層防線（Live Trading Prevention）

> **核心風險**（已從 [Shioaji 官方文件](https://sinotrade.github.io/) 確認）：
> 1. Shioaji 切換 simulation / live **只靠一個布林旗標** `sj.Shioaji(simulation=True)`
> 2. **同一組 `api_key` / `secret_key` 可同時用於兩種模式**（沒有獨立 sandbox token）
> 3. 申請 token 時可選「是否可用於 production」與權限範圍（Market / Account / Trading）
>
> → 一行程式碼 typo（`simulation=False`、漏設、env 沒讀到）就會把模擬下單變成真實扣款。**必須以 defense-in-depth 多層保護。**

---

## 2. 防線 1–9 完整說明

### 2.1 防線 1 — Token 帳號物理隔離（最強，源頭擋）

申請**兩組 Shioaji API token**（個人服務網站可建多組）：

| Token | 名稱 | 權限 | IP 白名單 | 用途 |
|---|---|---|---|---|
| **Token A：sim-only** | `ohmystock-sim` | ☑ Market、☑ Account、**☐ Trading 不勾** | 開發機 / CI 公網 IP | 給 dev / Phase 0-4 用 |
| **Token B：live** | `ohmystock-live` | ☑ Market、☑ Account、☑ Trading | **僅 production 主機 IP** | 僅 Phase 5+ 上線後使用 |

→ 即便程式 bug 用 Token A 打 live 模式，**Shioaji 後端會直接拒絕 trading 動作**（IP 不符 + 無 Trading 權限）。這是最強的防線，不依賴程式正確性。

### 2.2 防線 2 — 環境變數雙重旗標 + 強制檢查

```python
# src/ohmystock/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr, model_validator

class Settings(BaseSettings):
    # Broker 模式三選一，無預設（強制使用者明確指定）
    OHMYSTOCK_BROKER: Literal["mock", "shioaji-sim", "shioaji-live"] = Field(...)

    # Shioaji 憑證（兩組分開）
    SHIOAJI_SIM_API_KEY: SecretStr | None = None
    SHIOAJI_SIM_SECRET_KEY: SecretStr | None = None
    SHIOAJI_LIVE_API_KEY: SecretStr | None = None
    SHIOAJI_LIVE_SECRET_KEY: SecretStr | None = None

    # 切到 live 必須的「人類可讀」二次旗標 — 不可由 .env 預設
    OHMYSTOCK_LIVE_CONFIRMED: str | None = None  # 必須 = "I_UNDERSTAND_REAL_MONEY"

    @model_validator(mode="after")
    def enforce_live_safety(self):
        if self.OHMYSTOCK_BROKER == "shioaji-live":
            if self.OHMYSTOCK_LIVE_CONFIRMED != "I_UNDERSTAND_REAL_MONEY":
                raise RuntimeError(
                    "🛑 拒絕啟動：OHMYSTOCK_BROKER=shioaji-live 但未設定 "
                    "OHMYSTOCK_LIVE_CONFIRMED='I_UNDERSTAND_REAL_MONEY'"
                )
            if not (self.SHIOAJI_LIVE_API_KEY and self.SHIOAJI_LIVE_SECRET_KEY):
                raise RuntimeError("🛑 Live 模式但未提供 LIVE 憑證")
            # Live 必須有 CA 設定
            if not self.CA_PFX_PATH:
                raise RuntimeError("🛑 Live 模式必須有 CA 憑證")
        elif self.OHMYSTOCK_BROKER == "shioaji-sim":
            # Sim 模式禁止讀到 live key（防止意外）
            if self.SHIOAJI_LIVE_API_KEY or self.SHIOAJI_LIVE_SECRET_KEY:
                raise RuntimeError("🛑 Sim 模式禁止同時設定 LIVE 憑證（避免誤用）")
        return self
```

### 2.3 防線 3 — Broker 工廠強制驗證

```python
# src/ohmystock/paper/factory.py
def make_broker(settings: Settings) -> BrokerAdapter:
    match settings.OHMYSTOCK_BROKER:
        case "mock":
            return MockBroker()
        case "shioaji-sim":
            broker = ShioajiBroker(simulation=True)
            broker._api_key = settings.SHIOAJI_SIM_API_KEY      # 只給 sim key
            broker._secret_key = settings.SHIOAJI_SIM_SECRET_KEY
            return broker
        case "shioaji-live":
            # 額外人工二次同步確認（CLI 啟動會跳）
            if not _human_confirm_live_via_terminal():
                raise RuntimeError("🛑 Live 啟動使用者拒絕")
            broker = ShioajiBroker(simulation=False)
            broker._api_key = settings.SHIOAJI_LIVE_API_KEY
            broker._secret_key = settings.SHIOAJI_LIVE_SECRET_KEY
            return broker
```

### 2.4 防線 4 — `place_order` 前的最後 assert（每筆下單都檢查）

```python
# src/ohmystock/paper/shioaji_broker.py
class ShioajiBroker(BrokerAdapter):
    def __init__(self, simulation: bool):
        self._simulation = simulation       # 不可變
        self._api = sj.Shioaji(simulation=simulation)
        # 構造後立即驗證實際 SDK 狀態
        assert self._api.simulation == simulation, "Shioaji simulation 狀態異常"

    async def place_order(self, ..., requested_mode: str) -> Trade:
        # 第一道：requested_mode 由 caller 顯式傳入，必須與本實例一致
        expected = "live" if not self._simulation else "sim"
        if requested_mode != expected:
            raise RuntimeError(
                f"🛑 Mode mismatch: caller 要求 {requested_mode}, broker 是 {expected}"
            )

        # 第二道：Live 模式每筆下單再次檢查環境旗標
        if not self._simulation:
            if os.environ.get("OHMYSTOCK_LIVE_CONFIRMED") != "I_UNDERSTAND_REAL_MONEY":
                raise RuntimeError("🛑 Live 旗標被刪除，拒絕下單")

        # 第三道：寫入 audit log（含 mode），失敗即終止
        await audit.log_pre_order(symbol=..., qty=..., mode=expected)
        # ... 真實 place_order
```

### 2.5 防線 5 — 啟動 banner（視覺強提醒）

CLI / Web 啟動時必印（不可關）：

```
╔══════════════════════════════════════════════════════════╗
║  ohMyStock 啟動                                      ║
║  Broker 模式：🟢 SHIOAJI-SIM（模擬交易，不會動到真錢）    ║
║  資料源：FinMind + Shioaji production feed                ║
║  時間：2026-04-26 14:30:00                                ║
╚══════════════════════════════════════════════════════════╝
```

Live 模式則改為紅色：

```
╔══════════════════════════════════════════════════════════╗
║  ⚠️⚠️⚠️  WARNING: LIVE TRADING MODE  ⚠️⚠️⚠️            ║
║  Broker 模式：🔴 SHIOAJI-LIVE（真實金錢交易）             ║
║  OHMYSTOCK_LIVE_CONFIRMED=I_UNDERSTAND_REAL_MONEY            ║
║  按 Ctrl+C 在 10 秒內可中止...                            ║
╚══════════════════════════════════════════════════════════╝
```

Web UI top bar 同步：sim 顯示綠色「模擬」chip；live 顯示紅色閃爍「LIVE 真錢」chip + 強制免責確認彈窗。

### 2.6 防線 6 — 設定檔分離 + .gitignore

```
.env.sim        ← OHMYSTOCK_BROKER=shioaji-sim + Sim API key（dev / CI 用）
.env.live       ← OHMYSTOCK_BROKER=shioaji-live + Live API key（僅 prod 主機）
.env.example    ← 範本
.env.live → 必須在 .gitignore + 加密存放（cryptography.fernet + OS keyring）
```

CI pipeline 環境變數**寫死** `OHMYSTOCK_BROKER=mock`，永遠不會碰到 Shioaji。

### 2.7 防線 7 — Audit log + 告警

每筆 order audit 必含 `mode` 欄位：

```jsonl
{"ts":"...","kind":"order","mode":"sim","symbol":"2330","qty":1,...}
{"ts":"...","kind":"order","mode":"live","symbol":"2330","qty":1,...}
```

Live 模式啟動 + 每筆 live 下單，**自動寄通知**（Email / Telegram bot）給管理員：「⚠️ Live 模式啟動 / 已下單 X」。Sim 模式不發。

### 2.8 防線 8 — CI 自動 grep 防 live 殘留

CI 加一條 lint：

```yaml
- name: Block accidental live trading code
  run: |
    if grep -RIn "simulation=False\|OHMYSTOCK_BROKER.*live" src/ tests/; then
      echo "❌ 發現可能的 live trading 程式碼/設定"
      exit 1
    fi
```

只在 `src/ohmystock/paper/factory.py` 一處允許出現 `simulation=False`（白名單）。

### 2.9 防線 9 — LLM 自動下單熔斷（v3 新增）

> **適用情境**：`OHMYSTOCK_AUTO_EXECUTE=true` 模式啟用時。對應 cheatsheet §6.7 模式 B。
> **防住什麼**：LLM 幻覺、prompt injection 造成的異常下單。即便決策邏輯正確,LLM 也可能在某些邊界輸入下產生錯誤建議。

```python
# src/ohmystock/paper/auto_execute_breaker.py

class AutoExecuteBreaker:
    """LLM 自動下單熔斷器(僅 sim 模式可啟用,live 模式強制 disabled)"""

    DAILY_ORDER_LIMIT = 5                  # 單日 LLM-decided 下單筆數上限
    SINGLE_ORDER_PCT_LIMIT = 0.25          # 單筆金額上限 = equity × 25%
    MIN_CONFIDENCE = 0.7                   # LLM confidence < 此值 fallback 人工
    MAX_SIZING_DEVIATION = 0.30            # vs 系統公式偏離上限
    LOSS_LOCKOUT_THRESHOLD = -0.05         # 連續 3 筆虧損 > 5% 鎖定
    LOSS_LOCKOUT_HOURS = 24

    def check_or_fallback(self, decision: LLMDecision) -> CheckResult:
        # 0. live 模式強制返回 fallback(雙重保險)
        if not self.broker.is_simulation:
            return Fallback(reason="live mode forces human confirm")

        # 1. confidence 閾值
        if decision.confidence < self.MIN_CONFIDENCE:
            return Fallback(reason=f"confidence {decision.confidence} < {self.MIN_CONFIDENCE}")

        # 2. 單日筆數
        if self.today_count() >= self.DAILY_ORDER_LIMIT:
            return Fallback(reason="daily order limit reached")

        # 3. 單筆金額(由 sizing service 已 enforce,此處再驗一次)
        if decision.notional > self.equity * self.SINGLE_ORDER_PCT_LIMIT:
            return Fallback(reason="single order > 25% equity")

        # 4. 與系統公式偏離
        deviation = abs(decision.proposed_pct - self.system_sizing_pct) / self.system_sizing_pct
        if deviation > self.MAX_SIZING_DEVIATION:
            # 自動取較小者
            decision.proposed_pct = min(decision.proposed_pct, self.system_sizing_pct)

        # 5. 鎖定期(連續 3 筆 LLM-decided 虧損 > 5%)
        if self.is_in_loss_lockout():
            return Fallback(reason="loss streak lockout")

        return Approved()
```

熔斷觸發 → fallback 為人工 confirm(寫入 pending decisions 佇列),不直接下單。每次 fallback 寫 audit log。

> **程式碼 SSOT**：上述閾值（5/0.7/25%/30%/3 連虧 5%/24h）的權威值現由 `ohmystock.config.Settings` 的 `OHMYSTOCK_AUTO_EXECUTE_*` 欄位控制；行為 SSOT 為 `openspec/specs/auto-execute/spec.md`（archive 後）+ `src/ohmystock/safety/auto_execute.py`。本節僅供設計脈絡，調整數值請改 settings + 對應 spec。

### 2.10 防線總表（一目了然）

| # | 防線 | 失敗時的後果 | 防住什麼 |
|---|---|---|---|
| 1 | **Token 物理隔離** | Shioaji 後端拒絕 trading | 程式 bug、設定誤植 |
| 2 | **Env 雙旗標 + validator** | 程式啟動失敗 | 漏設 `simulation=True` |
| 3 | **Broker factory** | 工廠拒絕產生 | 直接 new ShioajiBroker(False) |
| 4 | **place_order 三道 assert** | 下單失敗 | 程式中段被改 |
| 5 | **啟動 banner + UI chip** | 使用者看到紅色警示 | 不知不覺已在 live |
| 6 | **.env 分離 + CI 寫死 mock** | CI 永遠不碰 Shioaji | 測試誤打 live |
| 7 | **Audit + 告警** | 管理員 30 秒內知道 | 已發生時即時止損 |
| 8 | **CI grep lint** | PR 無法合併 | 開發者手滑寫 live |
| **9** | **LLM 自動下單熔斷**(v3) | fallback 為人工 confirm | LLM 幻覺、prompt injection 造成的異常單 |

---

### 2.11 軟性熔斷 — LLM 成本超標自動降階（v3 決策 #15）

> **不算硬性「防線」**，是預算保護機制；防的是「強多頭月候選爆量導致月成本飆破預算」。

**觸發條件**：當月累積 LLM 成本（由 trade journal `llm_cost_usd` 即時聚合）達 **USD $50（NT$ 1,500）**。

**觸發後行為**：
- 設定 `OHMYSTOCK_LLM_DEGRADE=true`
- 所有 LLM call 強制改用 Sonnet 4.6（不再用 Opus 4.7）
- Phase 5 復盤延後到下個月（避開高成本節點）
- Admin Dashboard cost widget 顯示紅色 chip + 觸發時間
- 月初 1 號 00:00 自動清旗標（新月度重啟）

**早期警示**：
- 達 50% (USD $25) → Dashboard widget 黃色
- 達 80% (USD $40) → Dashboard widget 橘色 + 推播一次（若已配通知）
- 達 100% (USD $50) → 觸發軟熔斷如上

**為何不算硬性防線**：軟熔斷不影響交易安全（只影響 LLM 品質），與防線 1-9 的「防止錯誤下單 / 防止 live 誤觸」屬不同範疇。獨立小節記錄。

### 2.11 個人 build-time invariants checklist

> 每次重大改動（如新增防線、改 broker factory、改 confirm gate）後跑一次自我確認：

- [ ] Shioaji token 仍是 sim-only（**未勾 Trading 權限**），且 IP 白名單只含本機
- [ ] `.env` 的 `OHMYSTOCK_BROKER` 不是 `shioaji-live`
- [ ] `.env.live` 不存在於專案目錄（或受 OS keyring 保護）
- [ ] CI / pre-commit hook 仍 grep block `simulation=False` 殘留
- [ ] `verify-sim --strict --skip-live-order` 全綠
- [ ] 防線 1-9 程式碼未被「方便除錯」註解掉

> **未來若評估上 live：** 至少完成「sim 模式穩定跑滿 6 個月」+ 「LLM Decider 月度成本實際 vs 預估誤差 < 30%」+ 「3 個月內無防線觸發 false positive」。三項齊備再考慮切 token + 設 `OHMYSTOCK_LIVE_CONFIRMED`。

---

## 3. 自動化驗證腳本 `verify_simulation.py`（防線總體檢）

**目的**：一鍵跑完所有「確認系統處於模擬模式」的檢查，產出可給自己事後查驗的報告（個人專案的 build-time / pre-deploy 自我檢查）。

**檔案位置**：`src/ohmystock/tools/verify_simulation.py`（亦註冊為 `ohmystock verify-sim` CLI 指令與 `/api/system/verify-sim` 端點）

### 3.1 CLI 介面

```bash
# 全套檢查（預設）
uv run ohmystock verify-sim

# 跳過試下單（不需要市場開盤）
uv run ohmystock verify-sim --skip-live-order

# 輸出 JSON 給 CI / 監控使用
uv run ohmystock verify-sim --format json --output verify-report.json

# 只跑特定 check（除錯用）
uv run ohmystock verify-sim --only env,token

# 嚴格模式：任一警告也算失敗（給 CI 用）
uv run ohmystock verify-sim --strict
```

### 3.2 7 項檢查項目（CheckSpec）

每項檢查實作為一個 class，繼承 `BaseCheck`：

```python
@dataclass
class CheckResult:
    id: str                  # 'env' | 'token' | 'broker' | ...
    name: str                # 顯示名稱
    status: Literal["pass", "warn", "fail", "skip"]
    elapsed_ms: int
    detail: str              # 給人類看的詳細訊息
    evidence: dict           # 機器可讀證據（給 audit 用）
    remediation: str | None  # 失敗時的修復建議
```

| ID | 名稱 | 檢查內容 | Pass 條件 | Fail 行動 |
|---|---|---|---|---|
| `env` | 環境變數檢查 | `OHMYSTOCK_BROKER` 值、`OHMYSTOCK_LIVE_CONFIRMED` 是否未設、無 `.env.live` 檔案載入 | `OHMYSTOCK_BROKER in {"shioaji-sim","mock"}` 且 `OHMYSTOCK_LIVE_CONFIRMED` is None | 拒絕系統啟動，回傳 exit 2 |
| `token` | Token 權限檢查 | 呼叫 Shioaji `api.usage()` 或 token info API 確認當前 token 沒有 Trading scope | response 不含 `"Trading"` 權限 | 拒絕，附「請至 sinotrade 個人服務網站建新 token」連結 |
| `broker` | Broker 實例狀態 | 載入 broker，斷言 `broker._simulation == True` 且 `broker._api.simulation == True` | 兩個都 True | 拒絕，回報哪一層被改 |
| `audit` | 稽核日誌掃描 | grep 近 30 日 `~/.ohmystock/audit/*.jsonl`，確認無 `mode="live"` 紀錄 | 0 筆 live | 嚴重警報，列出可疑 run_id |
| `config_files` | 設定檔檢查 | `.env.live` 不存在或檔案權限 600 不可讀；`.env.example` 不含真 key | 都通過 | 警告 + 自動 chmod 修正建議 |
| `code_lint` | 原始碼掃描 | `grep -RIn "simulation=False"` 全 src/，僅允許出現在白名單檔案 | 僅在 `paper/factory.py:42-45` 區塊 | 列出違規檔案 + 行號 |
| `live_order` | 試下一張小單 + App 對照 | 模擬倉買 1 張 1101（台泥，低價穩定） + 等使用者在永豐 App 確認看不到 | 使用者在 60 秒內按 `[y]` | 5 分鐘無回應 → 視為 fail |

### 3.3 執行流程

```python
# 偽程式碼結構
class VerifySimulation:
    CHECKS: list[type[BaseCheck]] = [
        EnvCheck, TokenCheck, BrokerCheck, AuditCheck,
        ConfigFilesCheck, CodeLintCheck, LiveOrderCheck,
    ]

    async def run(self, only: set[str] | None = None,
                  skip_live_order: bool = False,
                  strict: bool = False) -> VerifyReport:
        results = []
        for cls in self.CHECKS:
            check = cls()
            if only and check.id not in only: continue
            if skip_live_order and check.id == "live_order": continue
            try:
                r = await check.execute()
            except Exception as e:
                r = CheckResult(check.id, check.name, "fail", 0,
                                str(e), {"exception": repr(e)},
                                check.remediation_for_exception(e))
            results.append(r)
            self._print_realtime(r)        # 即時印到 console
        report = VerifyReport(results, strict=strict)
        await audit.log("verify_sim", report.to_dict())
        return report
```

### 3.4 Console 輸出範例

```
$ uv run ohmystock verify-sim

╔══════════════════════════════════════════════════════════╗
║  ohMyStock 模擬模式驗證 v1.0                         ║
║  時間：2026-04-26 14:30:00                                ║
╚══════════════════════════════════════════════════════════╝

[1/7] env          ✓ pass  (12ms)   OHMYSTOCK_BROKER=shioaji-sim, OHMYSTOCK_LIVE_CONFIRMED 未設定
[2/7] token        ✓ pass  (823ms)  Token "ohmystock-sim" 權限：Market, Account（無 Trading）
[3/7] broker       ✓ pass  (8ms)    ShioajiBroker._simulation=True
[4/7] audit        ✓ pass  (45ms)   近 30 日掃描 1,247 筆 order，全部 mode=sim
[5/7] config_files ✓ pass  (3ms)    .env.live 不存在；.env.example 無敏感資訊
[6/7] code_lint    ✓ pass  (156ms)  simulation=False 僅在白名單 paper/factory.py:42
[7/7] live_order   ⏳ 試下單中：模擬倉買 1 張 1101 @ 30.50
                       已下單 ✓（模擬倉 ID: sim_8fa1）
                       請打開永豐 App 確認「真實帳戶」看不到此單，並按 [y] 確認 / [n] 中止
                       > y
                   ✓ pass  (28.3s)  使用者已確認真實帳戶無此單

╔══════════════════════════════════════════════════════════╗
║  ✓ 整體結果：🟢 確認為模擬模式（7/7 全通過）              ║
║  報告已存：~/.ohmystock/audit/verify-2026-04-26.json    ║
╚══════════════════════════════════════════════════════════╝
```

### 3.5 失敗時的範例輸出

```
[2/7] token        ✗ fail  (1.2s)
                   當前 token 包含 "Trading" 權限！
                   修復建議：
                     1. 至 https://account.sinotrade.com.tw 編輯 token "ohmystock-sim"
                     2. 取消勾選「Trading」權限後重新產生 secret_key
                     3. 更新 .env 的 SHIOAJI_SIM_SECRET_KEY
                   證據：
                     {"token_name":"ohmystock-sim","permissions":["Market","Account","Trading"]}

╔══════════════════════════════════════════════════════════╗
║  ✗ 整體結果：🔴 高風險（1 fail / 6 pass）                ║
║  系統將拒絕啟動。修復後重新執行 verify-sim。              ║
╚══════════════════════════════════════════════════════════╝

Exit code: 2
```

### 3.6 Exit Code 約定

| Code | 意義 | 用途 |
|---|---|---|
| `0` | 全綠（all pass） | CI / 排程繼續 |
| `1` | 含 warn 但無 fail | 預設可繼續，`--strict` 視為失敗 |
| `2` | 任一 fail | 必須修復，主程式啟動腳本 refuse |
| `3` | 使用者中止 live_order check | 視為未通過，重跑 |
| `4` | 內部錯誤（無法執行檢查本身） | 監控告警 |

### 3.7 整合點

| 整合對象 | 觸發方式 | 行為 |
|---|---|---|
| **主程式啟動腳本** | `ohmystock serve` 內部先呼叫 `verify-sim --skip-live-order` | exit ≠ 0 → 拒絕啟動 |
| **CI（GitHub Actions）** | 每次 PR + main push | `--strict --skip-live-order`；失敗即擋合併 |
| **每日排程** | APScheduler 每日 08:30（開盤前） | `--skip-live-order`；fail 即發 Email + Telegram |
| **Web UI Settings 頁** | 「執行驗證」按鈕（[frontend.md](frontend.md) 對應 Settings 頁） | 顯示即時進度條 + 結果卡片 |
| **REST API** | `GET /api/system/verify-sim` | 個人 dashboard 顯示「目前是 sim 模式」綠燈用；不串外部監控（個人專案不需 Datadog / Grafana） |
| **手動驗收（切 live 前）** | 自己跑 `ohmystock verify-sim` | 七項全綠 + live_order 對照 → 自我簽署 build-time invariants checklist（§2.11） |

### 3.8 報告檔案結構

存於 `~/.ohmystock/audit/verify-YYYY-MM-DD.json`：

```json
{
  "timestamp": "2026-04-26T14:30:00+08:00",
  "version": "1.0",
  "machine": "DEV-LAPTOP-01",
  "user": "Oolong",
  "broker_mode": "shioaji-sim",
  "overall": "pass",
  "checks": [
    {"id":"env","status":"pass","elapsed_ms":12,"evidence":{"OHMYSTOCK_BROKER":"shioaji-sim"}},
    {"id":"token","status":"pass","elapsed_ms":823,"evidence":{"permissions":["Market","Account"]}},
    {"id":"broker","status":"pass","elapsed_ms":8,"evidence":{"simulation":true}},
    {"id":"audit","status":"pass","elapsed_ms":45,"evidence":{"days_scanned":30,"live_count":0,"sim_count":1247}},
    {"id":"config_files","status":"pass","elapsed_ms":3,"evidence":{".env.live_exists":false}},
    {"id":"code_lint","status":"pass","elapsed_ms":156,"evidence":{"violations":[]}},
    {"id":"live_order","status":"pass","elapsed_ms":28300,"evidence":{"sim_order_id":"sim_8fa1","user_confirmed":true,"sym":"1101","qty":1}}
  ],
  "signature": "sha256:..."  // 防竄改
}
```

報告檔案保留個人歸檔即可（90 天 hot in `~/.ohmystock/audit/`，舊的可手動移到外接備份 / 雲端冷存）。個人專案無金管會稽核需求；保存目的純粹是事後 debug 與成本驗證。

### 3.9 開發優先序

加入 design-zh-TW.md §9 路線圖 Phase 2 第 3 週（Risk Gate 整合那週）：
- Day 1：實作 EnvCheck / BrokerCheck / ConfigFilesCheck / CodeLintCheck（純本地 5 分鐘可寫完）
- Day 2：實作 TokenCheck（需呼叫 Shioaji API，研究 SDK 取 token info 方式）
- Day 3：實作 AuditCheck + 報告產生器
- Day 4：實作 LiveOrderCheck + 整合 CLI 介面 + console UI
- Day 5：CI 整合 + 主程式啟動掛勾 + 文件補齊

---

## 4. Shioaji 模擬倉真實限制

| 議題 | 現況 |
|---|---|
| **是否真實送進撮合** | ❌ **不會**。`sj.Shioaji(simulation=True)` 為 stateful broker mock，立即按最後成交價成交，**不模擬排隊、撮合優先權、部分成交** |
| **即時報價** | ✅ 即使 simulation 模式，行情仍走正式 production feed |
| **登入** | `api_key` + `secret_key`（2023 後不再用身分證號）；憑證 `.pfx` **僅實單需要**，模擬倉不需 |
| **速率上限** | 訂閱 60 req/sec、最多訂閱 500 個合約；WebSocket 每日 03:00 重啟 → 需重連邏輯 |
| **部位持久化** | ❌ Shioaji 後端重啟會清空模擬部位 → **必須在本地 SQLite 鏡射部位（`paper/state.py`）作為 source of truth** |
| **盤後零股模擬** | ❌ 不支援 |
| **訂單類型** | ROD / IOC / FOK 支援 |

> **設計含義**：Shioaji 模擬倉 ≠ 市場模擬器。要做更真實的撮合排隊，需在 `backtest/fills.py` 實作 fill model，**把 Shioaji 當成「下單 ack & 部位帳本」就好**。

---

## 5. 對賬機制（`paper/reconcile.py`）
- 每日盤後與 Shioaji 後端對賬，差異記錄到稽核日誌。
- 部位狀態以本地 SQLite 為主、Shioaji 為輔。
