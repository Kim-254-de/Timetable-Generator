import { useState } from 'react'
import { errorMessage } from '@/lib/api'
import type { BulkResult } from '@/lib/types'
import { Dialog } from './Dialog'

export interface BulkColumn {
  key: string
  label: string
  example: string
  required?: boolean
  hint?: string
}

/**
 * Splits text pasted from Excel (tab-separated) or a CSV file (comma-separated,
 * double quotes allowed) into rows keyed by the header row's column names.
 */
export function parseTable(text: string): Record<string, string>[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n').filter((l) => l.trim() !== '')
  if (lines.length < 2) return []
  const delimiter = lines[0].includes('\t') ? '\t' : ','
  const split = (line: string): string[] => {
    if (delimiter === '\t') return line.split('\t')
    const out: string[] = []
    let cell = ''
    let quoted = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') { cell += '"'; i++ }
        else if (ch === '"') quoted = false
        else cell += ch
      } else if (ch === '"') quoted = true
      else if (ch === ',') { out.push(cell); cell = '' }
      else cell += ch
    }
    out.push(cell)
    return out
  }
  const header = split(lines[0]).map((h) => h.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''))
  return lines.slice(1).map((line) => {
    const cells = split(line)
    const row: Record<string, string> = {}
    header.forEach((h, i) => { if (h) row[h] = (cells[i] ?? '').trim() })
    return row
  })
}

export function templateCsv(columns: BulkColumn[]): string {
  const quote = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
  return [columns.map((c) => quote(c.label)).join(','), columns.map((c) => quote(c.example)).join(',')].join('\n') + '\n'
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * "Paste from Excel": the Director copies a block of cells (with its header
 * row) from Excel or opens a CSV, pastes it here, and every line is added or
 * updated. Bad lines are listed by number and skipped.
 */
export function BulkPaste({
  title,
  columns,
  templateName,
  submit,
  onClose,
}: {
  title: string
  columns: BulkColumn[]
  templateName: string
  submit: (rows: Record<string, string>[]) => Promise<BulkResult>
  onClose: () => void
}) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<BulkResult | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const rows = parseTable(text)

  const send = async () => {
    setBusy(true)
    setFailure(null)
    try {
      setResult(await submit(rows))
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const readFile = async (file: File | undefined) => {
    if (file) setText(await file.text())
  }

  return (
    <Dialog title={title} onClose={onClose} wide>
      <p className="text-sm text-slate-600">
        Copy the cells from Excel <b>including the header row</b> and paste them below, or open a CSV file. Existing items
        (same code) are updated; new ones are added.
      </p>
      <div className="mt-2 overflow-x-auto rounded-md border border-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-500">
            <tr>{columns.map((c) => <th key={c.key} className="px-2 py-1 font-medium">{c.label}{c.required ? ' *' : ''}</th>)}</tr>
          </thead>
          <tbody>
            <tr>{columns.map((c) => <td key={c.key} className="px-2 py-1 text-slate-600">{c.example}</td>)}</tr>
          </tbody>
        </table>
      </div>
      {columns.some((c) => c.hint) && (
        <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
          {columns.filter((c) => c.hint).map((c) => <li key={c.key}><b>{c.label}:</b> {c.hint}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
        <button type="button" onClick={() => downloadText(templateName, templateCsv(columns))} className="text-emerald-700">
          Download the template (CSV)
        </button>
        <label className="cursor-pointer text-emerald-700">
          Open a CSV file
          <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" onChange={(e) => void readFile(e.target.files?.[0])} />
        </label>
      </div>
      <textarea value={text} onChange={(e) => { setText(e.target.value); setResult(null) }} rows={10} aria-label="Pasted rows"
        placeholder={columns.map((c) => c.label).join('\t')}
        className="mt-2 w-full rounded-md border border-slate-300 px-2 py-1 font-mono text-xs" />
      <p className="text-xs text-slate-500">{rows.length} rows read.</p>
      {failure && <p role="alert" className="text-sm text-red-700">{failure}</p>}
      {result && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 text-sm">
          <p className="text-emerald-800">{result.created} added, {result.updated} updated.</p>
          {result.error_count > 0 && (
            <>
              <p className="text-red-700">{result.error_count} rows skipped:</p>
              <ul className="max-h-40 list-disc overflow-y-auto pl-5 text-red-700">
                {result.errors.map((e) => <li key={e.line}>Row {e.line}: {e.message}</li>)}
              </ul>
            </>
          )}
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Close</button>
        <button type="button" onClick={() => void send()} disabled={!rows.length || busy}
          className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">
          {busy ? 'Saving…' : `Save ${rows.length} rows`}
        </button>
      </div>
    </Dialog>
  )
}
