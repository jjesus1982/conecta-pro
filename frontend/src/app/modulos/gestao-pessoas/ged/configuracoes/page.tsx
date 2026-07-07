'use client';

import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import {
  Loader2,
  HardDrive,
  Mail,
  FileText,
  Clock,
  Save,
  CheckCircle,
  XCircle,
  Pencil,
  ToggleLeft,
  ToggleRight,
  Link,
  Unlink,
  Play,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/ged';
const GDRIVE_BASE = '/api/v1/gdrive';
// gdrive endpoints: gdrive/autorizar · gdrive/status · gdrive/desconectar

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') || localStorage.getItem('token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface DriveConfig {
  connected: boolean;
  folder_id: string;
  email: string | null;
  nome?: string | null;
}

interface EmailTemplate {
  id: string;
  name: string;
  assunto?: string;
  subject?: string;
}

interface DocumentType {
  id: string;
  name: string;
  code: string;
  enabled: boolean;
}

interface ColetaConfig {
  enabled: boolean;
  cron_expr: string;
  timezone: string;
  last_run: string | null;
  last_status: string | null;
}

interface ColetaLog {
  id: string;
  run_at: string;
  run_type: string;
  status: string;
  duration_ms: number | null;
  sync_novos: number;
  kits_assembled: number;
  onvio_matched: number;
  triggered_by: string | null;
  erros: Record<string, unknown>[] | null;
}

export default function ConfiguracoesPage() {
  const [loading, setLoading] = useState(true);
  const [savingSection, setSavingSection] = useState<string | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

  const [driveConfig, setDriveConfig] = useState<DriveConfig>({
    connected: false,
    folder_id: '',
    email: null,
    nome: null,
  });

  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);

  const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);

  const [coleta, setColeta] = useState<ColetaConfig>({
    enabled: true,
    cron_expr: '0 6 21 * *',
    timezone: 'America/Manaus',
    last_run: null,
    last_status: null,
  });
  const [coletaLogs, setColetaLogs] = useState<ColetaLog[]>([]);
  const [runningColeta, setRunningColeta] = useState(false);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Tratar callback OAuth do Google Drive (?gdrive=conectado ou ?gdrive=erro)
  useEffect(() => {
    const gdrive = searchParams.get('gdrive');
    if (!gdrive) return;
    if (gdrive === 'conectado') {
      showToast('Google Drive conectado com sucesso!', 'success');
      fetchConfig();
    } else if (gdrive === 'erro') {
      showToast('Erro ao conectar Google Drive. Tente novamente.', 'error');
    }
    // Limpar o query param da URL sem recarregar a página
    const url = new URL(window.location.href);
    url.searchParams.delete('gdrive');
    router.replace(url.pathname + (url.search || ''));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    fetchConfig();
  }, []);

  async function fetchConfig() {
    setLoading(true);
    try {
      const [driveRes, templatesRes, typesRes] = await Promise.all([
        fetch(`${GDRIVE_BASE}/status`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/config/email-templates`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/config/document-types`, { headers: getAuthHeaders() }),
      ]);

      if (driveRes.ok) {
        const d = await driveRes.json();
        setDriveConfig({
          connected: d.conectado ?? false,
          email: d.email ?? null,
          nome: d.nome ?? null,
          folder_id: d.folder_id ?? '',
        });
      }
      if (templatesRes.ok) {
        const data = await templatesRes.json();
        setEmailTemplates(Array.isArray(data) ? data : data.templates || data.items || []);
      }
      if (typesRes.ok) {
        const data = await typesRes.json();
        setDocumentTypes(Array.isArray(data) ? data : data.tipos || data.types || data.items || []);
      }
      const coletaRes = await fetch(`${API_BASE}/coleta-automatica`, { headers: getAuthHeaders() });
      if (coletaRes.ok) setColeta(await coletaRes.json());
      await fetchColetaHistory();
    } catch (error) {
      console.error('fetchConfig:', error);
      showToast('Erro ao carregar configurações', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function saveDriveConfig() {
    setSavingSection('drive');
    try {
      const res = await fetch(`${GDRIVE_BASE}/status`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (res.ok) showToast('Configuração do Drive salva');
      else showToast(`Erro: ${res.status}`, 'error');
    } catch (error) {
      showToast('Erro de conexão', 'error');
      console.error('saveDriveConfig:', error);
    } finally {
      setSavingSection(null);
    }
  }

  async function handleDriveConnect() {
    try {
      const res = await fetch(`${GDRIVE_BASE}/autorizar`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        const url = data.url_autorizacao || data.auth_url;
        if (url) {
          window.location.href = url;
        } else {
          showToast('URL de autorização não gerada', 'error');
        }
      } else {
        showToast('Erro ao obter URL de autorização', 'error');
      }
    } catch (error) {
      console.error('handleDriveConnect:', error);
      showToast('Erro ao conectar Google Drive', 'error');
    }
  }

  async function handleDriveDisconnect() {
    if (!confirm('Deseja desconectar o Google Drive?')) return;
    try {
      const res = await fetch(`${GDRIVE_BASE}/desconectar`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setDriveConfig({ connected: false, folder_id: '', email: null, nome: null });
        showToast('Google Drive desconectado');
      } else {
        showToast('Erro ao desconectar Google Drive', 'error');
      }
    } catch (error) {
      console.error('handleDriveDisconnect:', error);
      showToast('Erro ao desconectar Google Drive', 'error');
    }
  }

  async function toggleDocumentType(docType: DocumentType) {
    const updated = { ...docType, enabled: !docType.enabled };
    try {
      await fetch(`${API_BASE}/config/document-types/${docType.id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(updated),
      });
      setDocumentTypes((prev) =>
        prev.map((dt) => (dt.id === docType.id ? updated : dt))
      );
    } catch (error) {
      console.error('toggleDocumentType:', error);
      showToast('Erro ao alterar tipo de documento', 'error');
    }
  }

  async function fetchColetaHistory() {
    try {
      const res = await fetch(`${API_BASE}/coleta-automatica/history?limit=10`, { headers: getAuthHeaders() });
      if (res.ok) setColetaLogs(await res.json());
    } catch (e) {
      console.error('fetchColetaHistory:', e);
    }
  }

  async function saveColetaConfig() {
    setSavingSection('coleta');
    try {
      const { croniter } = await import('croniter').catch(() => ({ croniter: null }));
      const res = await fetch(`${API_BASE}/coleta-automatica`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ enabled: coleta.enabled, cron_expr: coleta.cron_expr }),
      });
      if (res.ok) showToast('Configuração salva com sucesso');
      else showToast(`Erro ao salvar: ${res.status}`, 'error');
    } catch (error) {
      showToast('Erro de conexão', 'error');
      console.error('saveColetaConfig:', error);
    } finally {
      setSavingSection(null);
    }
  }

  async function runColetaAgora() {
    if (runningColeta) return;
    setRunningColeta(true);
    try {
      const res = await fetch(`${API_BASE}/coleta-automatica/run`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({}),
      });
      if (res.status === 202) {
        showToast('Coleta iniciada! Aguarde os resultados...');
        // Poll history a cada 3s até novo log aparecer
        const before = coletaLogs.length;
        let attempts = 0;
        pollRef.current = setInterval(async () => {
          attempts++;
          await fetchColetaHistory();
          setColetaLogs((logs) => {
            if (logs.length > before || attempts > 20) {
              if (pollRef.current) clearInterval(pollRef.current);
              setRunningColeta(false);
            }
            return logs;
          });
        }, 3000);
      } else if (res.status === 409) {
        showToast('Coleta já em execução. Aguarde.', 'error');
        setRunningColeta(false);
      } else {
        showToast(`Erro: ${res.status}`, 'error');
        setRunningColeta(false);
      }
    } catch (error) {
      showToast('Erro de conexão', 'error');
      console.error('runColetaAgora:', error);
      setRunningColeta(false);
    }
  }

  function formatDuration(ms: number | null) {
    if (!ms) return '—';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  function statusBadge(status: string) {
    const map: Record<string, string> = {
      success: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30',
      partial: 'bg-amber-500/10 text-amber-500 border border-amber-500/30',
      error: 'bg-red-500/10 text-red-500 border border-red-500/30',
      running: 'bg-blue-500/10 text-blue-500 border border-blue-500/30',
    };
    return `inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[status] ?? 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30'}`;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-[hsl(var(--muted-foreground))]" />
        <span className="ml-2 text-[hsl(var(--muted-foreground))]">Carregando configuracoes...</span>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Configurações GED</h1>
        <p className="text-[hsl(var(--muted-foreground))] mt-1">Gerencie integracoes, templates e preferencias</p>
      </div>

      {/* Google Drive */}
      <Card className="border border-[hsl(var(--border))]">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <HardDrive className="h-5 w-5 text-emerald-500" />
            </div>
            <div className="flex-1">
              <CardTitle className="text-base font-semibold">Google Drive</CardTitle>
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Integracao para envio automatico de kits</p>
            </div>
            {driveConfig.connected ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">
                <CheckCircle className="h-3 w-3" />
                Conectado
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30">
                <XCircle className="h-3 w-3" />
                Desconectado
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">ID da Pasta</label>
            <input
              type="text"
              value={driveConfig.folder_id}
              onChange={(e) => setDriveConfig({ ...driveConfig, folder_id: e.target.value })}
              className="w-full px-3 py-2 bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              placeholder="ID da pasta no Google Drive"
            />
          </div>
          {driveConfig.connected && (driveConfig.email || driveConfig.nome) && (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              Conectado como: {driveConfig.nome || driveConfig.email}
            </p>
          )}
          <div className="flex gap-2">
            {driveConfig.connected ? (
              <button
                onClick={handleDriveDisconnect}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-500 bg-[hsl(var(--card))] border border-red-500/30 rounded-lg hover:bg-red-500/10 transition-colors"
              >
                <Unlink className="h-4 w-4" />
                Desconectar
              </button>
            ) : (
              <button
                onClick={handleDriveConnect}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors"
              >
                <Link className="h-4 w-4" />
                Conectar Google Drive
              </button>
            )}
            <button
              onClick={saveDriveConfig}
              disabled={savingSection === 'drive'}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {savingSection === 'drive' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Salvar
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Email Templates */}
      <Card className="border border-[hsl(var(--border))]">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <Mail className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold">Templates de Email</CardTitle>
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Modelos de email para envio de kits</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {emailTemplates.length === 0 ? (
            <p className="text-sm text-[hsl(var(--muted-foreground))] py-4 text-center">Nenhum template cadastrado</p>
          ) : (
            <div className="space-y-2">
              {emailTemplates.map((template) => (
                <div
                  key={template.id}
                  className="flex items-center justify-between p-3 bg-[hsl(var(--secondary))] rounded-lg"
                >
                  <div>
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">{template.name}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Assunto: {template.assunto || template.subject || '—'}</p>
                  </div>
                  <button
                    className="p-1.5 rounded hover:bg-[hsl(var(--secondary))] transition-colors"
                    title="Editar template"
                  >
                    <Pencil className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Document Types */}
      <Card className="border border-[hsl(var(--border))]">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/10 rounded-lg">
              <FileText className="h-5 w-5 text-amber-500" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold">Tipos de Documento</CardTitle>
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Ative ou desative tipos de documentos nos kits</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {documentTypes.length === 0 ? (
            <p className="text-sm text-[hsl(var(--muted-foreground))] py-4 text-center">Nenhum tipo de documento cadastrado</p>
          ) : (
            <div className="space-y-2">
              {documentTypes.map((docType) => (
                <div
                  key={docType.id}
                  className="flex items-center justify-between p-3 bg-[hsl(var(--secondary))] rounded-lg"
                >
                  <div>
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">{docType.name}</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono">{docType.code}</p>
                  </div>
                  <button
                    onClick={() => toggleDocumentType(docType)}
                    className="focus:outline-none"
                    title={docType.enabled ? 'Desativar' : 'Ativar'}
                  >
                    {docType.enabled ? (
                      <ToggleRight className="h-7 w-7 text-blue-500" />
                    ) : (
                      <ToggleLeft className="h-7 w-7 text-[hsl(var(--muted-foreground))]" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Coleta Automatica — D4 */}
      <Card className="border border-[hsl(var(--border))]">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Clock className="h-5 w-5 text-purple-500" />
            </div>
            <div className="flex-1">
              <CardTitle className="text-base font-semibold">Coleta Automatica</CardTitle>
              <p className="text-sm text-[hsl(var(--muted-foreground))]">
                Sync Onvio + montagem de kits + matching. Padrao: dia 21 as 06h (Manaus).
              </p>
            </div>
            <button
              onClick={() => setColeta({ ...coleta, enabled: !coleta.enabled })}
              className="focus:outline-none"
              title={coleta.enabled ? 'Desativar agendamento' : 'Ativar agendamento'}
            >
              {coleta.enabled ? (
                <ToggleRight className="h-7 w-7 text-blue-500" />
              ) : (
                <ToggleLeft className="h-7 w-7 text-[hsl(var(--muted-foreground))]" />
              )}
            </button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Config cron */}
          <div>
            <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">Expressao Cron</label>
            <input
              type="text"
              value={coleta.cron_expr}
              onChange={(e) => setColeta({ ...coleta, cron_expr: e.target.value })}
              className="w-full px-3 py-2 bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              placeholder="0 6 21 * *"
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
              Formato: min hora dia-do-mes mes dia-da-semana · Timezone: {coleta.timezone}
            </p>
          </div>

          {/* Status e ultima execucao */}
          <div className="flex items-center gap-4 text-xs text-[hsl(var(--muted-foreground))]">
            {coleta.last_run && (
              <span>Ultima execucao: {new Date(coleta.last_run).toLocaleString('pt-BR')}</span>
            )}
            {coleta.last_status && (
              <span className={statusBadge(coleta.last_status)}>{coleta.last_status}</span>
            )}
          </div>

          {/* Botoes */}
          <div className="flex gap-2">
            <button
              onClick={saveColetaConfig}
              disabled={savingSection === 'coleta'}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {savingSection === 'coleta' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Salvar
            </button>
            <button
              onClick={runColetaAgora}
              disabled={runningColeta}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-orange-500 rounded-lg hover:bg-orange-600 disabled:opacity-50 transition-colors"
              title="Dispara sync + auto-assemble agora"
            >
              {runningColeta ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {runningColeta ? 'Em execucao...' : 'Executar agora'}
            </button>
            <button
              onClick={fetchColetaHistory}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-[hsl(var(--muted-foreground))] bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg hover:bg-[hsl(var(--secondary))] transition-colors"
              title="Atualizar historico"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          {/* Historico */}
          {coletaLogs.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] mb-2 uppercase tracking-wider">
                Historico (ultimas {coletaLogs.length})
              </p>
              <div className="space-y-1">
                {coletaLogs.map((log) => (
                  <div key={log.id} className="border border-[hsl(var(--border))] rounded-lg">
                    <button
                      className="w-full flex items-center gap-3 p-2.5 text-left hover:bg-[hsl(var(--secondary))] transition-colors rounded-lg"
                      onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                    >
                      <span className={statusBadge(log.status)}>{log.status}</span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))] flex-1">
                        {new Date(log.run_at).toLocaleString('pt-BR', { timeZone: 'America/Manaus' })}
                      </span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))] font-mono">{log.run_type}</span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))]">{formatDuration(log.duration_ms)}</span>
                      {expandedLog === log.id ? (
                        <ChevronUp className="h-3 w-3 text-[hsl(var(--muted-foreground))]" />
                      ) : (
                        <ChevronDown className="h-3 w-3 text-[hsl(var(--muted-foreground))]" />
                      )}
                    </button>
                    {expandedLog === log.id && (
                      <div className="px-3 pb-3 text-xs text-[hsl(var(--muted-foreground))] space-y-1 border-t border-[hsl(var(--border))] pt-2">
                        <div className="flex gap-4">
                          <span>Sync novos: <strong>{log.sync_novos}</strong></span>
                          <span>Kits montados: <strong>{log.kits_assembled}</strong></span>
                          <span>Onvio casados: <strong>{log.onvio_matched}</strong></span>
                        </div>
                        {log.triggered_by && (
                          <div className="text-[hsl(var(--muted-foreground))]">Por: {log.triggered_by}</div>
                        )}
                        {log.erros && log.erros.length > 0 && (
                          <pre className="bg-red-500/10 text-red-500 p-2 rounded text-xs overflow-x-auto max-h-32">
                            {JSON.stringify(log.erros, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {coletaLogs.length === 0 && !loading && (
            <p className="text-xs text-[hsl(var(--muted-foreground))] text-center py-2">
              Nenhuma execucao registrada. Clique em "Executar agora" para iniciar.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
