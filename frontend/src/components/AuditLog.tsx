import type { AuditRecord } from '../types'
import { api, resolveAssetUrl } from '../api/client'

interface AuditLogProps {
  records: AuditRecord[]
  onClear: () => void
  onViewCard: (url: string) => void
}

const badgeClasses: Record<string, string> = {
  PRIORITY_FIELD_VERIFICATION_RECOMMENDED: 'bg-rose-100 text-rose-800 border-rose-200',
  PARTIAL_CHANGE_DETECTED: 'bg-amber-100 text-amber-900 border-amber-200',
  HIGH_PHYSICAL_CHANGE_VERIFIED: 'bg-green-100 text-green-800 border-green-200',
}

export function AuditLog({ records, onClear, onViewCard }: AuditLogProps) {
  async function handleClear() {
    if (!confirm('Are you sure you want to clear all audited records?')) return
    await api.clearHistory()
    onClear()
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <h2 className="text-base font-bold text-slate-900">Audit Results Log</h2>
        <button
          type="button"
          onClick={handleClear}
          className="rounded-lg border border-rose-200 px-3 py-1.5 text-sm font-semibold text-rose-600 hover:bg-rose-50"
        >
          Clear History
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-5 py-3">Project</th>
              <th className="px-5 py-3">Location</th>
              <th className="px-5 py-3">Verdict</th>
              <th className="px-5 py-3 text-right">Evidence Card</th>
            </tr>
          </thead>
          <tbody>
            {records.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-slate-500">
                  No satellite audits in database yet. Submit a work site above or upload tender documents.
                </td>
              </tr>
            ) : (
              records.map((record) => {
                const location =
                  record.geocoding.formatted_address.length > 55
                    ? `${record.geocoding.formatted_address.slice(0, 52)}...`
                    : record.geocoding.formatted_address

                return (
                  <tr key={record.tender_id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-5 py-4">
                      <div className="font-bold text-slate-900">{record.project_name}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {record.source === 'citizen' ? 'Citizen' : 'Tender'} |{' '}
                        <code className="rounded bg-slate-100 px-1.5 py-0.5">{record.tender_id}</code>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-slate-500">{location}</td>
                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${badgeClasses[record.audit.classification] || 'bg-slate-100 text-slate-700 border-slate-200'}`}
                      >
                        {record.verdict_label}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <button
                        type="button"
                        onClick={() => onViewCard(resolveAssetUrl(record.evidence_card_url))}
                        className="font-bold text-slate-900 transition hover:text-indigo-600"
                      >
                        View Card
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
