'use client'

import { useState, useEffect, useCallback } from 'react'
import { msgFromDetail } from '@/lib/string';

const API_PM = '/api/v1/people-management'

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

// ============================================================
// Generic helpers
// ============================================================

interface FetchState<T> {
  data: T
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

function useFetchList<T = any>(url: string, deps: any[] = []): FetchState<T[]> {
  const [data, setData] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(url, { headers: getAuthHeaders() })
      if (res.ok) {
        const json = await res.json()
        setData(json.items || json || [])
      } else {
        setError(`Erro ${res.status}`)
      }
    } catch {
      setError('Erro de conexão')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  useEffect(() => { load() }, [load, ...deps])

  return { data, loading, error, refresh: load }
}

function useFetchOne<T = any>(url: string): FetchState<T | null> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(url, { headers: getAuthHeaders() })
      if (res.ok) setData(await res.json())
      else setError(`Erro ${res.status}`)
    } catch {
      setError('Erro de conexão')
    } finally {
      setLoading(false)
    }
  }, [url])

  useEffect(() => { load() }, [load])

  return { data, loading, error, refresh: load }
}

interface MutationState<T = any> {
  mutate: (payload: any) => Promise<T | null>
  loading: boolean
  error: string | null
  data: T | null
}

function useMutation<T = any>(url: string, method: string = 'POST'): MutationState<T> {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<T | null>(null)

  const mutate = useCallback(async (payload: any): Promise<T | null> => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(url, {
        method,
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const result = await res.json()
        setData(result)
        return result
      } else {
        const err = await res.json().catch(() => ({ detail: `Erro ${res.status}` }))
        setError(msgFromDetail(err.detail) || `Erro ${res.status}`)
        return null
      }
    } catch {
      setError('Erro de conexão')
      return null
    } finally {
      setLoading(false)
    }
  }, [url, method])

  return { mutate, loading, error, data }
}

// ============================================================
// DP Hooks (Departamento Pessoal)
// ============================================================

export function useAdmissions(status?: string) {
  const qs = status && status !== 'todos' ? `?status=${status}&limit=50` : '?limit=50'
  return useFetchList(`${API_PM}/hr/admissions${qs}`, [status])
}

export function useTerminations() {
  return useFetchList(`${API_PM}/hr/terminations?limit=50`)
}

export function useBenefits(employeeId?: number) {
  return useFetchList(
    employeeId ? `${API_PM}/hr/benefits/employee/${employeeId}` : `${API_PM}/hr/benefits/?limit=50`,
  )
}

export function useContracts(employeeId?: number) {
  return useFetchOne(
    employeeId ? `${API_PM}/hr/contracts/employee/${employeeId}/current` : `${API_PM}/hr/contracts/?limit=50`,
  )
}

export function useVacationBalance(employeeId: number) {
  return useFetchOne(`${API_PM}/hr/vacations/employee/${employeeId}/balance`)
}

export function useTimeTracking(employeeId: number) {
  return useFetchList(`${API_PM}/hr/time-tracking/employee/${employeeId}/entries`)
}

export function useLeaves(employeeId: number) {
  return useFetchList(`${API_PM}/hr/discipline/employee/${employeeId}/history`)
}

export function useDPDocuments(employeeId: number) {
  return useFetchOne(`${API_PM}/hr/employees/${employeeId}/profile`)
}

export function usePayrollCalculation(employeeId: number, month?: number, year?: number) {
  const now = new Date()
  const m = month || now.getMonth() + 1
  const y = year || now.getFullYear()
  return useFetchOne(`${API_PM}/hr/payroll/employee/${employeeId}/calculate?month=${m}&year=${y}`)
}

export function useESocialEvents() {
  return useFetchList(`${API_PM}/hr/payroll/esocial/events?limit=50`)
}

// ============================================================
// RH Hooks (Recursos Humanos)
// ============================================================

export function usePerformanceReviews() {
  return useFetchList(`${API_PM}/human-resources/performance/reviews?limit=50`)
}

export function useCareerPlans() {
  return useFetchList(`${API_PM}/human-resources/career/plans?limit=50`)
}

export function useCourses() {
  return useFetchList(`${API_PM}/human-resources/training/courses?limit=50`)
}

export function useTrainings() {
  return useFetchList(`${API_PM}/human-resources/training/?limit=50`)
}

export function useTrainingEnrollments() {
  return useFetchList(`${API_PM}/human-resources/training/enrollments?limit=50`)
}

export function useExpiringCertificates() {
  return useFetchList(`${API_PM}/human-resources/training/certificates/expiring`)
}

export function useClimate() {
  return useFetchOne(`${API_PM}/human-resources/climate`)
}

export function useTurnover() {
  return useFetchOne(`${API_PM}/human-resources/turnover`)
}

export function useOnboarding() {
  return useFetchList(`${API_PM}/human-resources/onboarding`)
}

// ============================================================
// Portal Hooks (Funcionario)
// ============================================================

export function usePortalPayslips(year?: number) {
  const y = year || new Date().getFullYear()
  return useFetchList(`${API_PM}/portal/my-payslips?year=${y}`, [year])
}

export function usePortalMyData() {
  return useFetchOne(`${API_PM}/portal/my-data`)
}

export function usePortalDocuments() {
  return useFetchList(`${API_PM}/portal/my-documents`)
}

export function usePortalSchedules(month?: number, year?: number) {
  const params = new URLSearchParams()
  if (month) params.set('month', String(month))
  if (year) params.set('year', String(year))
  const qs = params.toString() ? `?${params.toString()}` : ''
  return useFetchOne(`${API_PM}/portal/my-schedules${qs}`)
}

export function usePortalVacationBalance() {
  return useFetchOne(`${API_PM}/portal/my-vacations/balance`)
}

export function usePortalVacationRequests() {
  return useFetchList(`${API_PM}/portal/my-vacations/requests`)
}

export function usePortalEnrollments() {
  return useFetchList(`${API_PM}/portal/my-trainings/enrollments`)
}

export function usePortalCertificates() {
  return useFetchList(`${API_PM}/portal/my-trainings/certificates`)
}

export function usePortalNotifications() {
  const state = useFetchList(`${API_PM}/portal/my-notifications`)

  const markAsRead = useCallback(async (id: string | number) => {
    try {
      await fetch(`${API_PM}/portal/my-notifications/${id}/read`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
      })
      state.refresh()
    } catch { /* ignore */ }
  }, [state])

  return { ...state, markAsRead }
}

// ============================================================
// Mutation Hooks (Create/Update)
// ============================================================

export function useCreateAdmission() {
  return useMutation(`${API_PM}/hr/admissions/`)
}

export function useCreatePerformanceReview() {
  return useMutation(`${API_PM}/human-resources/performance/reviews`)
}

export function useUpdatePortalData() {
  return useMutation(`${API_PM}/portal/my-data`, 'PUT')
}

export function useSignDocument() {
  return {
    sign: async (documentId: number, documentType: string = 'other') => {
      const res = await fetch(`${API_PM}/portal/my-documents/${documentId}/sign`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ document_type: documentType }),
      })
      return res.ok ? res.json() : null
    },
  }
}

// ============================================================
// Integration Hook
// ============================================================

export function useIntegrationStatus() {
  return useFetchOne(`${API_PM}/integration/status`)
}
