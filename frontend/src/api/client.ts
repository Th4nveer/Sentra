import type { ApiStatusResponse, AuditRecord, DashboardStats } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || error.message || 'Request failed')
  }
  return response.json() as Promise<T>
}

export function resolveAssetUrl(path: string): string {
  if (path.startsWith('http')) return path
  return `${API_BASE}${path}`
}

export const api = {
  getStats: () => request<DashboardStats>('/api/stats'),
  getRecords: () => request<{ records: AuditRecord[] }>('/api/records'),
  submitCommunityReport: (body: {
    title: string
    description?: string
    latitude: number
    longitude: number
    estimated_start_date?: string
    estimated_end_date?: string
  }) =>
    request<ApiStatusResponse>('/api/community/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  uploadTenders: (files: FileList) => {
    const formData = new FormData()
    Array.from(files).forEach((file) => formData.append('files', file))
    return request<ApiStatusResponse & { results?: { evidence_card_url: string }[] }>(
      '/api/audit/upload-tender',
      { method: 'POST', body: formData },
    )
  },
  scanFolder: () =>
    request<ApiStatusResponse>('/api/audit/scan-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }),
  clearHistory: () =>
    request<ApiStatusResponse>('/api/audit/clear-data', { method: 'POST' }),
}
