import { ComingSoon } from '@/components/ComingSoon'

const make = (name: string, description: string) => () =>
  <ComingSoon name={name} description={description} />

export const ChatPage           = make('對話模式',     '單一 agent 自由問答；session 列表與歷史續寫')
export const ChatSessionPage    = make('對話 Session', '進入既有 session 繼續對話')
export const SessionsPage       = make('對話歷史',     '所有 session 列表與全文搜尋')