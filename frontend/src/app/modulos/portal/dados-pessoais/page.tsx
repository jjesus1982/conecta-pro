'use client'

import { useState, useEffect } from 'react'
import { msgFromDetail } from '@/lib/string';
import { User, Mail, Phone, MapPin, Building, Calendar, Save, Pencil, X, Loader2, AlertCircle } from 'lucide-react'

const API_BASE = '/api/v1/people-management/portal'

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export default function DadosPessoaisPortalPage() {
  const [employee, setEmployee] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [form, setForm] = useState({ telefone: '', email: '', endereco: '', contato_emergencia: '' })

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/my-data`, { headers: getAuthHeaders() })
        if (res.ok) {
          const data = await res.json()
          setEmployee(data)
          setForm({
            telefone: data.telefone || '',
            email: data.email || '',
            endereco: data.endereco || '',
            contato_emergencia: data.contato_emergencia || '',
          })
        }
      } catch { /* fallback */ } finally { setLoading(false) }
    }
    load()
  }, [])

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const updateFields: Record<string, string> = {}
      if (form.telefone !== (employee?.telefone || '')) updateFields.telefone = form.telefone
      if (form.email !== (employee?.email || '')) updateFields.email = form.email
      if (form.endereco !== (employee?.endereco || '')) updateFields.endereco = form.endereco
      if (form.contato_emergencia !== (employee?.contato_emergencia || '')) updateFields.contato_emergencia = form.contato_emergencia

      if (Object.keys(updateFields).length === 0) {
        setEditing(false)
        return
      }

      const res = await fetch(`${API_BASE}/my-data`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(updateFields),
      })
      if (res.ok) {
        const updated = await res.json()
        setEmployee({ ...employee, ...updated })
        setSuccess('Dados atualizados com sucesso!')
        setEditing(false)
        setTimeout(() => setSuccess(null), 3000)
      } else {
        const err = await res.json()
        setError(msgFromDetail(err.detail) || 'Erro ao salvar dados')
      }
    } catch {
      setError('Erro de conexão')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm flex items-center justify-center h-60">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const readOnlyFields = [
    { label: 'Nome', value: employee?.nome, icon: User },
    { label: 'CPF', value: employee?.cpf, icon: User },
    { label: 'Cargo', value: employee?.cargo, icon: Building },
    { label: 'Admissão', value: employee?.data_admissao, icon: Calendar },
  ]

  const editableFields = [
    { key: 'telefone', label: 'Telefone', icon: Phone, placeholder: '(92) 99999-9999' },
    { key: 'email', label: 'Email Pessoal', icon: Mail, placeholder: 'seu@email.com' },
    { key: 'endereco', label: 'Endereço', icon: MapPin, placeholder: 'Rua, número, bairro' },
    { key: 'contato_emergencia', label: 'Contato de Emergência', icon: Phone, placeholder: 'Nome - Telefone' },
  ]

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <User className="w-5 h-5 text-blue-600" />
            Meus Dados Pessoais
          </h2>
          {!editing && (
            <button type="button" onClick={() => setEditing(true)} className="flex items-center gap-1 px-4 py-2 text-sm bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100">
              <Pencil className="w-4 h-4" /> Editar
            </button>
          )}
        </div>

        {success && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">{success}</div>
        )}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        )}

        {!employee ? (
          <p className="text-gray-500 text-center py-8">Não foi possível carregar seus dados</p>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              {readOnlyFields.map((f, i) => {
                const Icon = f.icon
                return (
                  <div key={i} className="flex items-start gap-3">
                    <div className="p-2 bg-gray-100 rounded-lg"><Icon className="w-5 h-5 text-gray-500" /></div>
                    <div>
                      <p className="text-sm text-gray-500">{f.label}</p>
                      <p className="font-medium">{f.value || '—'}</p>
                    </div>
                  </div>
                )
              })}
            </div>

            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">Dados Editáveis</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {editableFields.map((f) => {
                const Icon = f.icon
                return (
                  <div key={f.key} className="flex items-start gap-3">
                    <div className="p-2 bg-gray-100 rounded-lg"><Icon className="w-5 h-5 text-gray-500" /></div>
                    <div className="flex-1">
                      <p className="text-sm text-gray-500 mb-1">{f.label}</p>
                      {editing ? (
                        <input
                          type="text"
                          value={(form as any)[f.key]}
                          onChange={(e) => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                          placeholder={f.placeholder}
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      ) : (
                        <p className="font-medium">{(form as any)[f.key] || '—'}</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {editing && (
              <div className="flex items-center gap-3 mt-6 pt-4 border-t">
                <button type="button" onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm">
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {saving ? 'Salvando...' : 'Salvar Alterações'}
                </button>
                <button type="button" onClick={() => { setEditing(false); setForm({ telefone: employee?.telefone || '', email: employee?.email || '', endereco: employee?.endereco || '', contato_emergencia: employee?.contato_emergencia || '' }) }} className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm">
                  <X className="w-4 h-4" /> Cancelar
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
