'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Loader2, User, FileText, Calendar, ChevronRight, CheckCircle2, XCircle, Circle, Edit, Save, X, Download } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

const STATUS: Record<string, { label: string; color: string }> = {
  documents_pending: { label: 'Documentos Pendentes', color: 'bg-yellow-500 text-white' },
  medical_exam: { label: 'Exame Médico', color: 'bg-blue-500 text-white' },
  contract_signing: { label: 'Assinatura de Contrato', color: 'bg-orange-500 text-white' },
  completed: { label: 'Concluída', color: 'bg-green-500 text-white' },
  cancelled: { label: 'Cancelada', color: 'bg-red-500 text-white' },
};

function fmtDate(d: unknown): string {
  if (!d) return '-';
  const s = String(d);
  const p = s.split('-');
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : s;
}

export default function AdmissaoDetalhePage() {
  const params = useParams();
  const router = useRouter();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [showExamModal, setShowExamModal] = useState(false);
  const [examData, setExamData] = useState({ date: new Date().toISOString().slice(0, 10), result: 'apto' });
  const [showCompleteModal, setShowCompleteModal] = useState(false);
  const [completeData, setCompleteData] = useState({ actual_start_date: '' });
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({ candidate_name: '', cpf: '', position: '', department: '', salary_proposed: '', notes: '' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [generatingEsocial, setGeneratingEsocial] = useState(false);

  const handleGerarS2200 = async () => {
    if (!data) return;
    setGeneratingEsocial(true);
    try {
      const payload = {
        cpf: String(data.cpf || '').replace(/\D/g, ''),
        nome: String(data.candidate_name || ''),
        data_nascimento: data.data_nascimento ? String(data.data_nascimento) : null,
        sexo: data.sexo ? String(data.sexo) : 'M',
        data_admissao: String(data.actual_start_date || data.expected_start_date || ''),
        cargo: String(data.position || ''),
        salario: Number(data.salary_proposed || 0),
        matricula: String(data.employee_id || data.id || '').slice(0, 20),
        cbo: '',
        categoria: '101',
        tipo_contrato: '1',
      };
      if (!payload.cpf || !payload.nome || !payload.data_admissao || !payload.salario) {
        toast.error('Dados insuficientes para gerar S-2200 (CPF, nome, data de admissão e salário são obrigatórios)', { duration: 5000 });
        setGeneratingEsocial(false);
        return;
      }
      const res = await fetch(`${API_BASE}/esocial/s2200/gerar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `S2200_${payload.matricula}.xml`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        toast.success('XML S-2200 gerado e baixado com sucesso!', { duration: 4000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao gerar S-2200', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao gerar S-2200', { duration: 5000 });
    } finally {
      setGeneratingEsocial(false);
    }
  };

  const loadData = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/admissions/${params.id}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setEditData({
          candidate_name: String(json.candidate_name || ''),
          cpf: String(json.cpf || ''),
          position: String(json.position || ''),
          department: String(json.department || ''),
          salary_proposed: json.salary_proposed ? String(json.salary_proposed) : '',
          notes: String(json.notes || ''),
        });
      }
    } catch { /* */ }
    finally { setLoading(false); }
  }, [params.id]);

  useEffect(() => { if (params.id) loadData(); }, [params.id, loadData]);

  const advanceStatus = async (newStatus: string, extraData?: Record<string, string>) => {
    setAdvancing(true);
    try {
      const res = await fetch(`${API_BASE}/admissions/${params.id}`, {
        method: 'PATCH', headers: getAuthHeaders(),
        body: JSON.stringify({ status: newStatus, ...extraData }),
      });
      if (res.ok) { toast.success(`Status atualizado para ${STATUS[newStatus]?.label || newStatus}`, { duration: 4000 }); await loadData(); }
      else { toast.error('Erro ao atualizar status', { duration: 5000 }); }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setAdvancing(false); }
  };

  const handleCancelAdmission = async () => {
    setShowCancelConfirm(false);
    await advanceStatus('cancelled');
  };

  const handleSaveEdit = async () => {
    setSavingEdit(true);
    try {
      const payload: Record<string, unknown> = {};
      if (editData.candidate_name !== String(data?.candidate_name || '')) payload.candidate_name = editData.candidate_name;
      if (editData.cpf !== String(data?.cpf || '')) payload.cpf = editData.cpf;
      if (editData.position !== String(data?.position || '')) payload.position = editData.position;
      if (editData.department !== String(data?.department || '')) payload.department = editData.department;
      if (editData.notes !== String(data?.notes || '')) payload.notes = editData.notes;
      const newSalary = editData.salary_proposed ? parseFloat(editData.salary_proposed) : null;
      const oldSalary = data?.salary_proposed ? Number(data.salary_proposed) : null;
      if (newSalary !== oldSalary) payload.salary_proposed = newSalary;

      if (Object.keys(payload).length === 0) {
        toast.info('Nenhuma alteração detectada', { duration: 3000 });
        setEditing(false);
        setSavingEdit(false);
        return;
      }

      const res = await fetch(`${API_BASE}/admissions/${params.id}`, {
        method: 'PATCH', headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success('Dados atualizados com sucesso!', { duration: 4000 });
        setEditing(false);
        await loadData();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao salvar alterações', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setSavingEdit(false); }
  };

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  if (!data) return <div className="text-center py-20 text-muted-foreground">Admissão não encontrada</div>;

  const st = STATUS[String(data.status)] || { label: String(data.status), color: 'bg-gray-500 text-white' };
  const isEditable = String(data.status) !== 'completed' && String(data.status) !== 'cancelled';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push('/modulos/dp/admissao')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="font-display text-2xl font-semibold">{String(data.candidate_name || 'Candidato')}</h1>
          <p className="text-muted-foreground">Processo de admissão</p>
        </div>
        <Badge className={st.color}>{st.label}</Badge>
        <div className="ml-auto flex gap-2">
          {isEditable && !editing && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Edit className="h-4 w-4 mr-1" /> Editar
            </Button>
          )}
          {isEditable && (
            <Button variant="destructive" size="sm" disabled={advancing} onClick={() => setShowCancelConfirm(true)}>
              <XCircle className="h-4 w-4 mr-1" /> Cancelar Admissão
            </Button>
          )}
          {String(data.status) === 'completed' && (
            <Button variant="outline" size="sm" disabled={generatingEsocial} onClick={handleGerarS2200}>
              {generatingEsocial ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
              {generatingEsocial ? 'Gerando...' : 'Gerar S-2200 eSocial'}
            </Button>
          )}
        </div>
      </div>

      {/* Modal de confirmação de cancelamento */}
      {showCancelConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4 text-gray-900">
            <h3 className="text-lg font-bold mb-2">Confirmar Cancelamento</h3>
            <p className="text-sm text-gray-600 mb-4">
              Tem certeza que deseja cancelar a admissão de <strong>{String(data.candidate_name)}</strong>?
              Esta ação não pode ser desfeita.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setShowCancelConfirm(false)}>Não, manter</Button>
              <Button variant="destructive" size="sm" onClick={handleCancelAdmission}>
                Sim, cancelar admissão
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Workflow Buttons */}
      {isEditable && !editing && (
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-medium text-muted-foreground">Avançar para:</span>
              {String(data.status) === 'documents_pending' && (
                <Button size="sm" disabled={advancing} onClick={() => advanceStatus('medical_exam')}>
                  <ChevronRight className="h-4 w-4 mr-1" /> Exame Médico
                </Button>
              )}
              {String(data.status) === 'medical_exam' && (
                <Button size="sm" disabled={advancing} onClick={() => {
                  setExamData({ date: new Date().toISOString().slice(0, 10), result: 'apto' });
                  setShowExamModal(true);
                }}>
                  <ChevronRight className="h-4 w-4 mr-1" /> Assinatura Contrato
                </Button>
              )}
              {String(data.status) === 'contract_signing' && (
                <Button size="sm" disabled={advancing} onClick={() => {
                  setCompleteData({ actual_start_date: String(data.expected_start_date || new Date().toISOString().slice(0, 10)) });
                  setShowCompleteModal(true);
                }}>
                  <CheckCircle2 className="h-4 w-4 mr-1" /> Concluir Admissão
                </Button>
              )}
              {advancing && <Loader2 className="h-4 w-4 animate-spin" />}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal Exame Médico */}
      {showExamModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4 text-gray-900">
            <h3 className="text-lg font-bold mb-4">Dados do Exame Médico (ASO)</h3>
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium mb-1 block">Data do Exame *</label>
                <input type="date" value={examData.date} onChange={e => setExamData(p => ({ ...p, date: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Resultado *</label>
                <select value={examData.result} onChange={e => setExamData(p => ({ ...p, result: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm">
                  <option value="apto">Apto</option>
                  <option value="inapto">Inapto</option>
                  <option value="apto_com_restricao">Apto com Restrição</option>
                </select>
              </div>
              {examData.result === 'inapto' && (
                <p className="text-sm text-red-600 bg-red-50 p-2 rounded">
                  Candidato inapto não pode avançar para assinatura de contrato. Considere cancelar a admissão ou reagendar o exame.
                </p>
              )}
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <Button variant="outline" size="sm" onClick={() => setShowExamModal(false)}>Cancelar</Button>
              <Button size="sm" disabled={advancing || examData.result === 'inapto' || !examData.date}
                onClick={async () => {
                  setShowExamModal(false);
                  await advanceStatus('contract_signing', { medical_exam_date: examData.date, medical_exam_result: examData.result });
                }}>
                Confirmar e Avançar
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Concluir Admissão */}
      {showCompleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4 text-gray-900">
            <h3 className="text-lg font-bold mb-4">Concluir Admissão</h3>
            <p className="text-sm text-gray-600 mb-3">
              Ao concluir, o funcionário <strong>{String(data.candidate_name)}</strong> será registrado como colaborador ativo no sistema.
            </p>
            <div>
              <label className="text-sm font-medium mb-1 block">Data de Início Efetivo *</label>
              <input type="date" value={completeData.actual_start_date}
                onChange={e => setCompleteData(p => ({ ...p, actual_start_date: e.target.value }))}
                className="w-full px-3 py-2 border rounded-md text-sm" />
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <Button variant="outline" size="sm" onClick={() => setShowCompleteModal(false)}>Cancelar</Button>
              <Button size="sm" disabled={advancing || !completeData.actual_start_date}
                onClick={async () => {
                  setShowCompleteModal(false);
                  await advanceStatus('completed', { actual_start_date: completeData.actual_start_date });
                }}>
                <CheckCircle2 className="h-4 w-4 mr-1" /> Confirmar Admissão
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Formulário de edição */}
      {editing && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Editar Dados da Admissão</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setEditing(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Nome do Candidato</label>
                <input type="text" value={editData.candidate_name} onChange={e => setEditData(p => ({ ...p, candidate_name: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">CPF</label>
                <input type="text" value={editData.cpf} onChange={e => setEditData(p => ({ ...p, cpf: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" maxLength={14} />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Cargo</label>
                <select value={editData.position} onChange={e => setEditData(p => ({ ...p, position: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                  <option value="">Selecione</option>
                  <option value="Agente de Portaria">Agente de Portaria</option>
                  <option value="Agente de Serviços Gerais">Agente de Serviços Gerais</option>
                  <option value="Vigilante">Vigilante</option>
                  <option value="Líder de Portaria">Líder de Portaria</option>
                  <option value="Artífice">Artífice</option>
                  <option value="Supervisor">Supervisor</option>
                  <option value="Administrativo">Administrativo</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Departamento</label>
                <select value={editData.department} onChange={e => setEditData(p => ({ ...p, department: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                  <option value="">Selecione</option>
                  <option value="Operações">Operações</option>
                  <option value="Administrativo">Administrativo</option>
                  <option value="Comercial">Comercial</option>
                  <option value="Financeiro">Financeiro</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Salário Proposto (R$)</label>
                <input type="number" step="0.01" value={editData.salary_proposed} onChange={e => setEditData(p => ({ ...p, salary_proposed: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <input type="text" value={editData.notes} onChange={e => setEditData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Observações sobre o candidato" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button size="sm" disabled={savingEdit} onClick={handleSaveEdit}>
                {savingEdit ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {savingEdit ? 'Salvando...' : 'Salvar Alterações'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><User className="h-4 w-4" /> Dados do Candidato</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div><span className="text-sm text-muted-foreground">Nome:</span><p className="font-medium">{String(data.candidate_name || '-')}</p></div>
            <div><span className="text-sm text-muted-foreground">CPF:</span><p className="font-medium">{String(data.cpf || '-')}</p></div>
            <div><span className="text-sm text-muted-foreground">Cargo:</span><p className="font-medium">{String(data.position || '-')}</p></div>
            <div><span className="text-sm text-muted-foreground">Departamento:</span><p className="font-medium">{String(data.department || '-')}</p></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><Calendar className="h-4 w-4" /> Informações</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div><span className="text-sm text-muted-foreground">Salário Proposto:</span><p className="font-medium">{data.salary_proposed ? `R$ ${Number(data.salary_proposed).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : '-'}</p></div>
            <div><span className="text-sm text-muted-foreground">Data Prevista:</span><p className="font-medium">{fmtDate(data.expected_start_date)}</p></div>
            <div><span className="text-sm text-muted-foreground">Criado em:</span><p className="font-medium">{data.created_at ? new Date(String(data.created_at)).toLocaleString('pt-BR') : '-'}</p></div>
            {data.medical_exam_date ? <div><span className="text-sm text-muted-foreground">Exame Médico:</span><p className="font-medium">{fmtDate(data.medical_exam_date)} — {String(data.medical_exam_result || '-')}</p></div> : null}
            {data.actual_start_date ? <div><span className="text-sm text-muted-foreground">Data de Início:</span><p className="font-medium">{fmtDate(data.actual_start_date)}</p></div> : null}
            {data.notes ? <div><span className="text-sm text-muted-foreground">Observações:</span><p className="text-sm">{String(data.notes)}</p></div> : null}
          </CardContent>
        </Card>
      </div>

      {data.checklist && typeof data.checklist === 'object' ? (
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-2"><FileText className="h-4 w-4" /> Checklist de Documentos</CardTitle></CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(data.checklist as Record<string, Record<string, boolean>>).map(([cat, items]) => (
                <div key={cat}>
                  <h4 className="font-medium text-sm mb-2 capitalize">{cat.replace(/_/g, ' ')}</h4>
                  <div className="space-y-1">
                    {Object.entries(items).map(([doc, done]) => (
                      <button key={doc} className="flex items-center gap-2 text-sm w-full text-left hover:bg-muted/50 rounded px-1 py-0.5 transition-colors" onClick={async () => {
                        const checklist = { ...(data.checklist as Record<string, Record<string, boolean>>) };
                        checklist[cat] = { ...checklist[cat], [doc]: !done };
                        try {
                          const res = await fetch(`${API_BASE}/admissions/${params.id}`, { method: 'PATCH', headers: getAuthHeaders(), body: JSON.stringify({ checklist }) });
                          if (res.ok) { toast.success(`${doc.replace(/_/g, ' ')} ${!done ? 'marcado' : 'desmarcado'}`, { duration: 3000 }); loadData(); }
                        } catch { /* */ }
                      }}>
                        <span className={done ? 'text-green-600' : 'text-muted-foreground'}>{done ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}</span>
                        <span className={done ? '' : 'text-muted-foreground'}>{doc.replace(/_/g, ' ')}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Upload de Documentos */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><FileText className="h-4 w-4" /> Upload de Documentos</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <select id="doc-type" className="border rounded-md px-3 py-2 text-sm" defaultValue="rg">
                <option value="rg">RG</option>
                <option value="cpf">CPF</option>
                <option value="ctps">CTPS</option>
                <option value="pis_pasep">PIS/PASEP</option>
                <option value="titulo_eleitor">Título Eleitor</option>
                <option value="comprovante_residencia">Comprovante Residência</option>
                <option value="certidao_nascimento_casamento">Certidão Nascimento/Casamento</option>
                <option value="foto_3x4">Foto 3x4</option>
                <option value="curso_vigilante">Curso Vigilante</option>
                <option value="cnv_carteira_nacional_vigilante">CNV</option>
                <option value="certificado_reciclagem">Certificado Reciclagem</option>
                <option value="registro_policia_federal">Registro PF</option>
                <option value="antecedentes_criminais">Antecedentes</option>
                <option value="aso_admissional">ASO Admissional</option>
                <option value="dados_conta_bancaria">Dados Bancários</option>
                <option value="outro">Outro</option>
              </select>
              <input type="file" id="doc-file" className="text-sm" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"  aria-label="File" />
              <Button size="sm" onClick={async () => {
                const fileInput = document.getElementById('doc-file') as HTMLInputElement;
                const typeSelect = document.getElementById('doc-type') as HTMLSelectElement;
                const file = fileInput?.files?.[0];
                if (!file) { toast.error('Selecione um arquivo', { duration: 5000 }); return; }
                const formData = new FormData();
                formData.append('file', file);
                const token = localStorage.getItem('access_token') || localStorage.getItem('token') || '';
                try {
                  const res = await fetch(`${API_BASE}/admissions/${params.id}/documents?document_type=${typeSelect.value}`, {
                    method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: formData,
                  });
                  if (res.ok) { toast.success('Documento enviado com sucesso!', { duration: 4000 }); fileInput.value = ''; loadData(); }
                  else { toast.error('Erro ao enviar documento', { duration: 5000 }); }
                } catch { toast.error('Erro de conexão', { duration: 5000 }); }
              }}>
                Upload
              </Button>
            </div>
            {/* Documentos enviados */}
            {data.documents_received && typeof data.documents_received === 'object' && Object.keys(data.documents_received as Record<string, unknown>).length > 0 ? (
              <div className="border rounded-md p-3 bg-muted/30">
                <p className="text-sm font-medium mb-2">Documentos enviados ({Object.keys(data.documents_received as Record<string, unknown>).length}):</p>
                {Object.entries(data.documents_received as Record<string, Record<string, string>>).map(([type, info]) => (
                  <div key={type} className="flex items-center gap-2 text-sm py-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                    <span className="font-medium">{type.replace(/_/g, ' ')}</span>
                    <span className="text-muted-foreground">— {info?.original_name || info?.filename || 'arquivo'}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Nenhum documento enviado ainda.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
