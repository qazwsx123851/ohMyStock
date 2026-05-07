import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { LogIn, KeyRound } from 'lucide-react'
import { useAuthStore } from '@/stores'

type LocationState = { from?: string }

export function LoginPage() {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const setStoreToken = useAuthStore((s) => s.setToken)
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as LocationState | null)?.from ?? '/'

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = token.trim()
    if (trimmed.length < 32) {
      setError('Token 長度不足；OHMYSTOCK_ADMIN_TOKEN 應 ≥ 32 字元')
      return
    }
    setStoreToken(trimmed)
    navigate(from, { replace: true })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg border bg-card p-8 shadow-md"
      >
        <div className="mb-6 flex items-center gap-2">
          <KeyRound className="size-5 text-muted-foreground" aria-hidden />
          <h1 className="text-lg font-semibold">ohMyStock 後台登入</h1>
        </div>

        <label className="block text-xs font-medium text-muted-foreground" htmlFor="token">
          OHMYSTOCK_ADMIN_TOKEN
        </label>
        <input
          id="token"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => { setToken(e.target.value); if (error) setError(null) }}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={error ? 'token-error' : undefined}
          placeholder="paste-token-from-backend-env"
          className="mt-1 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        {error && (
          <p id="token-error" className="mt-2 text-xs text-destructive">{error}</p>
        )}

        <button
          type="submit"
          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <LogIn className="size-4" aria-hidden />
          登入
        </button>

        <p className="mt-4 text-[11px] text-muted-foreground">
          Token 儲存在本機 <code>localStorage</code>。 使用後請點右上角「登出」清除。
        </p>
      </form>
    </div>
  )
}