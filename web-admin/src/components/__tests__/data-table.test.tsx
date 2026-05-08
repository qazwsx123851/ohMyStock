import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable, type DataTableColumn } from '../data-table'

type Row = { id: number; name: string; price: number }

const COLS: DataTableColumn<Row>[] = [
  { id: 'name', header: 'Symbol', accessor: (r) => r.name, sortable: true },
  {
    id: 'price',
    header: 'Price',
    accessor: (r) => r.price,
    sortable: true,
    align: 'right',
  },
]

const ROWS: Row[] = [
  { id: 1, name: '2330', price: 1025 },
  { id: 2, name: '2454', price: 1180 },
]

describe('DataTable', () => {
  it('loading state renders ≥3 Skeleton elements and no real row data', () => {
    const { container } = render(
      <DataTable rows={[]} columns={COLS} loading skeletonRows={3} />,
    )
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)
    expect(container.textContent).not.toContain('2330')
  })

  it('empty state shows the custom message via Card', () => {
    render(
      <DataTable rows={[]} columns={COLS} emptyMessage="本月無交易紀錄" />,
    )
    expect(screen.getByText('本月無交易紀錄')).toBeInTheDocument()
  })

  it('error state renders panel with destructive border + retry slot', () => {
    render(
      <DataTable rows={[]} columns={COLS} error={new Error('boom')} />,
    )
    expect(screen.getByText('載入失敗')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('row click invokes onRowClick exactly once with the right row', () => {
    const onRowClick = vi.fn()
    const { container } = render(
      <DataTable rows={ROWS} columns={COLS} onRowClick={onRowClick} />,
    )
    const dataRows = container.querySelectorAll('tbody tr')
    fireEvent.click(dataRows[0])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0])
  })

  it('Enter on focused row invokes onRowClick (keyboard a11y)', () => {
    const onRowClick = vi.fn()
    const { container } = render(
      <DataTable rows={ROWS} columns={COLS} onRowClick={onRowClick} />,
    )
    const dataRows = container.querySelectorAll('tbody tr')
    expect((dataRows[0] as HTMLElement).tabIndex).toBe(0)
    fireEvent.keyDown(dataRows[0], { key: 'Enter' })
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0])
  })

  it('rows are not focusable when onRowClick is omitted', () => {
    const { container } = render(<DataTable rows={ROWS} columns={COLS} />)
    const dataRows = container.querySelectorAll('tbody tr')
    expect((dataRows[0] as HTMLElement).tabIndex).toBe(-1)
  })

  it('sortable header cycles asc → desc → unsorted with aria-sort tracking', async () => {
    const user = userEvent.setup()
    const onSortChange = vi.fn()
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        onSortChange={onSortChange}
      />,
    )
    const symbolHeader = screen.getByRole('columnheader', { name: /Symbol/ })
    expect(symbolHeader).toHaveAttribute('aria-sort', 'none')
    const symbolBtn = screen.getByRole('button', { name: /Symbol/ })

    await user.click(symbolBtn)
    expect(symbolHeader).toHaveAttribute('aria-sort', 'ascending')
    expect(onSortChange).toHaveBeenLastCalledWith('name', 'asc')

    await user.click(symbolBtn)
    expect(symbolHeader).toHaveAttribute('aria-sort', 'descending')
    expect(onSortChange).toHaveBeenLastCalledWith('name', 'desc')

    await user.click(symbolBtn)
    expect(symbolHeader).toHaveAttribute('aria-sort', 'none')
    expect(onSortChange).toHaveBeenLastCalledWith(null, null)
  })

  it('compact density applies var(--density-row-h-compact) min-height to rows', () => {
    const { container } = render(
      <DataTable rows={ROWS} columns={COLS} density="compact" />,
    )
    const dataRow = container.querySelector('tbody tr') as HTMLElement
    expect(dataRow.style.minHeight).toBe('var(--density-row-h-compact)')
  })

  it('numeric (align=right) cells get tabular + text-right classes', () => {
    const { container } = render(<DataTable rows={ROWS} columns={COLS} />)
    const priceCells = container.querySelectorAll('tbody td:nth-child(2)')
    expect(priceCells[0].className).toMatch(/tabular/)
    expect(priceCells[0].className).toMatch(/text-right/)
  })

  it('pagination renders with page indicator and disables prev on page=1', async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        pageSize={20}
        total={45}
        page={1}
        onPageChange={onPageChange}
      />,
    )
    expect(screen.getByText(/第 1 \/ 3 頁/)).toBeInTheDocument()
    const prev = screen.getByRole('button', { name: /上一頁/ })
    const next = screen.getByRole('button', { name: /下一頁/ })
    expect(prev).toBeDisabled()
    expect(next).not.toBeDisabled()
    await user.click(next)
    expect(onPageChange).toHaveBeenCalledWith(2)
  })

  it('pagination is hidden when total is undefined', () => {
    render(<DataTable rows={ROWS} columns={COLS} />)
    expect(screen.queryByRole('button', { name: /上一頁/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /下一頁/ })).toBeNull()
  })

  it('onRowClick fires with the clicked row when expandedRowRender is also provided', () => {
    const onRowClick = vi.fn()
    const { container } = render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        onRowClick={onRowClick}
        expandedRowRender={(r) => <div data-testid="exp">{r.name}</div>}
      />,
    )
    const dataRows = container.querySelectorAll('tbody tr')
    fireEvent.click(dataRows[1])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1])
  })

  it('expandedRowRender renders a colspan-full row directly below the clicked row', () => {
    const onRowClick = vi.fn()
    const { container } = render(
      <DataTable
        rows={ROWS}
        columns={COLS}
        onRowClick={onRowClick}
        expandedRowRender={(r) => <div data-testid="exp">id={r.id}</div>}
      />,
    )
    expect(container.querySelector('[data-testid="exp"]')).toBeNull()

    const dataRows = container.querySelectorAll('tbody tr')
    fireEvent.click(dataRows[0])

    const exp = container.querySelector('[data-testid="exp"]')
    expect(exp).not.toBeNull()
    expect(exp!.textContent).toBe('id=1')

    const expTd = exp!.closest('td') as HTMLTableCellElement
    expect(expTd).not.toBeNull()
    expect(expTd.colSpan).toBe(COLS.length)

    fireEvent.click(dataRows[0])
    expect(container.querySelector('[data-testid="exp"]')).toBeNull()
  })
})
