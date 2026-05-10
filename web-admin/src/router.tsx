import { createBrowserRouter } from 'react-router'
import { Layout } from '@/components/layout'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { PaperPositionsPage } from '@/pages/PaperPositionsPage'
import { PaperOrdersPage } from '@/pages/PaperOrdersPage'
import { PaperOverviewPage } from '@/pages/PaperOverviewPage'
import { AuditPage } from '@/pages/AuditPage'
import { MarketPage } from '@/pages/MarketPage'
import { MarketSymbolPage } from '@/pages/MarketSymbolPage'
import { BacktestPage } from '@/pages/BacktestPage'
import { BacktestJobPage } from '@/pages/BacktestJobPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SkillsPage } from '@/pages/SkillsPage'
import { SkillDetailPage } from '@/pages/SkillDetailPage'
import { MemoryPage } from '@/pages/MemoryPage'
import { ProposalsPage } from '@/pages/ProposalsPage'
import { ProposalDetailPage } from '@/pages/ProposalDetailPage'
import {
  ChatPage, ChatSessionPage, SwarmPage, SwarmRunPage,
  SessionsPage,
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
      { path: 'proposals',            element: <ProposalsPage /> },
      { path: 'proposals/:slug',      element: <ProposalDetailPage /> },
      { path: 'sessions',             element: <SessionsPage /> },
      { path: 'settings',             element: <SettingsPage /> },
      { path: 'audit',                element: <AuditPage /> },
    ],
  },
])