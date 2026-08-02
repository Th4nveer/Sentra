import type { DashboardStats } from '../types'

interface StatsGridProps {
  stats: DashboardStats
}

export function StatsGrid({ stats }: StatsGridProps) {
  const cards = [
    { label: 'Audited Projects', value: stats.total_audited, tone: 'blue' },
    { label: 'Flagged for Verification', value: stats.flagged_count, tone: 'red' },
    { label: 'Verified Physical Work', value: stats.verified_count, tone: 'green' },
  ] as const

  const toneClasses = {
    blue: 'border-blue-100 bg-blue-50 text-blue-900',
    red: 'border-rose-100 bg-rose-50 text-rose-900',
    green: 'border-green-100 bg-green-50 text-green-900',
  }

  const labelClasses = {
    blue: 'text-blue-800',
    red: 'text-rose-800',
    green: 'text-green-800',
  }

  return (
    <section className="grid gap-5 md:grid-cols-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className={`rounded-2xl border p-5 transition hover:-translate-y-0.5 ${toneClasses[card.tone]}`}
        >
          <p className={`text-xs font-bold uppercase tracking-wide ${labelClasses[card.tone]}`}>
            {card.label}
          </p>
          <p className="mt-1 text-4xl font-bold tracking-tight">{card.value}</p>
        </div>
      ))}
    </section>
  )
}
