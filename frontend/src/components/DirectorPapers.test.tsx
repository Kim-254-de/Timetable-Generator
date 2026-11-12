import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { DirectorPapers } from './DirectorPapers'
import type { ExamPaperItem } from '@/lib/types'

const mutate = vi.fn()
vi.mock('@/lib/queries', () => ({ useRemoveDirectorPapers: () => ({ mutate, isPending: false, isError: false }) }))

const paper = (id: string, codes: string, director = true) =>
  ({ id, codes, title: codes, category: 'regular', students: 0, director_paper: director }) as unknown as ExamPaperItem

describe('papers the Director uploaded earlier', () => {
  const papers = [paper('1', 'NURS 101'), paper('2', 'NURS 102'), paper('3', 'NURS 103'), paper('4', 'COSC 200', false)]

  it('shows nothing when there are none', () => {
    const { container } = render(<DirectorPapers termId="t" papers={[papers[3]]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('removes only the selected ones, after asking, and lists no department paper', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<DirectorPapers termId="t" papers={papers} />)
    expect(screen.queryByLabelText(/COSC 200/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove selected (0)' })).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/NURS 101/))
    fireEvent.click(screen.getByLabelText(/NURS 103/))
    fireEvent.click(screen.getByRole('button', { name: 'Remove selected (2)' }))
    expect(confirm).toHaveBeenCalledOnce()
    expect(mutate).not.toHaveBeenCalled() // said no

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Remove selected (2)' }))
    expect(mutate.mock.calls[0][0]).toEqual(['1', '3'])
  })

  it('selects and clears all at once', () => {
    render(<DirectorPapers termId="t" papers={papers} />)
    fireEvent.click(screen.getByLabelText('Select all 3'))
    expect(screen.getByRole('button', { name: 'Remove selected (3)' })).toBeEnabled()
    fireEvent.click(screen.getByLabelText('Select all 3'))
    expect(screen.getByRole('button', { name: 'Remove selected (0)' })).toBeDisabled()
  })
})
