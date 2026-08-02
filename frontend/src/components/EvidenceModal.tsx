import { useEffect } from 'react'

interface EvidenceModalProps {
  cardUrl: string | null
  onClose: () => void
}

export function EvidenceModal({ cardUrl, onClose }: EvidenceModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  if (!cardUrl) return null

  return (
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center bg-black/60 p-3 sm:p-6 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="relative flex h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-semibold text-slate-900">Evidence Card</h3>
          <div className="flex items-center gap-2">
            <a
              href={cardUrl}
              download
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Save
            </a>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="flex-1">
          <iframe
            src={cardUrl}
            title="Evidence Card"
            className="h-full w-full border-0"
          />
        </div>
      </div>
    </div>
  )
}
