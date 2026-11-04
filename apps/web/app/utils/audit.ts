import type { AuditRecord } from '../types/api'

export interface AuditFilter {
  action: 'all' | 'ALLOWED' | 'BLOCKED'
  review: 'all' | 'reviewed' | 'unreviewed'
  text: string
}

export function filterAuditRecords(records: AuditRecord[], filter: AuditFilter): AuditRecord[] {
  const q = filter.text.trim().toLowerCase()
  return records.filter((record) => {
    if (filter.action !== 'all' && record.action !== filter.action) {
      return false
    }
    if (filter.review === 'reviewed' && !record.reviewed) {
      return false
    }
    if (filter.review === 'unreviewed' && record.reviewed) {
      return false
    }
    if (q) {
      const hay = `${record.query} ${record.reason ?? ''} ${record.layer ?? ''}`.toLowerCase()
      if (!hay.includes(q)) {
        return false
      }
    }
    return true
  })
}

export function applyReview(record: AuditRecord, label: 0 | 1): AuditRecord {
  return {
    ...record,
    reviewed: true,
    human_label: label
  }
}
