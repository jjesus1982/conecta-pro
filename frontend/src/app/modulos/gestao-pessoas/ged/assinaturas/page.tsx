'use client';

import { useState, useEffect, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  PenTool,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Send,
  Loader2,
  Eye,
  FileText,
  RefreshCw,
  User,
  Calendar,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';

const API_BASE = '/api/v1/ged';

function getAuthHeaders() {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface SignatureStats {
  total_signatures: number;
  pending: number;
  signed: number;
  refused: number;
  expired: number;
  avg_time_to_sign_hours: number;
}

interface Signature {
  id: string;
  document_id: string;
  document_title?: string;
  signer_name: string;
  signer_email: string;
  signer_role?: string;
  status: string;
  signature_type?: string;
  order_number?: number;
  signed_at?: string;
  refused_at?: string;
  refusal_reason?: string;
  expires_at?: string;
  created_at: string;
  created_by_name?: string;
}

const statusConfig: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  pendente: { label: 'Pendente', color: 'bg-amber-500/10 text-amber-500 border border-amber-500/30', icon: Clock },
  assinado: { label: 'Assinado', color: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30', icon: CheckCircle2 },
  recusado: { label: 'Recusado', color: 'bg-red-500/10 text-red-500 border border-red-500/30', icon: XCircle },
  expirado: { label: 'Expirado', color: 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30', icon: AlertTriangle },
  cancelado: { label: 'Cancelado', color: 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30', icon: XCircle },
};

function getUrgencyBadge(expiresAt?: string) {
  if (!expiresAt) return null;
  const diff = new Date(expiresAt).getTime() - Date.now();
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
  if (days < 0) return <Badge className="bg-red-500/10 text-red-500 border border-red-500/30 text-xs">Vencido</Badge>;
  if (days === 0) return <Badge className="bg-red-500/10 text-red-500 border border-red-500/30 text-xs">Vence hoje</Badge>;
  if (days === 1) return <Badge className="bg-orange-500/10 text-orange-500 border border-orange-500/30 text-xs">Vence amanha</Badge>;
  if (days <= 7) return <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30 text-xs">Vence em {days}d</Badge>;
  return null;
}

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

export default function AssinaturasPage() {
  const [stats, setStats] = useState<SignatureStats | null>(null);
  const [pending, setPending] = useState<Signature[]>([]);
  const [sent, setSent] = useState<Signature[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Modal state
  const [signModal, setSignModal] = useState(false);
  const [refuseModal, setRefuseModal] = useState(false);
  const [selectedSig, setSelectedSig] = useState<Signature | null>(null);
  const [refusalReason, setRefusalReason] = useState('');
  const [observation, setObservation] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [statsRes, pendingRes, sentRes] = await Promise.all([
        fetch(`${API_BASE}/document-signatures/stats/summary`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/document-signatures/signer/pending`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/document-signatures/signer/list`, { headers: getAuthHeaders() }),
      ]);

      if (statsRes.ok) {
        setStats(await statsRes.json());
      }
      if (pendingRes.ok) {
        const data = await pendingRes.json();
        setPending(Array.isArray(data) ? data : data.items || []);
      }
      if (sentRes.ok) {
        const data = await sentRes.json();
        setSent(Array.isArray(data) ? data : data.items || []);
      }
    } catch (err) {
      console.error('loadData:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleSign = async () => {
    if (!selectedSig) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/document-signatures/${selectedSig.id}/sign`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          observation: observation || undefined,
          ip_address: '0.0.0.0',
        }),
      });
      if (res.ok) {
        setSignModal(false);
        setSelectedSig(null);
        setObservation('');
        showToast('Documento assinado com sucesso!');
        loadData();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(msgFromDetail(data.detail) || 'Erro ao assinar documento', 'error');
      }
    } catch (err) {
      console.error('handleSign:', err);
      showToast('Erro de conexao ao assinar', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefuse = async () => {
    if (!selectedSig || !refusalReason) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/document-signatures/${selectedSig.id}/refuse`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason: refusalReason }),
      });
      if (res.ok) {
        setRefuseModal(false);
        setSelectedSig(null);
        setRefusalReason('');
        showToast('Assinatura recusada');
        loadData();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(msgFromDetail(data.detail) || 'Erro ao recusar assinatura', 'error');
      }
    } catch (err) {
      console.error('handleRefuse:', err);
      showToast('Erro de conexao ao recusar', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const openSign = (sig: Signature) => {
    setSelectedSig(sig);
    setObservation('');
    setSignModal(true);
  };

  const openRefuse = (sig: Signature) => {
    setSelectedSig(sig);
    setRefusalReason('');
    setRefuseModal(true);
  };

  const signedList = sent.filter((s) => s.status === 'assinado');
  const refusedList = sent.filter((s) => s.status === 'recusado');
  const completedList = [...signedList, ...refusedList].sort(
    (a, b) => new Date(b.signed_at || b.refused_at || b.created_at).getTime() -
              new Date(a.signed_at || a.refused_at || a.created_at).getTime()
  );

  const renderSignatureRow = (sig: Signature, showActions = false) => {
    const cfg = statusConfig[sig.status] ?? statusConfig.pendente!;
    const StatusIcon = cfg!.icon;
    return (
      <tr key={sig.id} className="border-b last:border-0 hover:bg-muted/50">
        <td className="p-3">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <div>
              <p className="font-medium text-sm">{sig.document_title || `Doc ${sig.document_id?.slice(0, 8)}`}</p>
              {sig.created_by_name && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <User className="h-3 w-3" /> {sig.created_by_name}
                </p>
              )}
            </div>
          </div>
        </td>
        <td className="p-3">
          <div className="text-sm">
            <p>{sig.signer_name}</p>
            <p className="text-xs text-muted-foreground">{sig.signer_email}</p>
          </div>
        </td>
        <td className="p-3">
          <div className="flex items-center gap-1.5">
            <Badge className={`${cfg.color} text-xs`}>
              <StatusIcon className="h-3 w-3 mr-1" />
              {cfg.label}
            </Badge>
            {sig.status === 'pendente' && getUrgencyBadge(sig.expires_at)}
          </div>
        </td>
        <td className="p-3 text-sm text-muted-foreground">
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {new Date(sig.created_at).toLocaleDateString('pt-BR')}
          </div>
        </td>
        <td className="p-3">
          {showActions && sig.status === 'pendente' && (
            <div className="flex items-center gap-1">
              <Button size="sm" className="h-7 text-xs" onClick={() => openSign(sig)}>
                <PenTool className="h-3 w-3 mr-1" />
                Assinar
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openRefuse(sig)}>
                <XCircle className="h-3 w-3 mr-1" />
                Recusar
              </Button>
            </div>
          )}
          {sig.status === 'assinado' && sig.signed_at && (
            <span className="text-xs text-emerald-500">
              {new Date(sig.signed_at).toLocaleDateString('pt-BR')}
            </span>
          )}
          {sig.status === 'recusado' && (
            <span className="text-xs text-red-500 truncate max-w-[150px] block">
              {sig.refusal_reason || 'Recusado'}
            </span>
          )}
        </td>
      </tr>
    );
  };

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
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <PenTool className="h-6 w-6" />
            Assinaturas Digitais
          </h1>
          <p className="text-muted-foreground">Gerencie solicitacoes e assinaturas de documentos</p>
        </div>
        <div className="flex items-center gap-2">
          {stats && stats.pending > 0 && (
            <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/30">
              {stats.pending} pendente{stats.pending > 1 ? 's' : ''}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`h-4 w-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendentes</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-amber-500">{stats?.pending ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Assinados</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-emerald-500">{stats?.signed ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Recusados</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-500">{stats?.refused ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tempo Medio</CardTitle>
            <PenTool className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">
              {stats?.avg_time_to_sign_hours
                ? `${Math.round(stats.avg_time_to_sign_hours)}h`
                : '-'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="pending" className="space-y-4">
        <TabsList>
          <TabsTrigger value="pending" className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            Aguardando ({pending.length})
          </TabsTrigger>
          <TabsTrigger value="sent" className="flex items-center gap-1.5">
            <Send className="h-3.5 w-3.5" />
            Todos ({sent.length})
          </TabsTrigger>
          <TabsTrigger value="completed" className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Concluidos ({completedList.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab: Pending */}
        <TabsContent value="pending">
          <Card>
            <CardContent className="p-0">
              {pending.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <CheckCircle2 className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhuma assinatura pendente</p>
                  <p className="text-sm mt-1">Voce esta em dia!</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium text-muted-foreground">Documento</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Signatario</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Ações</th>
                    </tr>
                  </thead>
                  <tbody>{pending.map((sig) => renderSignatureRow(sig, true))}</tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: All Sent */}
        <TabsContent value="sent">
          <Card>
            <CardContent className="p-0">
              {sent.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Send className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhuma assinatura encontrada</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium text-muted-foreground">Documento</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Signatario</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Acao</th>
                    </tr>
                  </thead>
                  <tbody>{sent.map((sig) => renderSignatureRow(sig, true))}</tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: Completed */}
        <TabsContent value="completed">
          <Card>
            <CardContent className="p-0">
              {completedList.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <CheckCircle2 className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p className="font-medium">Nenhuma assinatura concluida</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium text-muted-foreground">Documento</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Signatario</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Detalhe</th>
                    </tr>
                  </thead>
                  <tbody>{completedList.map((sig) => renderSignatureRow(sig, false))}</tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Modal: Assinar */}
      <Dialog open={signModal} onOpenChange={(open) => { if (!open) { setSignModal(false); setSelectedSig(null); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PenTool className="h-5 w-5" />
              Confirmar Assinatura
            </DialogTitle>
          </DialogHeader>
          {selectedSig && (
            <div className="space-y-4 py-2">
              <div className="bg-muted/50 rounded-lg p-3 space-y-1">
                <p className="text-sm font-medium">
                  {selectedSig.document_title || `Documento ${selectedSig.document_id?.slice(0, 8)}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  Solicitado em {new Date(selectedSig.created_at).toLocaleDateString('pt-BR')}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="obs">Observacao (opcional)</Label>
                <Input
                  id="obs"
                  value={observation}
                  onChange={(e) => setObservation(e.target.value)}
                  placeholder="Adicione uma observacao..."
                />
              </div>
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                <p className="text-xs text-blue-400">
                  Ao confirmar, voce declara ter lido e concordar com o conteudo do documento.
                  Esta acao nao pode ser desfeita.
                </p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSignModal(false)}>Cancelar</Button>
            <Button onClick={handleSign} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <PenTool className="h-4 w-4 mr-2" />}
              Confirmar Assinatura
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Modal: Recusar */}
      <Dialog open={refuseModal} onOpenChange={(open) => { if (!open) { setRefuseModal(false); setSelectedSig(null); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-600" />
              Recusar Assinatura
            </DialogTitle>
          </DialogHeader>
          {selectedSig && (
            <div className="space-y-4 py-2">
              <div className="bg-muted/50 rounded-lg p-3 space-y-1">
                <p className="text-sm font-medium">
                  {selectedSig.document_title || `Documento ${selectedSig.document_id?.slice(0, 8)}`}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reason">Motivo da recusa *</Label>
                <Input
                  id="reason"
                  value={refusalReason}
                  onChange={(e) => setRefusalReason(e.target.value)}
                  placeholder="Informe o motivo..."
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRefuseModal(false)}>Cancelar</Button>
            <Button variant="destructive" onClick={handleRefuse} disabled={actionLoading || !refusalReason}>
              {actionLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <XCircle className="h-4 w-4 mr-2" />}
              Confirmar Recusa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
