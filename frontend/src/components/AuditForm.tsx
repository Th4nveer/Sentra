import { useEffect, useState } from 'react'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { api, resolveAssetUrl } from '../api/client'

const defaultLat = 12.9716
const defaultLon = 77.5946

const markerIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
})

function MapClickHandler({
  onSelect,
}: {
  onSelect: (lat: number, lon: number) => void
}) {
  useMapEvents({
    click(e) {
      onSelect(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function MapRecenter({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap()
  useEffect(() => {
    map.setView([lat, lng], map.getZoom(), { animate: true })
  }, [lat, lng, map])
  return null
}

interface AuditFormProps {
  onComplete: () => void
  onViewCard: (url: string) => void
}

export function AuditForm({ onComplete, onViewCard }: AuditFormProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [latitude, setLatitude] = useState(defaultLat)
  const [longitude, setLongitude] = useState(defaultLon)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [status, setStatus] = useState<{ type: 'idle' | 'processing' | 'success' | 'error'; message: string }>({
    type: 'idle',
    message: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [locating, setLocating] = useState(false)

  const handleLocateMe = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported by your browser')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLatitude(pos.coords.latitude)
        setLongitude(pos.coords.longitude)
        setLocating(false)
      },
      (err) => {
        console.warn('Geolocation error:', err)
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  useEffect(() => {
    const today = new Date()
    const sixMonthsAgo = new Date()
    sixMonthsAgo.setMonth(today.getMonth() - 6)
    setStartDate(sixMonthsAgo.toISOString().slice(0, 10))
    setEndDate(today.toISOString().slice(0, 10))

    handleLocateMe()
  }, [])

  async function handleSubmit() {
    if (!title.trim()) {
      alert('Please enter a project or work title.')
      return
    }

    setSubmitting(true)
    setStatus({
      type: 'processing',
      message: 'Running audit...',
    })

    try {
      const data = await api.submitCommunityReport({
        title: title.trim(),
        description: description.trim(),
        latitude,
        longitude,
        estimated_start_date: startDate || undefined,
        estimated_end_date: endDate || undefined,
      })

      if (data.status === 'success' && data.evidence_card_url) {
        setStatus({ type: 'success', message: `Audit complete - Verdict: ${data.verdict}` })
        onComplete()
        onViewCard(resolveAssetUrl(data.evidence_card_url))
      } else {
        setStatus({ type: 'error', message: data.detail || 'Audit failed' })
      }
    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Request failed',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const statusClasses = {
    idle: 'hidden',
    processing: 'block border-blue-200 bg-blue-50 text-blue-800',
    success: 'block border-green-200 bg-green-50 text-green-800',
    error: 'block border-rose-200 bg-rose-50 text-rose-900',
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">Report a Site</h2>
        <button
          type="button"
          onClick={handleLocateMe}
          disabled={locating}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          <span className="text-sm">📍</span>
          {locating ? 'Locating...' : 'Use My Location'}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Work Title</span>
            <input
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
              placeholder="e.g. Ward 12 Connector Road Asphalt Resurfacing"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Description (Optional)</span>
            <textarea
              className="min-h-[70px] w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
              placeholder="Brief description of the work going on..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Latitude</span>
              <input
                type="number"
                step="any"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
                value={latitude}
                onChange={(e) => setLatitude(parseFloat(e.target.value) || 0)}
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Longitude</span>
              <input
                type="number"
                step="any"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
                value={longitude}
                onChange={(e) => setLongitude(parseFloat(e.target.value) || 0)}
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Estimated Start Date</span>
              <input
                type="date"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-900">Completion / Check Date</span>
              <input
                type="date"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
              <span className="text-xs text-slate-500">Defaults to today if left blank</span>
            </label>
          </div>

          <button
            type="button"
            disabled={submitting}
            onClick={handleSubmit}
            className="inline-flex w-full items-center justify-center rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Running audit...' : 'Run Audit'}
          </button>

          <div className={`rounded-lg border px-3 py-2 text-sm font-medium ${statusClasses[status.type]}`}>
            {status.message}
          </div>
        </div>

        <div className="space-y-2">
          <div className="relative z-0 isolate h-[330px] overflow-hidden rounded-xl border border-slate-200">
            <MapContainer
              center={[latitude, longitude]}
              zoom={13}
              scrollWheelZoom
              className="h-full w-full"
            >
              <TileLayer
                attribution="OpenStreetMap"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <MapRecenter lat={latitude} lng={longitude} />
              <MapClickHandler onSelect={(lat, lon) => {
                setLatitude(lat)
                setLongitude(lon)
              }} />
              <Marker
                position={[latitude, longitude]}
                icon={markerIcon}
                draggable
                eventHandlers={{
                  dragend: (e) => {
                    const marker = e.target as L.Marker
                    const pos = marker.getLatLng()
                    setLatitude(pos.lat)
                    setLongitude(pos.lng)
                  },
                }}
              />
            </MapContainer>
          </div>
          <p className="text-center text-xs text-slate-500">
            Drag pin or click map to pick coordinates, or type Lat/Lon manually
          </p>
        </div>
      </div>
    </section>
  )
}
