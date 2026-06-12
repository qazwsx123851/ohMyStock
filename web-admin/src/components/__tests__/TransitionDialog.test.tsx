/**
 * <TransitionDialog> tests — required-field validation, submit flow +
 * localStorage write + cache invalidation, server-error inline rendering.
 */
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type Mock,
} from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  TransitionDialog,
  ValidatingConfirmDialog,
} from '@/components/transition-dialog'
import { useAuthStore } from '@/stores'

const ACTOR_KEY = 'ohmystock.admin.actor'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: Mock
let qc: QueryClient

function renderDialog(target: 'approved' | 'merged' | 'rejected') {
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <TransitionDialog
        slug="2026-04-30-x"
        target={target}
        open
        onOpenChange={() => {}}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setToken('test-token-aaaaaaaaaaaaaaaaaaaaaaaa')
  localStorage.clear()
  fetchMock = vi.fn(async () =>
    jsonResponse({
      ok: true,
      data: {
        slug: '2026-04-30-x',
        new_status: 'approved',
        new_path: 'PENDING_REVIEW/2026-04-30-x.md',
      },
    }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock as never)
})

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('TransitionDialog required-field validation', () => {
  it('approved: report path prefilled with <slug>.validation.json; clearing it disables submit', () => {
    renderDialog('approved')
    const submit = screen.getByRole('button', { name: 'Approve' })
    const pathInput = screen.getByLabelText('Validation report path')

    // Manual-verdict flow prefill (proposal-manual-verdict).
    expect(pathInput).toHaveValue('2026-04-30-x.validation.json')
    expect(submit).toBeDisabled() // actor still empty

    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    expect(submit).not.toBeDisabled()

    fireEvent.change(pathInput, { target: { value: '' } })
    expect(submit).toBeDisabled()
  })

  it('merged: submit disabled until merged_to_version filled', () => {
    renderDialog('merged')
    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    const submit = screen.getByRole('button', { name: 'Mark merged' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Merged to version'), {
      target: { value: 'v3.1' },
    })
    expect(submit).not.toBeDisabled()
  })

  it('rejected: submit disabled until reason filled', () => {
    renderDialog('rejected')
    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    const submit = screen.getByRole('button', { name: 'Reject' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Sharpe drop' },
    })
    expect(submit).not.toBeDisabled()
  })
})

describe('TransitionDialog submit flow', () => {
  it('writes actor to localStorage on success and invalidates the proposal query', async () => {
    const onOpenChange = vi.fn()
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    })
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    render(
      <QueryClientProvider client={qc}>
        <TransitionDialog
          slug="2026-04-30-x"
          target="approved"
          open
          onOpenChange={onOpenChange}
        />
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    fireEvent.change(screen.getByLabelText('Validation report path'), {
      target: { value: 'reports/x.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(localStorage.getItem(ACTOR_KEY)).toBe('mark')

    expect(invalidateSpy).toHaveBeenCalled()
    const calls = invalidateSpy.mock.calls.map((c) => c[0])
    expect(calls).toEqual(
      expect.arrayContaining([
        { queryKey: ['proposal', '2026-04-30-x'] },
        { queryKey: ['proposals'] },
      ]),
    )

    const lastCall = fetchMock.mock.calls[
      fetchMock.mock.calls.length - 1
    ] as Parameters<typeof fetch>
    const init = lastCall[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      new_status: 'approved',
      actor: 'mark',
      validation_report_path: 'reports/x.json',
    })
  })

  it('renders inline server error and keeps dialog open on non-200', async () => {
    const onOpenChange = vi.fn()
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          ok: false,
          error: {
            code: 'illegal_transition',
            message: 'pending -> approved is not legal',
          },
        },
        409,
      ),
    )
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    })

    render(
      <QueryClientProvider client={qc}>
        <TransitionDialog
          slug="2026-04-30-x"
          target="approved"
          open
          onOpenChange={onOpenChange}
        />
      </QueryClientProvider>,
    )

    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    fireEvent.change(screen.getByLabelText('Validation report path'), {
      target: { value: 'reports/x.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    const inline = await screen.findByTestId('transition-error')
    expect(inline.textContent).toContain('illegal_transition')
    expect(inline.textContent).toContain('pending -> approved is not legal')
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
    expect(screen.getByRole('button', { name: 'Approve' })).not.toBeDisabled()
  })
})

describe('ValidatingConfirmDialog', () => {
  it('actor-only flow: submit disabled until actor non-empty, then submits', async () => {
    const onOpenChange = vi.fn()
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    })

    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: true,
        data: {
          slug: '2026-04-30-x',
          new_status: 'validating',
          new_path: '2026-04-30-x.md',
        },
      }),
    )

    render(
      <QueryClientProvider client={qc}>
        <ValidatingConfirmDialog
          slug="2026-04-30-x"
          open
          onOpenChange={onOpenChange}
        />
      </QueryClientProvider>,
    )

    const submit = screen.getByRole('button', { name: 'Confirm' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Actor'), {
      target: { value: 'mark' },
    })
    expect(submit).not.toBeDisabled()
    fireEvent.click(submit)

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
    expect(localStorage.getItem(ACTOR_KEY)).toBe('mark')

    const lastCall = fetchMock.mock.calls[
      fetchMock.mock.calls.length - 1
    ] as Parameters<typeof fetch>
    const init = lastCall[1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({
      new_status: 'validating',
      actor: 'mark',
    })
  })
})
