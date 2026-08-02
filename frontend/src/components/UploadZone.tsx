import { useRef, useState } from 'react'
import { api, resolveAssetUrl } from '../api/client'

interface UploadZoneProps {
  pendingCount: number
  onComplete: () => void
  onViewCard: (url: string) => void
}

export function UploadZone({ pendingCount, onComplete, onViewCard }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [status, setStatus] = useState<{ type: 'idle' | 'processing' | 'success' | 'error'; message: string }>({
    type: 'idle',
    message: '',
  })

  async function uploadFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return

    setStatus({
      type: 'processing',
      message: `Uploading and auditing ${fileList.length} tender file(s)...`,
    })

    try {
      const data = await api.uploadTenders(fileList)
      if (data.status === 'success') {
        setStatus({ type: 'success', message: data.message || 'Upload complete' })
        onComplete()
        if (data.results?.[0]?.evidence_card_url) {
          onViewCard(resolveAssetUrl(data.results[0].evidence_card_url))
        }
      } else {
        setStatus({ type: 'error', message: data.message || data.detail || 'Upload failed' })
      }
    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Upload failed',
      })
    }
  }

  async function scanFolder() {
    setScanning(true)
    setStatus({ type: 'processing', message: 'Scanning tender folder...' })

    try {
      const data = await api.scanFolder()
      if (data.status === 'success') {
        setStatus({ type: 'success', message: data.message || 'Scan complete' })
        onComplete()
      } else {
        setStatus({ type: 'error', message: data.message || 'Scan failed' })
      }
    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Scan failed',
      })
    } finally {
      setScanning(false)
    }
  }

  const statusClasses = {
    idle: 'hidden',
    processing: 'block border-blue-200 bg-blue-50 text-blue-800',
    success: 'block border-green-200 bg-green-50 text-green-800',
    error: 'block border-rose-200 bg-rose-50 text-rose-900',
  }

  return (
    <section
      className={`rounded-2xl border border-dashed border-yellow-300 bg-yellow-50 p-5 transition ${dragOver ? 'border-yellow-600 bg-yellow-100' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={(e) => {
        e.preventDefault()
        setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        uploadFiles(e.dataTransfer.files)
      }}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-yellow-200 px-3 py-2 text-sm font-bold text-yellow-900">DOC</span>
          <div>
            <p className="font-bold text-yellow-900">Upload Tenders</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.txt,.csv"
            className="hidden"
            onChange={(e) => uploadFiles(e.target.files)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="rounded-xl border border-yellow-300 bg-white px-4 py-2.5 text-sm font-semibold text-yellow-950 shadow-sm hover:bg-yellow-100/50"
          >
            Upload File(s)
          </button>
          <button
            type="button"
            disabled={scanning}
            onClick={scanFolder}
            className="rounded-xl bg-yellow-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-yellow-800 disabled:opacity-50"
          >
            {scanning ? 'Scanning...' : `Scan Server Folder (${pendingCount} pending)`}
          </button>
        </div>
      </div>

      <div className={`mt-3 rounded-lg border px-3 py-2 text-sm font-medium ${statusClasses[status.type]}`}>
        {status.message}
      </div>
    </section>
  )
}
