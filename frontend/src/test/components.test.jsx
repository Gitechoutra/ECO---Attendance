import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable, FormModal, StatusBadge } from '../components/ui'
import { fmtMinutes, fmtMoney, initials, titleCase } from '../lib/format'
import { visibleNav } from '../components/layout/nav'

describe('format helpers', () => {
  it('formats money in INR without decimals for whole numbers', () => {
    expect(fmtMoney(43500)).toBe('₹43,500')
    expect(fmtMoney(null)).toBe('—')
  })
  it('formats minutes and names', () => {
    expect(fmtMinutes(545)).toBe('9h 5m')
    expect(fmtMinutes(0)).toBe('0h')
    expect(titleCase('pending_approval')).toBe('Pending Approval')
    expect(initials('Asha Rao Kumar')).toBe('AR')
  })
})

describe('StatusBadge', () => {
  it('humanises status labels', () => {
    render(<StatusBadge status="on_hold" />)
    expect(screen.getByText('On Hold')).toBeInTheDocument()
  })
})

describe('DataTable', () => {
  const columns = [{ key: 'name', header: 'Name' }, { key: 'role', header: 'Role' }]
  it('renders rows and fires row clicks', async () => {
    const onRowClick = vi.fn()
    render(<DataTable columns={columns} rows={[{ id: 1, name: 'Asha', role: 'Dev' }]} onRowClick={onRowClick} />)
    const cells = screen.getAllByText('Asha')
    expect(cells.length).toBeGreaterThan(0)
    await userEvent.click(cells[0])
    expect(onRowClick).toHaveBeenCalledWith({ id: 1, name: 'Asha', role: 'Dev' })
  })
  it('shows an empty state', () => {
    render(<DataTable columns={columns} rows={[]} />)
    expect(screen.getByText('No records found')).toBeInTheDocument()
  })
  it('shows an error state with retry', async () => {
    const retry = vi.fn()
    render(<DataTable columns={columns} rows={null} error="Server down" onRetry={retry} />)
    expect(screen.getByText('Server down')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Try again'))
    expect(retry).toHaveBeenCalled()
  })
})

describe('FormModal', () => {
  const fields = [
    { name: 'title', label: 'Title', required: true },
    { name: 'amount', label: 'Amount', type: 'number' },
    { name: 'kind', label: 'Kind', type: 'select', numeric: true, options: [{ value: 1, label: 'One' }, { value: 2, label: 'Two' }] },
  ]
  it('blocks submission when required fields are empty', async () => {
    const onSubmit = vi.fn()
    render(<FormModal open title="Test" fields={fields} onSubmit={onSubmit} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('Title is required')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })
  it('converts numbers and empty values in the payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue()
    const onClose = vi.fn()
    render(<FormModal open title="Test" fields={fields} onSubmit={onSubmit} onClose={onClose} />)
    await userEvent.type(screen.getByLabelText(/Title/), 'Laptop')
    await userEvent.type(screen.getByLabelText('Amount'), '1200')
    await userEvent.selectOptions(screen.getByLabelText('Kind'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ title: 'Laptop', amount: 1200, kind: 2 }))
    expect(onClose).toHaveBeenCalled()
  })
  it('shows server errors without closing', async () => {
    const onSubmit = vi.fn().mockRejectedValue({ response: { data: { detail: 'Duplicate name' } } })
    const onClose = vi.fn()
    render(<FormModal open title="Test" fields={fields} initial={{ title: 'X' }} onSubmit={onSubmit} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Duplicate name')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('navigation permissions', () => {
  it('hides admin and HR modules from employees', () => {
    const perms = new Set(['ai.use'])
    const labels = visibleNav((...c) => c.some((x) => perms.has(x))).flatMap((s) => s.items.map((i) => i.label))
    expect(labels).toContain('Attendance')
    expect(labels).toContain('Payroll')
    expect(labels).not.toContain('Employees')
    expect(labels).not.toContain('Users & Roles')
    expect(labels).not.toContain('Recruitment')
  })
  it('shows everything to a super admin', () => {
    const labels = visibleNav(() => true).flatMap((s) => s.items.map((i) => i.label))
    expect(labels).toEqual(expect.arrayContaining(['Employees', 'Recruitment', 'Users & Roles', 'Audit Log', 'Settings']))
  })
})
