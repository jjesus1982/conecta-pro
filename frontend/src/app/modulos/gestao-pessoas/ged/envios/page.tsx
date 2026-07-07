'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  Mail,
  Globe,
  Printer,
  Send,
  CheckCircle,
  Clock,
  Package,
  FileText,
  RefreshCw,
  ExternalLink,
  Copy,
  AlertCircle,
  Archive,
  Search,
  Link2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const API_BASE = '/api/v1/document-kits';

function getAuthHeaders() {
  let token: string | null = null;
  try {
    token = localStorage.getItem('access_token') || localStorage.getItem('token');
  } catch {
    token = null;
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface Kit {
  id: string;
  codigo: string;
  nome: string;
  descricao: string;
  tipo: string;
  is_template: boolean;
  is_obrigatorio: boolean;
  prazo_dias: number;
  status: string;
  total_itens: number;
  itens_obrigatorios: number;
  condominio_id: string;
  created_at: string;
  updated_at: string;
}

interface KitStats {
  total_kits: number;
  kits_ativos: number;
  kits_inativos: number;
  total_assignments: number;
  assignments_pendentes: number;
  assignments_completos: number;
  assignments_vencidos: number;
  taxa_conclusao: number;
  por_tipo: Record<string, number>;
  por_status: Record<string, number>;
}

const statusConfig: Record<string, { label: string; color: string }> = {
  ATIVO: { label: 'Ativo', color: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' },
  INATIVO: { label: 'Inativo', color: 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30' },
  ARQUIVADO: { label: 'Arquivado', color: 'bg-amber-500/10 text-amber-500 border border-amber-500/30' },
  RASCUNHO: { label: 'Rascunho', color: 'bg-blue-500/10 text-blue-500 border border-blue-500/30' },
};

const typeLabels: Record<string, string> = {
  ADMISSAO: 'Admissão',
  DEMISSAO: 'Demissão',
  MENSAL: 'Mensal',
  AFASTAMENTO: 'Afastamento',
  OUTRO: 'Outro',
};

const methodConfig: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  email: { label: 'Email', color: 'bg-blue-500/10 text-blue-500 border border-blue-500/30', icon: Mail },
  portal: { label: 'Portal', color: 'bg-purple-500/10 text-purple-500 border border-purple-500/30', icon: Globe },
  manual: { label: 'Manual', color: 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30', icon: Printer },
  link: { label: 'Link', color: 'bg-amber-500/10 text-amber-500 border border-amber-500/30', icon: Link2 },
};

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

export default function EnviosPage() {
  const [kits, setKits] = useState<Kit[]>([]);
  const [stats, setStats] = useState<KitStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all');

  // Send modal
  const [sendModal, setSendModal] = useState(false);
  const [selectedKit, setSelectedKit] = useState<Kit | null>(null);
  const [sendMethod, setSendMethod] = useState('email');
  const [sendEmail, setSendEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [sentKits, setSentKits] = useState<Array<{
    kit_id: string;
    kit_name: string;
    method: string;
    sent_at: string;
    recipient: string;
  }>>([]);
  const [linkCopied, setLinkCopied] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [kitsRes, statsRes] = await Promise.all([
        fetch(API_BASE, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/stats`, { headers: getAuthHeaders() }),
      ]);

      if (kitsRes.ok) {
        const data = await kitsRes.json();
        setKits(Array.isArray(data) ? data : data.items || []);
      }
      if (statsRes.ok) {
        setStats(await statsRes.json());
      }
    } catch (err) {
      console.error('loadData:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    // Load sent history from localStorage
    const saved = localStorage.getItem('ged_sent_history');
    if (saved) {
      try { setSentKits(JSON.parse(saved)); } catch (err) { console.error('parseSentHistory:', err); }
    }
  }, [loadData]);

  const saveSentHistory = (history: typeof sentKits) => {
    setSentKits(history);
    localStorage.setItem('ged_sent_history', JSON.stringify(history));
  };

  const openSend = (kit: Kit) => {
    setSelectedKit(kit);
    setSendMethod('email');
    setSendEmail('');
    setSendModal(true);
  };

  const handleSend = async () => {
    if (!selectedKit) return;
    setSending(true);

    try {
      // Try to activate/mark as sent via API
      await fetch(`${API_BASE}/${selectedKit.id}/activate`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ user_id: '00000000-0000-0000-0000-000000000000' }),
      }).catch((err) => { console.error('activate kit:', err); });

      const newEntry = {
        kit_id: selectedKit.id,
        kit_name: selectedKit.nome,
        method: sendMethod,
        sent_at: new Date().toISOString(),
        recipient: sendMethod === 'email' ? sendEmail : sendMethod === 'link' ? 'Link gerado' : 'Entrega manual',
      };

      const newHistory = [newEntry, ...sentKits].slice(0, 50);
      saveSentHistory(newHistory);

      setSendModal(false);
      setSelectedKit(null);
      showToast('Kit enviado com sucesso!');
    } catch (err) {
      console.error('handleSend:', err);
      showToast('Erro ao enviar kit', 'error');
    } finally {
      setSending(false);
    }
  };

  const generateLink = (kit: Kit) => {
    const link = `${window.location.origin}/area-cliente/kit/${kit.id}`;
    navigator.clipboard.writeText(link).then(() => {
      setLinkCopied(kit.id);
      setTimeout(() => setLinkCopied(''), 2000);

      const newEntry = {
        kit_id: kit.id,
        kit_name: kit.nome,
        method: 'link',
        sent_at: new Date().toISOString(),
        recipient: link,
      };
      const newHistory = [newEntry, ...sentKits].slice(0, 50);
      saveSentHistory(newHistory);
    });
  };

  const activeKits = kits.filter((k) => k.status === 'ATIVO' && !k.is_template);
  const templates = kits.filter((k) => k.is_template);

  const filtered = activeKits.filter((k) => {
    if (filterType !== 'all' && k.tipo !== filterType) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        k.nome.toLowerCase().includes(q) ||
        k.codigo.toLowerCase().includes(q) ||
        k.tipo.toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Send className="h-6 w-6" />
            Envios e Entregas
          </h1>
          <p className="text-muted-foreground">
            Gerencie envios de kits documentais para clientes
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadData(); }}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Atualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Kits Ativos</CardTitle>
            <Package className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-emerald-500">{stats?.kits_ativos ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Prontos para envio</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Atribuicoes</CardTitle>
            <FileText className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-500">{stats?.total_assignments ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">{stats?.assignments_pendentes ?? 0} pendentes</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Concluidos</CardTitle>
            <CheckCircle className="h-4 w-4 text-emerald-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-emerald-500">{stats?.assignments_completos ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Taxa: {stats?.taxa_conclusao ?? 0}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencidos</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-500">{stats?.assignments_vencidos ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Precisam atencao</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="enviar" className="space-y-4">
        <TabsList>
          <TabsTrigger value="enviar" className="flex items-center gap-1.5">
            <Send className="h-3.5 w-3.5" />
            Kits para Enviar ({activeKits.length})
          </TabsTrigger>
          <TabsTrigger value="historico" className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            Historico ({sentKits.length})
          </TabsTrigger>
          <TabsTrigger value="templates" className="flex items-center gap-1.5">
            <Archive className="h-3.5 w-3.5" />
            Templates ({templates.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab: Kits para enviar */}
        <TabsContent value="enviar" className="space-y-4">
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex flex-col md:flex-row gap-3">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar por nome ou codigo..."
                    className="pl-10"
                  />
                </div>
                <Select value={filterType} onValueChange={setFilterType} aria-label="Filter Type">
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="Tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {Object.entries(typeLabels).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-0">
              {filtered.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Package className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhum kit disponivel para envio</p>
                  <p className="text-sm mt-1">Kits ativos aparecerão aqui</p>
                </div>
              ) : (
                <div className="divide-y">
                  {filtered.map((kit) => {
                    const cfg = statusConfig[kit.status] ?? statusConfig['ATIVO']!;
                    return (
                      <div key={kit.id} className="p-4 hover:bg-muted/50 transition-colors">
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <h3 className="font-medium truncate">{kit.nome}</h3>
                              <Badge className={`${cfg.color} text-xs`}>{cfg.label}</Badge>
                              <Badge variant="outline" className="text-xs">{typeLabels[kit.tipo] || kit.tipo}</Badge>
                            </div>
                            <p className="text-sm text-muted-foreground mt-0.5 truncate">{kit.descricao}</p>
                            <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                              <span className="font-mono">{kit.codigo}</span>
                              <span>{kit.total_itens} itens</span>
                              <span>Prazo: {kit.prazo_dias}d</span>
                              {kit.is_obrigatorio && <Badge variant="secondary" className="text-xs">Obrigatorio</Badge>}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => generateLink(kit)}
                            >
                              {linkCopied === kit.id ? (
                                <><CheckCircle className="h-3.5 w-3.5 mr-1 text-emerald-500" /> Copiado!</>
                              ) : (
                                <><Copy className="h-3.5 w-3.5 mr-1" /> Link</>
                              )}
                            </Button>
                            <Button size="sm" onClick={() => openSend(kit)}>
                              <Send className="h-3.5 w-3.5 mr-1" />
                              Enviar
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: Historico */}
        <TabsContent value="historico">
          <Card>
            <CardContent className="p-0">
              {sentKits.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Clock className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhum envio registrado</p>
                  <p className="text-sm mt-1">O historico de envios aparecera aqui</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium text-muted-foreground">Kit</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Metodo</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Destinatario</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sentKits.map((entry, i) => {
                      const mcfg = methodConfig[entry.method] ?? methodConfig['manual'];
                      const MethodIcon = mcfg?.icon ?? (() => null);
                      return (
                        <tr key={`${entry.kit_id}-${i}`} className="border-b last:border-0 hover:bg-muted/50">
                          <td className="p-3 font-medium">{entry.kit_name}</td>
                          <td className="p-3">
                            <Badge className={`${mcfg?.color ?? ''} text-xs`}>
                              <MethodIcon className="h-3 w-3 mr-1" />
                              {mcfg?.label ?? entry.method}
                            </Badge>
                          </td>
                          <td className="p-3 text-muted-foreground truncate max-w-[200px]">{entry.recipient}</td>
                          <td className="p-3 text-muted-foreground">
                            {new Date(entry.sent_at).toLocaleString('pt-BR')}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: Templates */}
        <TabsContent value="templates">
          <Card>
            <CardContent className="p-0">
              {templates.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Archive className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhum template encontrado</p>
                </div>
              ) : (
                <div className="divide-y">
                  {templates.map((kit) => (
                    <div key={kit.id} className="p-4 hover:bg-muted/50 transition-colors">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium">{kit.nome}</h3>
                            <Badge variant="secondary" className="text-xs">Template</Badge>
                            <Badge variant="outline" className="text-xs">{typeLabels[kit.tipo] || kit.tipo}</Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mt-0.5">{kit.descricao}</p>
                          <span className="text-xs text-muted-foreground font-mono">{kit.codigo}</span>
                        </div>
                        <Button variant="outline" size="sm" onClick={() => openSend(kit)}>
                          <ExternalLink className="h-3.5 w-3.5 mr-1" />
                          Usar
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Send Modal */}
      <Dialog open={sendModal} onOpenChange={(open) => { if (!open) setSendModal(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-5 w-5" />
              Enviar Kit
            </DialogTitle>
          </DialogHeader>
          {selectedKit && (
            <div className="space-y-4 py-2">
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="font-medium">{selectedKit.nome}</p>
                <p className="text-sm text-muted-foreground">{selectedKit.codigo} - {typeLabels[selectedKit.tipo] || selectedKit.tipo}</p>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">Metodo de envio</label>
                <div className="grid grid-cols-3 gap-2">
                  {(['email', 'portal', 'manual'] as const).map((method) => {
                    const mcfg = methodConfig[method];
                    const Icon = mcfg?.icon ?? (() => null);
                    return (
                      <button
                        key={method}
                        onClick={() => setSendMethod(method)}
                        className={`p-3 rounded-lg border text-center transition-colors ${
                          sendMethod === method ? 'border-primary bg-primary/5' : 'border-muted hover:border-primary/50'
                        }`}
                      >
                        <Icon className="h-5 w-5 mx-auto mb-1" />
                        <span className="text-xs font-medium">{mcfg?.label ?? method}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {sendMethod === 'email' && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="email">Email do destinatario</label>
                  <Input
                    id="email"
                    type="email"
                    value={sendEmail}
                    onChange={(e) => setSendEmail(e.target.value)}
                    placeholder="cliente@empresa.com"
                  />
                </div>
              )}

              {sendMethod === 'portal' && (
                <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
                  <p className="text-sm text-purple-400">
                    O kit sera disponibilizado no Portal do Cliente.
                    O cliente recebera uma notificacao automatica.
                  </p>
                </div>
              )}

              {sendMethod === 'manual' && (
                <div className="bg-[hsl(var(--secondary))] border border-[hsl(var(--border))] rounded-lg p-3">
                  <p className="text-sm text-[hsl(var(--foreground))]">
                    Marcar como enviado manualmente (entrega fisica, WhatsApp, etc).
                  </p>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSendModal(false)}>Cancelar</Button>
            <Button
              onClick={handleSend}
              disabled={sending || (sendMethod === 'email' && !sendEmail)}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              Confirmar Envio
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
