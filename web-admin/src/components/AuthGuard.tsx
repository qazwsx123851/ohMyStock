import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuthStore } from '@/stores'

export function AuthGuard() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}