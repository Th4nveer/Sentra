export interface AuditSummary {
  tender_id: string
  fraud_risk_score: number
  physical_alteration_score: number
  classification: string
}

export interface GeocodingInfo {
  latitude: number
  longitude: number
  formatted_address: string
}

export interface AuditRecord {
  tender_id: string
  project_name: string
  source: 'citizen' | 'tender'
  geocoding: GeocodingInfo
  audit: AuditSummary
  verdict_label: string
  evidence_card_url: string
}

export interface DashboardStats {
  total_audited: number
  flagged_count: number
  verified_count: number
  pending_count: number
}

export interface ApiStatusResponse {
  status: string
  message?: string
  verdict?: string
  evidence_card_url?: string
  detail?: string
}
