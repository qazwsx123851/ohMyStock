import { ComingSoon } from '@/components/ComingSoon'

const make = (name: string, description: string) => () =>
  <ComingSoon name={name} description={description} />

export const ChatPage           = make('對話模式',     '單一 agent 自由問答；session 列表與歷史續寫')
export const ChatSessionPage    = make('對話 Session', '進入既有 session 繼續對話')
export const SwarmPage          = make('Swarm 入口',   '10 個 preset 卡片：選股、復盤、報表、策略提案…')
export const SwarmRunPage       = make('Swarm 執行',   'DAG 即時更新與節點輸出')
export const BacktestPage       = make('回測入口',     '策略表單 + 歷史 job 列表')
export const BacktestJobPage    = make('回測結果',     '資金曲線 / 回撤 / 交易明細 / 診斷')
export const MarketPage         = make('市場掃描',     '即時行情、籌碼、強弱排行')
export const MarketSymbolPage   = make('個股頁',       'K 線 + 三大法人 + 融資融券 + 籌碼分點')
export const SkillsPage         = make('Skills 瀏覽', '已註冊 skill 清單與啟停')
export const SkillDetailPage    = make('Skill 詳情',  'YAML + Markdown 預覽 + 編輯')
export const MemoryPage         = make('長期記憶',     'FTS5 全文索引、tag 過濾')
export const SessionsPage       = make('對話歷史',     '所有 session 列表與全文搜尋')
export const SettingsPage       = make('設定',         'API Key、Shioaji、FinMind、主題、合規開關')