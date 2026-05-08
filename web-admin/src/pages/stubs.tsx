import { ComingSoon } from '@/components/ComingSoon'

const make = (name: string, description: string) => () =>
  <ComingSoon name={name} description={description} />

export const ChatPage           = make('對話模式',     '單一 agent 自由問答；session 列表與歷史續寫')
export const ChatSessionPage    = make('對話 Session', '進入既有 session 繼續對話')
export const SwarmPage          = make('Swarm 入口',   '10 個 preset 卡片：選股、復盤、報表、策略提案…')
export const SwarmRunPage       = make('Swarm 執行',   'DAG 即時更新與節點輸出')
export const SkillsPage         = make('Skills 瀏覽', '已註冊 skill 清單與啟停')
export const SkillDetailPage    = make('Skill 詳情',  'YAML + Markdown 預覽 + 編輯')
export const MemoryPage         = make('長期記憶',     'FTS5 全文索引、tag 過濾')
export const SessionsPage       = make('對話歷史',     '所有 session 列表與全文搜尋')