import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import {
  LayoutDashboard, MessagesSquare, Network, FlaskConical, ReceiptText, ListOrdered,
  Briefcase, LineChart, BookOpen, History, Settings, ShieldCheck, Sparkles,
  ClipboardList, GitPullRequest,
  PanelLeftClose, PanelLeftOpen, LogOut, Sun, Moon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiStore, logout } from '@/stores'
import { AuthGuard } from '@/components/AuthGuard'

type NavItem = { to: string; label: string; icon: React.ComponentType<{ className?: string }> }
type NavGroup = { name: string; items: NavItem[] }

const NAV: NavGroup[] = [
  {
    name: '工作流',
    items: [
      { to: '/',         label: 'Dashboard', icon: LayoutDashboard },
      { to: '/chat',     label: '對話模式',  icon: MessagesSquare },
      { to: '/swarm',    label: 'Swarm',     icon: Network },
      { to: '/backtest', label: '回測',      icon: FlaskConical },
    ],
  },
  {
    name: '交易',
    items: [
      { to: '/paper',           label: '模擬交易', icon: Briefcase },
      { to: '/paper/orders',    label: '委託歷史', icon: ReceiptText },
      { to: '/paper/positions', label: '持倉明細', icon: ListOrdered },
    ],
  },
  {
    name: '研究',
    items: [
      { to: '/market',   label: '市場掃描', icon: LineChart },
      { to: '/skills',   label: 'Skills',   icon: Sparkles },
      { to: '/memory',   label: '長期記憶', icon: BookOpen },
      { to: '/sessions', label: '對話歷史', icon: History },
    ],
  },
  {
    name: '復盤',
    items: [
      { to: '/reviews',   label: 'Reviews',   icon: ClipboardList },
      { to: '/proposals', label: 'Proposals', icon: GitPullRequest },
    ],
  },
  {
    name: '系統',
    items: [
      { to: '/settings', label: '設定', icon: Settings },
      { to: '/audit',    label: '稽核', icon: ShieldCheck },
    ],
  },
]

const TITLE_BY_PATH: Record<string, string> = {
  '/':                'Dashboard',
  '/chat':            '對話模式',
  '/swarm':           'Swarm',
  '/backtest':        '回測',
  '/paper':           '模擬交易',
  '/paper/orders':    '委託歷史',
  '/paper/positions': '持倉明細',
  '/market':          '市場掃描',
  '/skills':          'Skills',
  '/memory':          '長期記憶',
  '/sessions':        '對話歷史',
  '/reviews':         'Reviews',
  '/proposals':       'Proposals',
  '/settings':        '設定',
  '/audit':           '稽核日誌',
}

function pageTitle(pathname: string): string {
  if (TITLE_BY_PATH[pathname]) return TITLE_BY_PATH[pathname]
  if (pathname.startsWith('/chat/'))     return '對話 Session'
  if (pathname.startsWith('/swarm/'))    return 'Swarm 執行'
  if (pathname.startsWith('/backtest/')) return '回測結果'
  if (pathname.startsWith('/market/'))   return '個股頁'
  if (pathname.startsWith('/skills/'))   return 'Skill 詳情'
  if (pathname.startsWith('/reviews/'))  return 'Review 詳情'
  if (pathname.startsWith('/proposals/')) return 'Proposal 詳情'
  return 'ohMyStock'
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  const toggle = useUiStore((s) => s.toggleSidebar)
  return (
    <nav
      aria-label="主導覽"
      className={cn(
        'flex h-full flex-col border-r bg-card transition-[width] duration-200',
        collapsed ? 'w-14' : 'w-60',
      )}
    >
      <div className={cn('flex items-center gap-2 px-3 py-3 text-sm font-semibold', collapsed && 'justify-center')}>
        {!collapsed && <span className="text-base">ohMyStock</span>}
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? '展開側邊欄' : '收合側邊欄'}
          className="ml-auto rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
        >
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {NAV.map((group) => (
          <div key={group.name} className="mt-3 first:mt-0">
            {!collapsed && (
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {group.name}
              </div>
            )}
            <ul>
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors cursor-pointer',
                        'hover:bg-muted hover:text-foreground',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        isActive ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground',
                        collapsed && 'justify-center',
                      )
                    }
                  >
                    <item.icon className="size-4 shrink-0" aria-hidden />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// TopBar - title + clock + logout
// ---------------------------------------------------------------------------

function TpeClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const formatted = now.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })
  return <span className="tabular text-xs text-muted-foreground" title="Asia/Taipei">{formatted}</span>
}

function ThemeToggle() {
  const theme = useUiStore((s) => s.theme)
  const toggleTheme = useUiStore((s) => s.toggleTheme)
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? '切換為淺色' : '切換為深色'}
      title={isDark ? '切換為淺色' : '切換為深色'}
      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {isDark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </button>
  )
}

function TopBar() {
  const location = useLocation()
  return (
    <header className="flex h-12 items-center gap-3 border-b bg-card px-4">
      <h1 className="text-sm font-semibold text-foreground">{pageTitle(location.pathname)}</h1>
      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
        <TpeClock />
        <button
          type="button"
          onClick={logout}
          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="登出"
        >
          <LogOut className="size-3.5" aria-hidden />
          <span>登出</span>
        </button>
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// DisclaimerFooter
// ---------------------------------------------------------------------------

function DisclaimerFooter() {
  return (
    <footer className="border-t bg-card px-4 py-1.5 text-center text-[11px] text-muted-foreground">
      模擬交易僅供研究 · 非投資建議 · 本系統不涉及實單委託
    </footer>
  )
}

// ---------------------------------------------------------------------------
// Layout - composes everything; wraps Outlet in AuthGuard
// ---------------------------------------------------------------------------

export function Layout() {
  return (
    <div className="grid h-screen grid-cols-[auto_1fr] grid-rows-[auto_1fr_auto] bg-background">
      <div className="row-span-3"><Sidebar /></div>
      <div><TopBar /></div>
      <main className="overflow-y-auto p-6">
        <AuthGuard />
      </main>
      <div><DisclaimerFooter /></div>
    </div>
  )
}