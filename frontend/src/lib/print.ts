import { api } from './api'

/**
 * Prints a PDF from the API with the browser's print dialog. The export is
 * sent as a download (Content-Disposition: attachment), so it is fetched with
 * the session cookie and shown from a blob URL in a hidden frame instead.
 * Where a browser won't print a PDF frame (some Safari versions), the PDF
 * opens in a new tab to print from there.
 */
export async function printPdf(path: string): Promise<void> {
  const { data } = await api.get<Blob>(path, { responseType: 'blob', timeout: 120_000 })
  const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
  const frame = document.createElement('iframe')
  frame.title = 'Timetable to print'
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden'
  // Long enough for the print dialog to have taken its copy.
  const cleanup = () => setTimeout(() => { frame.remove(); URL.revokeObjectURL(url) }, 60_000)
  frame.onload = () => {
    try {
      frame.contentWindow?.focus()
      frame.contentWindow?.print()
    } catch {
      window.open(url, '_blank', 'noopener')
    }
    cleanup()
  }
  frame.src = url
  document.body.appendChild(frame)
}
