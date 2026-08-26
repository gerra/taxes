import { act, fireEvent, render, screen } from '@testing-library/react'
import { ConfirmProvider, useConfirm } from '../components/ConfirmDialog'

function Harness({ onResult }: { onResult: (r: { ok: boolean; input?: string }) => void }) {
  const confirm = useConfirm()
  return (
    <button
      onClick={async () =>
        onResult(
          await confirm({
            title: 'Delete it?',
            message: 'Gone forever.',
            confirmLabel: 'Delete',
            danger: true,
            input: { label: 'Note' },
          }),
        )
      }
    >
      open
    </button>
  )
}

test('modal resolves with ok + input on confirm, false on cancel', async () => {
  const results: { ok: boolean; input?: string }[] = []
  render(
    <ConfirmProvider>
      <Harness onResult={(r) => results.push(r)} />
    </ConfirmProvider>,
  )
  await act(async () => {
    fireEvent.click(screen.getByText('open'))
  })
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('Gone forever.')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'dormant' } })
  await act(async () => {
    fireEvent.click(screen.getByText('Delete'))
  })
  expect(results).toEqual([{ ok: true, input: 'dormant' }])
  expect(screen.queryByRole('dialog')).toBeNull()

  await act(async () => {
    fireEvent.click(screen.getByText('open'))
  })
  await act(async () => {
    fireEvent.click(screen.getByText('Cancel'))
  })
  expect(results[1]).toEqual({ ok: false, input: undefined })
})
