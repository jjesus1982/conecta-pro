'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  MessageCircle,
  Send,
  Loader2,
  CheckCircle,
  XCircle,
  Phone,
  FileText,
  AlertTriangle,
  RefreshCw,
  Wifi,
  WifiOff,
  Building2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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

interface WAStatus {
  online: boolean;
  instance: string;
  enabled: boolean;
  details: Record<string, unknown>;
}

interface Certificate {
  id: string;
  tipo: string;
  nome: string;
  razao_social: string;
  dias_para_vencer: number;
  data_validade: string;
  esta_valida: boolean;
}

interface Kit {
  id: string;
  codigo: string;
  nome: string;
  tipo: string;
  status: string;
  total_itens: number;
  is_template?: boolean;
}

interface SendLog {
  type: string;
  phone: string;
  recipient: string;
  status: string;
  sent_at: string;
}

const MONTHS = [
  'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

export default function WhatsAppPage() {
  const now = new Date();
  const [waStatus, setWaStatus] = useState<WAStatus | null>(null);
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [kits, setKits] = useState<Kit[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendLogs, setSendLogs] = useState<SendLog[]>([]);

  // Send kit modal
  const [kitModal, setKitModal] = useState(false);
  const [selectedKit, setSelectedKit] = useState<Kit | null>(null);
  const [kitPhone, setKitPhone] = useState('');
  const [kitClientName, setKitClientName] = useState('');
  const [kitMonth, setKitMonth] = useState(String(now.getMonth() + 1));
  const [kitYear] = useState(String(now.getFullYear()));
  const [sending, setSending] = useState(false);

  // Send cert alert modal
  const [certModal, setCertModal] = useState(false);
  const [selectedCert, setSelectedCert] = useState<Certificate | null>(null);
  const [certPhone, setCertPhone] = useState('');

  // Custom message
  const [customPhone, setCustomPhone] = useState('');
  const [customMessage, setCustomMessage] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [statusRes, certsRes, kitsRes] = await Promise.all([
        fetch('/api/v1/whatsapp/status', { headers: getAuthHeaders() }),
        fetch('/api/v1/bidding/certificates', { headers: getAuthHeaders() }),
        fetch('/api/v1/document-kits', { headers: getAuthHeaders() }),
      ]);

      if (statusRes.ok) setWaStatus(await statusRes.json());
      if (certsRes.ok) {
        const data = await certsRes.json();
        const items = Array.isArray(data) ? data : data.items ?? [];
        setCertificates(items.filter((c: Certificate) => c.dias_para_vencer <= 30));
      }
      if (kitsRes.ok) {
        const data = await kitsRes.json();
        setKits(Array.isArray(data) ? data : data.items ?? []);
      }
    } catch (err) { console.error('loadData:', err); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    loadData();
    try {
      const saved = localStorage.getItem('wa_send_logs');
      if (saved) try { setSendLogs(JSON.parse(saved)); } catch (err) { console.error('parseSendLogs:', err); }
    } catch { /* localStorage indisponível */ }
  }, [loadData]);

  const addLog = (log: SendLog) => {
    const updated = [log, ...sendLogs].slice(0, 50);
    setSendLogs(updated);
    try { localStorage.setItem('wa_send_logs', JSON.stringify(updated)); } catch { /* ignorar */ }
  };

  const handleSendKit = async () => {
    if (!selectedKit) { alert('Selecione um kit'); return; }
    if (!kitPhone || kitPhone.trim().length < 10) { alert('Informe um telefone válido'); return; }
    setSending(true);
    try {
      const res = await fetch('/api/v1/whatsapp/send/kit-notification', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone: kitPhone,
          client_name: kitClientName || 'Cliente',
          month: parseInt(kitMonth),
          year: parseInt(kitYear),
          documents_count: selectedKit.total_itens,
          portal_url: `${window.location.origin}/area-cliente/kit/${selectedKit.id}`,
        }),
      });
      const data = await res.json();
      addLog({
        type: 'Kit Documental',
        phone: kitPhone,
        recipient: kitClientName || 'Cliente',
        status: data.success ? 'enviado' : data.status || 'erro',
        sent_at: new Date().toISOString(),
      });
      if (data.success) { alert('Kit enviado com sucesso!'); }
      else { alert(data.detail || data.message || 'Erro ao enviar'); }
      setKitModal(false);
    } catch (error) { alert('Erro de conexão ao enviar WhatsApp'); console.error(error); }
    finally { setSending(false); }
  };

  const handleSendCertAlert = async () => {
    if (!selectedCert || !certPhone) return;
    setSending(true);
    try {
      const res = await fetch('/api/v1/whatsapp/send/certificate-alert', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone: certPhone,
          client_name: selectedCert.razao_social,
          certificate_type: selectedCert.nome || selectedCert.tipo,
          expiry_date: new Date(selectedCert.data_validade).toLocaleDateString('pt-BR'),
          days_remaining: selectedCert.dias_para_vencer,
        }),
      });
      const data = await res.json();
      addLog({
        type: 'Alerta Certidao',
        phone: certPhone,
        recipient: selectedCert.razao_social,
        status: data.success ? 'enviado' : data.status || 'erro',
        sent_at: new Date().toISOString(),
      });
      setCertModal(false);
      alert('Alerta enviado com sucesso!');
    } catch (err) { console.error('handleSendCertAlert:', err); alert('Erro de conexao ao enviar alerta'); }
    finally { setSending(false); }
  };

  const handleSendCustom = async () => {
    if (!customPhone || customPhone.trim().length < 10) { alert('Informe um telefone válido'); return; }
    if (!customMessage || customMessage.trim() === '') { alert('Digite uma mensagem'); return; }
    setSending(true);
    try {
      const res = await fetch('/api/v1/whatsapp/send/custom', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ phone: customPhone, message: customMessage }),
      });
      const data = await res.json();
      addLog({
        type: 'Mensagem Custom',
        phone: customPhone,
        recipient: customPhone,
        status: data.success ? 'enviado' : data.status || 'erro',
        sent_at: new Date().toISOString(),
      });
      if (data.success) { alert('Mensagem enviada!'); setCustomPhone(''); setCustomMessage(''); }
      else { alert(data.detail || data.message || 'Erro ao enviar'); }
    } catch (error) { alert('Erro de conexão'); console.error(error); }
    finally { setSending(false); }
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
            <MessageCircle className="h-6 w-6 text-green-600" />
            WhatsApp — Evolution API
          </h1>
          <p className="text-muted-foreground">
            Envio de kits, alertas de certidoes e notificacoes via WhatsApp
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className={waStatus?.online ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' : 'bg-red-500/10 text-red-500 border border-red-500/30'}>
            {waStatus?.online ? <Wifi className="h-3 w-3 mr-1" /> : <WifiOff className="h-3 w-3 mr-1" />}
            {waStatus?.online ? 'Online' : waStatus?.enabled ? 'Offline' : 'Desabilitado'}
          </Badge>
          <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadData(); }}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Status card */}
      <Card className={waStatus?.online ? 'border-emerald-500/30' : 'border-amber-500/30'}>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${waStatus?.online ? 'bg-emerald-500/10' : 'bg-amber-500/10'}`}>
              <MessageCircle className={`h-5 w-5 ${waStatus?.online ? 'text-emerald-500' : 'text-amber-500'}`} />
            </div>
            <div>
              <p className="font-medium">
                Instancia: {waStatus?.instance ?? '-'}
              </p>
              <p className="text-sm text-muted-foreground">
                {waStatus?.online
                  ? 'Conectado e pronto para enviar mensagens'
                  : waStatus?.enabled
                    ? 'Evolution API habilitada mas nao conectada — verifique a configuracao'
                    : 'WhatsApp desabilitado nas configuracoes (WHATSAPP_API_ENABLED=false)'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="kits" className="space-y-4">
        <TabsList>
          <TabsTrigger value="kits" className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Kits ({kits.filter(k => k.is_template !== true).length})
          </TabsTrigger>
          <TabsTrigger value="certs" className="flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5" />
            Certidoes ({certificates.length})
          </TabsTrigger>
          <TabsTrigger value="custom" className="flex items-center gap-1.5">
            <Send className="h-3.5 w-3.5" />
            Mensagem Livre
          </TabsTrigger>
          <TabsTrigger value="history" className="flex items-center gap-1.5">
            <CheckCircle className="h-3.5 w-3.5" />
            Historico ({sendLogs.length})
          </TabsTrigger>
        </TabsList>

        {/* Kits */}
        <TabsContent value="kits">
          <Card>
            <CardContent className="p-0">
              {kits.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <FileText className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p>Nenhum kit disponivel</p>
                </div>
              ) : (
                <div className="divide-y">
                  {kits.filter(k => k.status === 'ATIVO').map((kit) => (
                    <div key={kit.id} className="p-4 flex items-center justify-between hover:bg-muted/50">
                      <div>
                        <p className="font-medium">{kit.nome}</p>
                        <p className="text-sm text-muted-foreground">{kit.codigo} — {kit.tipo} — {kit.total_itens} itens</p>
                      </div>
                      <Button size="sm" onClick={() => { setSelectedKit(kit); setKitModal(true); }}>
                        <MessageCircle className="h-3.5 w-3.5 mr-1" />
                        Enviar
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Certidoes */}
        <TabsContent value="certs">
          <Card>
            <CardContent className="p-0">
              {certificates.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p>Nenhuma certidao em alerta</p>
                </div>
              ) : (
                <div className="divide-y">
                  {certificates.map((cert) => (
                    <div key={cert.id} className="p-4 flex items-center justify-between hover:bg-muted/50">
                      <div>
                        <p className="font-medium">{cert.nome || cert.tipo}</p>
                        <p className="text-sm text-muted-foreground">
                          {cert.razao_social} —{' '}
                          <span className={cert.dias_para_vencer <= 7 ? 'text-red-600 font-semibold' : 'text-yellow-600'}>
                            {cert.dias_para_vencer <= 0 ? 'Vencida' : `${cert.dias_para_vencer}d restantes`}
                          </span>
                        </p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => { setSelectedCert(cert); setCertPhone(''); setCertModal(true); }}>
                        <AlertTriangle className="h-3.5 w-3.5 mr-1" />
                        Alertar
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Custom */}
        <TabsContent value="custom">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="space-y-1.5">
                <Label>Telefone (com DDD)</Label>
                <Input value={customPhone} onChange={(e) => setCustomPhone(e.target.value)} placeholder="92 99999-9999" />
              </div>
              <div className="space-y-1.5">
                <Label>Mensagem</Label>
                <textarea
                  value={customMessage}
                  onChange={(e) => setCustomMessage(e.target.value)}
                  placeholder="Digite a mensagem..."
                  rows={5}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <Button onClick={handleSendCustom} disabled={sending || !customPhone || !customMessage}>
                {sending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                Enviar WhatsApp
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* History */}
        <TabsContent value="history">
          <Card>
            <CardContent className="p-0">
              {sendLogs.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <MessageCircle className="h-12 w-12 mx-auto mb-3 opacity-40" />
                  <p>Nenhum envio registrado</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-medium text-muted-foreground">Tipo</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Destinatario</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Telefone</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sendLogs.map((log, i) => (
                      <tr key={i} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="p-3">{log.type}</td>
                        <td className="p-3 text-muted-foreground">{log.recipient}</td>
                        <td className="p-3 font-mono text-xs">{log.phone}</td>
                        <td className="p-3">
                          <Badge className={log.status === 'enviado' ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-500 border border-amber-500/30'}>
                            {log.status === 'enviado' ? <CheckCircle className="h-3 w-3 mr-1" /> : <XCircle className="h-3 w-3 mr-1" />}
                            {log.status}
                          </Badge>
                        </td>
                        <td className="p-3 text-muted-foreground text-xs">{new Date(log.sent_at).toLocaleString('pt-BR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Kit Modal */}
      <Dialog open={kitModal} onOpenChange={setKitModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MessageCircle className="h-5 w-5 text-green-600" />
              Enviar Kit via WhatsApp
            </DialogTitle>
          </DialogHeader>
          {selectedKit && (
            <div className="space-y-4 py-2">
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="font-medium">{selectedKit.nome}</p>
                <p className="text-sm text-muted-foreground">{selectedKit.codigo} — {selectedKit.total_itens} itens</p>
              </div>
              <div className="space-y-1.5">
                <Label>Telefone do cliente (DDD + numero)</Label>
                <Input value={kitPhone} onChange={(e) => setKitPhone(e.target.value)} placeholder="92 99999-9999" />
              </div>
              <div className="space-y-1.5">
                <Label>Nome do cliente</Label>
                <Input value={kitClientName} onChange={(e) => setKitClientName(e.target.value)} placeholder="Nome do condominio" />
              </div>
              <div className="space-y-1.5">
                <Label>Mes referencia</Label>
                <Select value={kitMonth} onValueChange={setKitMonth} aria-label="Kit Month">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MONTHS.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setKitModal(false)}>Cancelar</Button>
            <Button onClick={handleSendKit} disabled={sending || !kitPhone} className="bg-emerald-600 hover:bg-emerald-700">
              {sending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
              Enviar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cert Modal */}
      <Dialog open={certModal} onOpenChange={setCertModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600" />
              Alertar via WhatsApp
            </DialogTitle>
          </DialogHeader>
          {selectedCert && (
            <div className="space-y-4 py-2">
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="font-medium">{selectedCert.nome || selectedCert.tipo}</p>
                <p className="text-sm text-muted-foreground">
                  {selectedCert.razao_social} — {selectedCert.dias_para_vencer <= 0 ? 'Vencida' : `${selectedCert.dias_para_vencer}d`}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label>Telefone do responsavel</Label>
                <Input value={certPhone} onChange={(e) => setCertPhone(e.target.value)} placeholder="92 99999-9999" />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCertModal(false)}>Cancelar</Button>
            <Button onClick={handleSendCertAlert} disabled={sending || !certPhone} variant="destructive">
              {sending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
              Enviar Alerta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
