import { createBrowserRouter } from 'react-router'
import { Layout } from '@/components/layout'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { PaperPositionsPage } from '@/pages/PaperPositionsPage'
import { PaperOrdersPage } from '@/pages/PaperOrdersPage'
import { PaperOverviewPage } from '@/pages/PaperOverviewPage'
import { AuditPage } from '@/pages/AuditPage'
import {
  ChatPage, ChatSessionPage, SwarmPage, SwarmRunPage, BacktestPage, BacktestJobPage,
  MarketPage, MarketSymbolPage,
  SkillsPage, SkillDetailPage, MemoryPage, SessionsPage, SettingsPage,
} from '@/pages/stubs'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true,                  element: <DashboardPage /> },
      { path: 'chat',                 element: <ChatPage /> },
      { path: 'chat/:sessionId',      element: <ChatSessionPage /> },
      { path: 'swarm',                element: <SwarmPage /> },
      { path: 'swarm/:preset/:runId', element: <SwarmRunPage /> },
      { path: 'backtest',             element: <BacktestPage /> },
      { path: 'backtest/:jobId',      element: <BacktestJobPage /> },
      { path: 'paper',                element: <PaperOverviewPage /> },
      { path: 'paper/orders',         element: <PaperOrdersPage /> },
      { path: 'paper/positions',      element: <PaperPositionsPage /> },
      { path: 'market',               element: <MarketPage /> },
      { path: 'market/:symbol',       element: <MarketSymbolPage /> },
      { path: 'skills',               element: <SkillsPage /> },
      { path: 'skills/:name',         element: <SkillDetailPage /> },
      { path: 'memory',               element: <MemoryPage /> },
      { path: 'sessions',             element: <SessionsPage /> },
      { path: 'settings',             element: <SettingsPage /> },
      { path: 'audit',                element: <AuditPage /> },
    ],
  },
])