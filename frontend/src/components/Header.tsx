export function Header() {
  return (
    <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <img
          src="/logo.jpeg"
          alt="Sentra"
          className="h-11 w-11 rounded-xl object-cover"
        />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sentra</h1>
          <p className="text-sm text-slate-500">Satellite Audit Platform</p>
        </div>
      </div>
      <div className="inline-flex items-center gap-2 rounded-full border border-green-200 bg-green-50 px-3.5 py-1.5 text-xs font-semibold text-green-800">
        <span className="h-1.5 w-1.5 rounded-full bg-green-600 shadow-[0_0_6px_rgba(22,163,74,0.4)]" />
        Esri Wayback Feed Active
      </div>
    </header>
  )
}
