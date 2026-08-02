import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { AuditForm } from './components/AuditForm'
import { AuditLog } from './components/AuditLog'
import { EvidenceModal } from './components/EvidenceModal'
import { Header } from './components/Header'
import { StatsGrid } from './components/StatsGrid'
import { UploadZone } from './components/UploadZone'
import type { AuditRecord, DashboardStats } from './types'

const emptyStats: DashboardStats = {
  total_audited: 0,
  flagged_count: 0,
  verified_count: 0,
  pending_count: 0,
}

function App() {
  const [stats, setStats] = useState<DashboardStats>(emptyStats)
  const [records, setRecords] = useState<AuditRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeCardUrl, setActiveCardUrl] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [statsData, recordsData] = await Promise.all([api.getStats(), api.getRecords()])
      setStats(statsData)
      setRecords(recordsData.records)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-700">
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Header />

        {error && (
          <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            Backend unavailable: {error}. Start the API with <code>python main.py serve</code> in{' '}
            <code>backend/</code>.
          </div>
        )}

        <div className="mt-6 space-y-6">
          <StatsGrid stats={stats} />
          <AuditForm onComplete={refresh} onViewCard={(url) => setActiveCardUrl(url)} />
          <UploadZone
            pendingCount={stats.pending_count}
            onComplete={refresh}
            onViewCard={(url) => setActiveCardUrl(url)}
          />
          {loading ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">
              Loading audit records...
            </div>
          ) : (
            <AuditLog
              records={records}
              onClear={refresh}
              onViewCard={(url) => setActiveCardUrl(url)}
            />
          )}
        </div>
      </main>

      <EvidenceModal
        cardUrl={activeCardUrl}
        onClose={() => setActiveCardUrl(null)}
      />
    </div>
  )
}

export default App
