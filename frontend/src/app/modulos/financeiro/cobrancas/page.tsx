'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { CobrancaPreview, CrmClientItem, CrmResumo, AiRecommendation, CollectionAction, CollectionAnalysis, BillingRule, ReceivableAccount } from '@/types/billing';
import Link from 'next/link';
import {
  ArrowLeft,
  FileText,
  Barcode,
  QrCode,
  Copy,
  Download,
  RefreshCw,
  CheckCircle,
  Plus,
  AlertTriangle,
  MessageSquare,
  Handshake,
  Clock,
  Users,
  ExternalLink,
  AlertCircle,
  Bell,
  Settings,
  TrendingDown,
  Phone,
  Mail,
  ChevronDown,
  ChevronUp,
  X,
  CheckCircle2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn, formatCurrency, formatDate } from '@/lib/utils';
import { emitirBoleto, listarBoletos, gerarCobrancaPix } from '@/services/banking/bankingService';
import type { BoletoResponse, BoletoListItem, PixChargeResponse } from '@/services/banking/bankingService';
import { useReceivableDashboard } from '@/hooks/financial/useFinancial';
import { useCondominio } from '@/contexts/CondominioContext';

// ─── Tipos ───────────────────────────────────────────────────────────────────

type TabType = 'emit' | 'list' | 'regua' | 'inadimplentes' | 'recorrente';
type EmitMode = 'boleto' | 'pix';

interface BoletoForm {
  bank_code: string;
  payer_name: string;
  payer_document: string;
  amount: string;
  due_date: string;
  description: string;
}

interface ReguaMomento {
  key: string;
  label: string;
  dias: number; // negativo = antes do vencimento
  enabled: boolean;
  canal: 'whatsapp' | 'email' | 'sms' | 'telefone';
  tom: 'amigavel' | 'profissional' | 'firme' | 'formal';
}

interface ContatoNota {
  inadimplente_id: string;
  texto: string;
  data: string;
}

interface AcordoForm {
  valor: string;
  parcelas: string;
  data_primeiro: string;
}

interface LembreteModal {
  id: string;
  nome: string;
  valor: number;
  dias: number;
}

interface AcordoModal {
  id: string;
  nome: string;
  valor: number;
}

interface ContatoModal {
  id: string;
  nome: string;
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const BANK_COLORS: Record<string, string> = {
  '077': '#00a859', // Inter
};

const BANK_NAMES: Record<string, string> = {
  '077': 'Banco Inter',
};

const INITIAL_BOLETO_FORM: BoletoForm = {
  bank_code: '077',
  payer_name: '',
  payer_document: '',
  amount: '',
  due_date: '',
  description: '',
};

const REGUA_DEFAULT: ReguaMomento[] = [
  { key: 'd-3',  label: 'D-3 (3 dias antes)',      dias: -3,  enabled: true,  canal: 'whatsapp', tom: 'amigavel'     },
  { key: 'd0',   label: 'D0 (dia do vencimento)',   dias:  0,  enabled: true,  canal: 'email',    tom: 'profissional' },
  { key: 'd+1',  label: 'D+1 (1 dia após)',         dias:  1,  enabled: true,  canal: 'whatsapp', tom: 'profissional' },
  { key: 'd+3',  label: 'D+3 (3 dias após)',        dias:  3,  enabled: true,  canal: 'email',    tom: 'firme'        },
  { key: 'd+7',  label: 'D+7 (7 dias após)',        dias:  7,  enabled: false, canal: 'sms',      tom: 'firme'        },
  { key: 'd+15', label: 'D+15 (15 dias após)',      dias: 15,  enabled: false, canal: 'telefone', tom: 'formal'       },
  { key: 'd+30', label: 'D+30 (30 dias após)',      dias: 30,  enabled: false, canal: 'telefone', tom: 'formal'       },
];

const CANAL_ICONS: Record<string, React.ReactNode> = {
  whatsapp:  <MessageSquare className="h-3.5 w-3.5" />,
  email:     <Mail className="h-3.5 w-3.5" />,
  sms:       <Bell className="h-3.5 w-3.5" />,
  telefone:  <Phone className="h-3.5 w-3.5" />,
};

const TOM_PREVIEW: Record<string, Record<string, string>> = {
  amigavel: {
    'd-3':  'Olá {nome}! Passando para lembrar que seu boleto de {valor} vence em 3 dias (dia {venc}). Qualquer dúvida, estamos à disposição!',
    'd0':   'Olá {nome}! Hoje é o dia do vencimento do seu boleto de {valor}. Evite juros pagando ainda hoje!',
    default:'Olá {nome}! Seu compromisso de {valor} precisa da sua atenção.',
  },
  profissional: {
    'd+1':  'Prezado(a) {nome}, identificamos que o boleto de {valor} com vencimento em {venc} ainda não foi quitado. Por favor, regularize para evitar encargos.',
    'd+3':  'Prezado(a) {nome}, o valor de {valor} encontra-se em atraso há 3 dias. Solicitamos a regularização o mais breve possível.',
    default:'Prezado(a) {nome}, seu débito de {valor} requer atenção imediata.',
  },
  firme: {
    'd+7':  '{nome}, o débito de {valor} está em atraso há 7 dias. Acréscimo de juros e multa já foram aplicados. Entre em contato HOJE para evitar medidas adicionais.',
    default:'{nome}, débito de {valor} em atraso. Regularize imediatamente.',
  },
  formal: {
    'd+15': 'Comunicamos ao Sr./Sra. {nome} que o débito no valor de R$ {valor} encontra-se em aberto há {dias} dias, sujeitando-se às penalidades previstas em contrato. Favor entrar em contato em até 48h.',
    'd+30': 'Notificamos o Sr./Sra. {nome} sobre débito de R$ {valor} em atraso há 30 dias. O não pagamento poderá resultar em negativação e cobrança judicial.',
    default:'Notificamos V.Sa. sobre débito de R$ {valor} em aberto.',
  },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function maskDocument(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 14);
  if (digits.length <= 11) {
    return digits
      .replace(/^(\d{3})(\d)/, '$1.$2')
      .replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3-$4');
  }
  return digits
    .replace(/^(\d{2})(\d)/, '$1.$2')
    .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/^(\d{2})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3/$4')
    .replace(/^(\d{2})\.(\d{3})\.(\d{3})\/(\d{4})(\d)/, '$1.$2.$3/$4-$5');
}

function getReguaCor(dias: number): string {
  if (dias < 0)  return 'border-green-500/40 bg-green-500/5';
  if (dias === 0) return 'border-yellow-500/40 bg-yellow-500/5';
  if (dias <= 7)  return 'border-orange-500/40 bg-orange-500/5';
  return 'border-red-500/40 bg-red-500/5';
}

function getReguaDotCor(dias: number): string {
  if (dias < 0)  return 'bg-green-500';
  if (dias === 0) return 'bg-yellow-500';
  if (dias <= 7)  return 'bg-orange-500';
  return 'bg-red-500';
}

function getPreviewMensagem(momento: ReguaMomento): string {
  const tomMap: Record<string, string> = (TOM_PREVIEW[momento.tom] ?? TOM_PREVIEW['amigavel']) as Record<string, string>;
  const texto: string = tomMap[momento.key] ?? tomMap['default'] ?? '';
  return texto
    .replace('{nome}', 'João Silva')
    .replace('{valor}', 'R$ 1.250,00')
    .replace('{venc}', '10/03/2026')
    .replace('{dias}', String(Math.abs(momento.dias)));
}

// ─── Sub-componentes ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    paid:      { label: 'Pago',      cls: 'bg-green-500/15 text-green-600 border-green-500/30'   },
    pago:      { label: 'Pago',      cls: 'bg-green-500/15 text-green-600 border-green-500/30'   },
    pending:   { label: 'Pendente',  cls: 'bg-yellow-500/15 text-yellow-600 border-yellow-500/30'},
    pendente:  { label: 'Pendente',  cls: 'bg-yellow-500/15 text-yellow-600 border-yellow-500/30'},
    overdue:   { label: 'Vencido',   cls: 'bg-red-500/15 text-red-600 border-red-500/30'         },
    vencido:   { label: 'Vencido',   cls: 'bg-red-500/15 text-red-600 border-red-500/30'         },
    cancelled: { label: 'Cancelado', cls: 'bg-gray-500/15 text-gray-500 border-gray-500/30'      },
    cancelado: { label: 'Cancelado', cls: 'bg-gray-500/15 text-gray-500 border-gray-500/30'      },
  };
  const key = status?.toLowerCase() ?? '';
  const entry = map[key] ?? { label: status, cls: 'bg-gray-500/15 text-gray-500 border-gray-500/30' };
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border', entry.cls)}>
      {entry.label}
    </span>
  );
}

function CopyField({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [value]);

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
        {icon}{label}
      </p>
      <div className="flex items-center gap-2">
        <Input readOnly value={value} className="font-mono text-xs bg-muted/30 flex-1 truncate" />
        <Button
          type="button" variant="outline" size="sm" onClick={handleCopy}
          className={cn('shrink-0 transition-colors', copied && 'border-green-500 text-green-600')}
        >
          {copied
            ? <><CheckCircle className="h-3.5 w-3.5 mr-1" />Copiado!</>
            : <><Copy className="h-3.5 w-3.5 mr-1" />Copiar</>
          }
        </Button>
      </div>
    </div>
  );
}

function BankSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">Banco</label>
      <div className="flex gap-3">
        {[{ code: '077', name: 'Inter' }].map((b) => (
          <button
            key={b.code} type="button" onClick={() => onChange(b.code)}
            className={cn(
              'flex-1 flex items-center gap-2 px-4 py-3 rounded-xl border-2 transition-all text-left',
              value === b.code ? 'border-current bg-current/5' : 'border-border hover:border-muted-foreground/40'
            )}
            style={value === b.code ? { color: BANK_COLORS[b.code], borderColor: BANK_COLORS[b.code] } : {}}
          >
            <div
              className="h-8 w-8 rounded-lg flex items-center justify-center text-white text-xs font-bold shrink-0"
              style={{ backgroundColor: BANK_COLORS[b.code] }}
            >
              {b.name[0]}
            </div>
            <div>
              <p className="text-sm font-semibold">{b.name}</p>
              <p className="text-xs text-muted-foreground">Banco {b.code}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Tab 1: Emitir Cobrança ───────────────────────────────────────────────────

function TabEmitir() {
  const [mode, setMode] = useState<EmitMode>('boleto');
  const [form, setForm] = useState<BoletoForm>(INITIAL_BOLETO_FORM);
  const [pixBankCode, setPixBankCode] = useState('077');
  const [isPending, setIsPending] = useState(false);
  const [resultado, setResultado] = useState<BoletoResponse | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pixForm, setPixForm] = useState({ amount: '', description: 'Cobrança Conecta Mais Patrimonial', payer_name: '', payer_document: '', expiracao_horas: 24 });
  const [pixPending, setPixPending] = useState(false);
  const [pixResultado, setPixResultado] = useState<PixChargeResponse | null>(null);
  const [pixError, setPixError] = useState<string | null>(null);

  const setField = useCallback(<K extends keyof BoletoForm>(key: K, val: BoletoForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: val }));
  }, []);

  const validate = (): string | null => {
    if (!form.payer_name.trim()) return 'Nome do pagador é obrigatório.';
    const digits = form.payer_document.replace(/\D/g, '');
    if (digits.length !== 11 && digits.length !== 14) return 'CPF ou CNPJ inválido.';
    const amount = parseFloat(form.amount.replace(',', '.'));
    if (isNaN(amount) || amount <= 0) return 'Informe um valor maior que zero.';
    if (!form.due_date) return 'Data de vencimento é obrigatória.';
    return null;
  };

  const handleEmitir = useCallback(async () => {
    setFormError(null);
    const err = validate();
    if (err) { setFormError(err); return; }
    setIsPending(true);
    try {
      const res = await emitirBoleto({
        bank_code: form.bank_code,
        payer_name: form.payer_name.trim(),
        payer_document: form.payer_document.replace(/\D/g, ''),
        amount: parseFloat(form.amount.replace(',', '.')),
        due_date: form.due_date,
        description: form.description.trim(),
      });
      if (!res.success) {
        setFormError(res.error ?? 'Erro ao emitir boleto. Tente novamente.');
      } else {
        setResultado(res);
      }
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as { message?: string })?.message ??
        'Erro inesperado ao emitir boleto.';
      setFormError(msg);
    } finally {
      setIsPending(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  const handleNovo = useCallback(() => {
    setResultado(null);
    setFormError(null);
    setForm(INITIAL_BOLETO_FORM);
  }, []);

  const handleGerarPix = useCallback(async () => {
    setPixError(null);
    const amount = parseFloat(pixForm.amount.replace(',', '.'));
    if (isNaN(amount) || amount <= 0) { setPixError('Informe um valor maior que zero.'); return; }
    if (!pixForm.description.trim()) { setPixError('Descrição é obrigatória.'); return; }
    setPixPending(true);
    try {
      const res = await gerarCobrancaPix({
        bank_code: pixBankCode,
        amount,
        description: pixForm.description.trim(),
        payer_name: pixForm.payer_name.trim() || undefined,
        payer_document: pixForm.payer_document.replace(/\D/g, '') || undefined,
        chave_pix: '35710481000103',
        expiracao_horas: pixForm.expiracao_horas,
      });
      if (!res.success) {
        setPixError(res.error ?? 'Erro ao gerar QR Code PIX. Tente novamente.');
      } else {
        setPixResultado(res);
      }
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as { message?: string })?.message ??
        'Erro inesperado ao gerar cobrança PIX.';
      setPixError(msg);
    } finally {
      setPixPending(false);
    }
  }, [pixForm, pixBankCode]);

  // ── Resultado de emissão bem-sucedida ──────────────────────────────────────
  if (resultado) {
    return (
      <Card className="border-green-500/30 bg-green-500/5">
        <CardContent className="pt-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-green-500/15 flex items-center justify-center shrink-0">
              <CheckCircle className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-green-700">Boleto Emitido com Sucesso</h2>
              <p className="text-sm text-muted-foreground">{resultado.bank_name} &mdash; {resultado.payer_name}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-background/60 border">
            <div>
              <p className="text-xs text-muted-foreground">Valor</p>
              <p className="text-sm font-semibold">{formatCurrency(resultado.amount)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Vencimento</p>
              <p className="text-sm font-semibold">{formatDate(resultado.due_date)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Banco</p>
              <p className="text-sm font-semibold" style={{ color: BANK_COLORS[resultado.bank_code] }}>
                {resultado.bank_name}
              </p>
            </div>
            {resultado.boleto_id && (
              <div>
                <p className="text-xs text-muted-foreground">ID Boleto</p>
                <p className="text-sm font-mono truncate">{resultado.boleto_id}</p>
              </div>
            )}
          </div>

          {resultado.digitable_line && (
            <CopyField label="Linha Digitável" value={resultado.digitable_line} icon={<FileText className="h-3 w-3" />} />
          )}
          {resultado.barcode && (
            <CopyField label="Código de Barras" value={resultado.barcode} icon={<Barcode className="h-3 w-3" />} />
          )}
          {resultado.pix_copy_paste && (
            <CopyField label="PIX Copia e Cola" value={resultado.pix_copy_paste} icon={<QrCode className="h-3 w-3" />} />
          )}

          {resultado.pix_qrcode && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <QrCode className="h-3 w-3" />QR Code PIX
              </p>
              {resultado.pix_qrcode.startsWith('data:image') || resultado.pix_qrcode.match(/^[A-Za-z0-9+/=]{40,}$/) ? (
                <img
                  src={resultado.pix_qrcode.startsWith('data:') ? resultado.pix_qrcode : `data:image/png;base64,${resultado.pix_qrcode}`}
                  alt="QR Code PIX"
                  className="w-36 h-36 rounded-lg border object-contain bg-white p-1"
                />
              ) : (
                <a href={resultado.pix_qrcode} target="_blank" rel="noopener noreferrer"
                  className="text-sm text-primary underline flex items-center gap-1">
                  Ver QR Code <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {resultado.pdf_url && (
              <a href={resultado.pdf_url} target="_blank" rel="noopener noreferrer">
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Download className="h-4 w-4" />Baixar PDF
                </Button>
              </a>
            )}
            <Button onClick={handleNovo} size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />Nova Cobrança
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toggle de modo */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl w-fit">
        <button
          onClick={() => setMode('boleto')}
          className={cn(
            'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            mode === 'boleto' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'
          )}
        >
          <Barcode className="h-4 w-4" />Boleto Convencional
        </button>
        <button
          onClick={() => setMode('pix')}
          className={cn(
            'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all',
            mode === 'pix' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'
          )}
        >
          <QrCode className="h-4 w-4" />PIX
        </button>
      </div>

      {/* ── Formulário Boleto ────────────────────────────────────────────── */}
      {mode === 'boleto' && (
        <Card>
          <CardContent className="pt-6 space-y-5">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Dados do Boleto</h2>

            {formError && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-600 text-sm">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />{formError}
              </div>
            )}

            <BankSelector value={form.bank_code} onChange={(v) => setField('bank_code', v)} />

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Nome Completo do Pagador</label>
              <Input
                placeholder="Ex: João da Silva"
                value={form.payer_name}
                onChange={(e) => setField('payer_name', e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">CPF / CNPJ</label>
              <Input
                placeholder="000.000.000-00 ou 00.000.000/0001-00"
                value={form.payer_document}
                onChange={(e) => setField('payer_document', maskDocument(e.target.value))}
                maxLength={18}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Valor (R$)</label>
                <Input
                  type="number" min="0.01" step="0.01" placeholder="0,00"
                  value={form.amount}
                  onChange={(e) => setField('amount', e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Data de Vencimento</label>
                <Input
                  type="date"
                  value={form.due_date}
                  min={new Date().toISOString().split('T')[0]}
                  onChange={(e) => setField('due_date', e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Descrição / Referência</label>
              <textarea
                rows={3}
                placeholder="Ex: Mensalidade de vigilância — Janeiro/2026"
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                className={cn(
                  'w-full rounded-md border border-input bg-background px-3 py-2 text-sm',
                  'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
                  'resize-none'
                )}
              />
            </div>

            <Button
              onClick={handleEmitir} disabled={isPending}
              className="w-full gap-2"
              style={{ backgroundColor: BANK_COLORS[form.bank_code] }}
            >
              {isPending
                ? <><RefreshCw className="h-4 w-4 animate-spin" />Emitindo boleto…</>
                : <><Barcode className="h-4 w-4" />Emitir Boleto via {BANK_NAMES[form.bank_code]}</>
              }
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Painel PIX ───────────────────────────────────────────────────── */}
      {mode === 'pix' && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center gap-3 p-4 rounded-xl border border-violet-500/30 bg-violet-500/5">
            <div className="h-10 w-10 rounded-xl bg-violet-600 flex items-center justify-center shrink-0">
              <QrCode className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold">PIX de Recebimento — QR Code Dinâmico</p>
              <p className="text-xs text-muted-foreground">Chave recebedora: CNPJ 35.710.481/0001-03 (Conecta Mais)</p>
            </div>
          </div>

          {/* Resultado gerado */}
          {pixResultado && (
            <Card className="border-violet-500/30 bg-violet-500/5">
              <CardContent className="pt-5 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-violet-500/15 flex items-center justify-center shrink-0">
                    <CheckCircle className="h-5 w-5 text-violet-600" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-violet-700">QR Code PIX Gerado!</h2>
                    <p className="text-sm text-muted-foreground">{pixResultado.bank_name} — {formatCurrency(pixResultado.amount)}</p>
                  </div>
                </div>

                {pixResultado.pix_qrcode && (
                  <div className="flex flex-col items-center gap-3 py-2">
                    {pixResultado.pix_qrcode.startsWith('data:') || pixResultado.pix_qrcode.match(/^[A-Za-z0-9+/=]{40,}$/) ? (
                      <img
                        src={pixResultado.pix_qrcode.startsWith('data:') ? pixResultado.pix_qrcode : `data:image/png;base64,${pixResultado.pix_qrcode}`}
                        alt="QR Code PIX"
                        className="w-48 h-48 border rounded-xl"
                      />
                    ) : (
                      <div className="w-48 h-48 border rounded-xl bg-muted/30 flex items-center justify-center">
                        <QrCode className="h-20 w-20 text-violet-500/40" />
                      </div>
                    )}
                    {pixResultado.expires_at && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Válido até {new Date(pixResultado.expires_at).toLocaleString('pt-BR')}
                      </p>
                    )}
                  </div>
                )}

                {pixResultado.pix_copy_paste && (
                  <CopyField
                    label="PIX Copia e Cola"
                    value={pixResultado.pix_copy_paste}
                    icon={<QrCode className="h-3 w-3" />}
                  />
                )}

                <Button variant="outline" className="w-full" onClick={() => { setPixResultado(null); setPixError(null); }}>
                  Nova Cobrança PIX
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Formulário */}
          {!pixResultado && (
            <Card>
              <CardContent className="pt-6 space-y-5">
                <BankSelector value={pixBankCode} onChange={setPixBankCode} />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">Valor (R$) *</label>
                    <Input
                      type="number" step="0.01" min="0.01" placeholder="Ex: 1.250,00"
                      value={pixForm.amount}
                      onChange={(e) => setPixForm(p => ({ ...p, amount: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">Validade</label>
                    <select
                      value={pixForm.expiracao_horas}
                      onChange={(e) => setPixForm(p => ({ ...p, expiracao_horas: Number(e.target.value) }))}
                      className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value={1}>1 hora</option>
                      <option value={4}>4 horas</option>
                      <option value={24}>24 horas</option>
                      <option value={72}>72 horas</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Descrição *</label>
                  <Input
                    placeholder="Ex: Contrato de vigilância — Março/2026"
                    value={pixForm.description}
                    onChange={(e) => setPixForm(p => ({ ...p, description: e.target.value }))}
                    maxLength={140}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-muted-foreground">Nome do Pagador (opcional)</label>
                    <Input
                      placeholder="Nome ou razão social"
                      value={pixForm.payer_name}
                      onChange={(e) => setPixForm(p => ({ ...p, payer_name: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-muted-foreground">CPF/CNPJ (opcional)</label>
                    <Input
                      placeholder="000.000.000-00"
                      value={pixForm.payer_document}
                      onChange={(e) => setPixForm(p => ({ ...p, payer_document: maskDocument(e.target.value) }))}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2 p-3 rounded-lg border border-violet-500/30 bg-violet-500/5">
                  <QrCode className="h-4 w-4 text-violet-600 shrink-0" />
                  <p className="text-xs text-muted-foreground">
                    Recebimento via: <span className="font-mono font-semibold text-violet-700">CNPJ 35.710.481/0001-03</span>
                  </p>
                </div>

                {pixError && (
                  <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                    <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                    <p className="text-sm text-destructive">{pixError}</p>
                  </div>
                )}

                <Button
                  onClick={handleGerarPix}
                  disabled={pixPending}
                  className="w-full gap-2 bg-violet-600 hover:bg-violet-700 text-white"
                >
                  {pixPending
                    ? <><RefreshCw className="h-4 w-4 animate-spin" />Gerando QR Code...</>
                    : <><QrCode className="h-4 w-4" />Gerar QR Code PIX</>
                  }
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Tab 2: Cobranças Emitidas ────────────────────────────────────────────────

function TabListagem() {
  const [filterBanco, setFilterBanco] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDias, setFilterDias] = useState('30');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const { data: boletosData, isLoading, refetch } = useQuery<{ boletos: BoletoListItem[] }>({
    queryKey: ['boletos', filterBanco, filterStatus, filterDias],
    queryFn: () => listarBoletos(filterBanco || undefined, filterStatus || undefined, parseInt(filterDias)),
    staleTime: 5 * 60 * 1000,
  });

  const boletos = boletosData?.boletos ?? [];
  const carregar = useCallback(() => { void refetch(); }, [refetch]);

  const copiar = useCallback(async (id: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  return (
    <div className="space-y-4">
      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={filterBanco}
          onChange={(e) => setFilterBanco(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Todos os bancos</option>
          <option value="077">Inter (077)</option>
        </select>

        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Todos os status</option>
          <option value="pending">Pendente</option>
          <option value="paid">Pago</option>
          <option value="overdue">Vencido</option>
          <option value="cancelled">Cancelado</option>
        </select>

        <select
          value={filterDias}
          onChange={(e) => setFilterDias(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="7">Últimos 7 dias</option>
          <option value="15">Últimos 15 dias</option>
          <option value="30">Últimos 30 dias</option>
          <option value="60">Últimos 60 dias</option>
          <option value="90">Últimos 90 dias</option>
        </select>

        <Button
          variant="outline" size="sm" onClick={carregar} disabled={isLoading}
          className="gap-1.5 ml-auto"
        >
          <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
          {isLoading ? 'Atualizando…' : 'Atualizar'}
        </Button>
      </div>

      {/* Tabela */}
      {boletos.length === 0 ? (
        <Card>
          <CardContent className="py-16 flex flex-col items-center gap-3 text-center">
            <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
              <Barcode className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium">Nenhuma cobrança encontrada.</p>
            <p className="text-xs text-muted-foreground max-w-xs">
              {filterBanco || filterStatus ? 'Tente outros filtros.' : 'Emita a primeira cobrança na aba "Emitir Cobrança".'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {boletos.map((b) => (
            <Card
              key={b.boleto_id} className="overflow-hidden"
              style={{ borderLeft: `4px solid ${BANK_COLORS[b.bank_code] ?? '#888'}` }}
            >
              <CardContent className="py-3 px-4">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{b.payer_name}</p>
                    <p className="text-xs font-medium" style={{ color: BANK_COLORS[b.bank_code] ?? '#888' }}>
                      {b.bank_name}
                    </p>
                  </div>

                  <div className="text-right">
                    <p className="text-sm font-semibold">{formatCurrency(b.amount)}</p>
                    <p className="text-xs text-muted-foreground">Vence {formatDate(b.due_date)}</p>
                  </div>

                  {b.created_at && (
                    <div className="hidden sm:block text-right">
                      <p className="text-xs text-muted-foreground">Emitido</p>
                      <p className="text-xs">{formatDate(b.created_at)}</p>
                    </div>
                  )}

                  <StatusBadge status={b.status} />

                  <div className="flex items-center gap-1 ml-auto">
                    {b.digitable_line && (
                      <Button
                        variant="ghost" size="sm"
                        className={cn('h-8 gap-1.5 text-xs', copiedId === b.boleto_id && 'text-green-600')}
                        title="Copiar linha digitável"
                        onClick={() => copiar(b.boleto_id, b.digitable_line!)}
                      >
                        {copiedId === b.boleto_id
                          ? <><CheckCircle className="h-3.5 w-3.5" />Copiado!</>
                          : <><Copy className="h-3.5 w-3.5" />Copiar</>
                        }
                      </Button>
                    )}
                    {b.pdf_url && (
                      <a href={b.pdf_url} target="_blank" rel="noopener noreferrer">
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="Ver PDF">
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </a>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          <p className="text-xs text-muted-foreground text-right pt-1">
            {boletos.length} cobrança{boletos.length !== 1 ? 's' : ''} encontrada{boletos.length !== 1 ? 's' : ''}
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Tab 4: Régua de Cobrança ─────────────────────────────────────────────────

const STORAGE_KEY = 'cobrancas_regua_config';

function TabRegua() {
  const [momentos, setMomentos] = useState<ReguaMomento[]>(REGUA_DEFAULT);
  const [saved, setSaved] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setMomentos(JSON.parse(stored) as ReguaMomento[]);
    } catch { /* ignora */ }
  }, []);

  const updateMomento = useCallback((key: string, patch: Partial<ReguaMomento>) => {
    setMomentos((prev) => prev.map((m) => m.key === key ? { ...m, ...patch } : m));
  }, []);

  const salvar = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(momentos));
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }, [momentos]);

  const CANAL_OPTIONS: Array<{ value: ReguaMomento['canal']; label: string }> = [
    { value: 'whatsapp',  label: 'WhatsApp'  },
    { value: 'email',     label: 'E-mail'    },
    { value: 'sms',       label: 'SMS'       },
    { value: 'telefone',  label: 'Telefone'  },
  ];

  const TOM_OPTIONS: Array<{ value: ReguaMomento['tom']; label: string }> = [
    { value: 'amigavel',     label: 'Amigável'      },
    { value: 'profissional', label: 'Profissional'  },
    { value: 'firme',        label: 'Firme'         },
    { value: 'formal',       label: 'Formal'        },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Régua Automática de Cobrança</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Configure quando e como os lembretes serão enviados automaticamente.
          </p>
        </div>
        <Button onClick={salvar} size="sm" className="gap-1.5 shrink-0">
          {saved
            ? <><CheckCircle className="h-4 w-4" />Salvo!</>
            : <><Settings className="h-4 w-4" />Salvar Configuração</>
          }
        </Button>
      </div>

      {/* Linha do tempo visual */}
      <div className="relative pl-4">
        <div className="absolute left-6 top-4 bottom-4 w-0.5 bg-border" />
        <div className="space-y-3">
          {momentos.map((m) => {
            const isExpanded = expandedKey === m.key;
            const dotCor = getReguaDotCor(m.dias);
            const cardCor = getReguaCor(m.dias);
            const preview = getPreviewMensagem(m);

            return (
              <div key={m.key} className="relative">
                {/* Dot na linha do tempo */}
                <div className={cn(
                  'absolute left-0 top-4 h-4 w-4 rounded-full border-2 border-background z-10',
                  dotCor,
                  !m.enabled && 'opacity-40'
                )} />

                <div className={cn('ml-8 rounded-xl border-2 transition-all', cardCor, !m.enabled && 'opacity-60')}>
                  {/* Cabeçalho do card */}
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Toggle */}
                    <button
                      type="button"
                      onClick={() => updateMomento(m.key, { enabled: !m.enabled })}
                      className={cn(
                        'relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors',
                        m.enabled ? 'bg-primary' : 'bg-muted-foreground/30'
                      )}
                    >
                      <span className={cn(
                        'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform',
                        m.enabled ? 'translate-x-4' : 'translate-x-0'
                      )} />
                    </button>

                    {/* Label */}
                    <div className="flex-1 min-w-0">
                      <p className={cn('text-sm font-medium', !m.enabled && 'text-muted-foreground')}>
                        {m.label}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-muted-foreground">{CANAL_ICONS[m.canal]}</span>
                        <span className="text-xs text-muted-foreground capitalize">{m.canal}</span>
                        <span className="text-muted-foreground/40 text-xs">·</span>
                        <span className="text-xs text-muted-foreground capitalize">{m.tom}</span>
                      </div>
                    </div>

                    {/* Expand toggle */}
                    <button
                      type="button"
                      onClick={() => setExpandedKey(isExpanded ? null : m.key)}
                      className="text-muted-foreground hover:text-foreground transition-colors p-1"
                    >
                      {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                  </div>

                  {/* Detalhes expandidos */}
                  {isExpanded && (
                    <div className="px-4 pb-4 pt-0 space-y-3 border-t border-current/10">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3">
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-muted-foreground">Canal de envio</label>
                          <select
                            value={m.canal}
                            onChange={(e) => updateMomento(m.key, { canal: e.target.value as ReguaMomento['canal'] })}
                            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          >
                            {CANAL_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-muted-foreground">Tom da mensagem</label>
                          <select
                            value={m.tom}
                            onChange={(e) => updateMomento(m.key, { tom: e.target.value as ReguaMomento['tom'] })}
                            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          >
                            {TOM_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                          </select>
                        </div>
                      </div>

                      {/* Preview da mensagem */}
                      <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">Prévia da mensagem</label>
                        <div className="p-3 rounded-lg bg-background/70 border text-xs text-muted-foreground italic leading-relaxed">
                          &ldquo;{preview}&rdquo;
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legenda */}
      <div className="flex flex-wrap gap-3 pt-2">
        {[
          { cor: 'bg-green-500', label: 'Pré-vencimento' },
          { cor: 'bg-yellow-500', label: 'Dia do vencimento' },
          { cor: 'bg-orange-500', label: 'Até 7 dias de atraso' },
          { cor: 'bg-red-500', label: 'Mais de 7 dias' },
        ].map(({ cor, label }) => (
          <div key={label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className={cn('h-2.5 w-2.5 rounded-full', cor)} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Tab 3: PIX Recorrente ────────────────────────────────────────────────────

function TabRecorrente() {
  const now = new Date();
  const mes = now.getMonth() + 1;
  const ano = now.getFullYear();

  const { data: preview, isLoading, refetch } = useQuery<CobrancaPreview>({
    queryKey: ['cobrar-recorrente-preview', mes, ano],
    queryFn: () =>
      api.get<CobrancaPreview>(`/api/v1/financial/billing/cobrar-recorrente/${mes}/${ano}/preview`)
        .then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const [cobrandoTodos, setCobrandoTodos] = useState(false);
  const [cobrancaMsg, setCobrancaMsg] = useState<string | null>(null);

  const cobrarTodos = useCallback(async () => {
    setCobrandoTodos(true);
    setCobrancaMsg(null);
    try {
      await api.post(`/api/v1/financial/billing/cobrar-recorrente/${mes}/${ano}`);
      setCobrancaMsg('Cobranças enviadas com sucesso!');
      refetch();
    } catch {
      setCobrancaMsg('Erro ao enviar cobranças. Verifique as chaves PIX.');
    } finally {
      setCobrandoTodos(false);
    }
  }, [mes, ano, refetch]);

  const MESES = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const clientes = preview?.clientes ?? [];
  const semPix = preview?.sem_pix_key ?? [];

  return (
    <div className="space-y-5">
      {/* Header KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground">MRR {MESES[mes]}/{ano}</p>
            <p className="font-data text-xl font-semibold tabular-nums text-emerald-600 mt-1">
              {formatCurrency(preview?.total_mrr ?? 0)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground">Clientes recorrentes</p>
            <p className="font-data text-xl font-semibold tabular-nums text-blue-600 mt-1">
              {preview?.total_clientes ?? 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground">Sem chave PIX</p>
            <p className={cn('font-data text-xl font-semibold tabular-nums mt-1', semPix.length > 0 ? 'text-red-600' : 'text-emerald-600')}>
              {semPix.length}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Ação cobrar todos */}
      <div className="flex items-center gap-3">
        <Button
          onClick={cobrarTodos}
          disabled={cobrandoTodos || clientes.length === 0}
          className="gap-2 bg-violet-600 hover:bg-violet-700 text-white"
        >
          {cobrandoTodos
            ? <><RefreshCw className="h-4 w-4 animate-spin" />Enviando PIX...</>
            : <><QrCode className="h-4 w-4" />Cobrar todos via PIX ({MESES[mes]})</>
          }
        </Button>
        {cobrancaMsg && (
          <span className={cn('text-sm', cobrancaMsg.includes('sucesso') ? 'text-emerald-600' : 'text-red-600')}>
            {cobrancaMsg}
          </span>
        )}
      </div>

      {/* Lista de clientes */}
      {clientes.length === 0 ? (
        <Card>
          <CardContent className="py-12 flex flex-col items-center gap-2 text-center">
            <Users className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Nenhum cliente recorrente encontrado para {MESES[mes]}/{ano}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {clientes.map((c, i) => (
            <Card key={i}>
              <CardContent className="py-3 px-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{c.nome}</p>
                    <p className="text-xs text-muted-foreground">
                      CNPJ: {c.cnpj} · Venc: {new Date(c.vencimento).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={cn(
                      'text-xs px-2 py-0.5 rounded-full border',
                      c.pix_key
                        ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30'
                        : 'bg-red-500/10 text-red-600 border-red-500/30'
                    )}>
                      {c.pix_key ? <span className="inline-flex items-center gap-1">PIX <CheckCircle2 className="w-3 h-3" /></span> : 'Sem PIX'}
                    </span>
                    <p className="text-sm font-bold text-emerald-600">
                      {formatCurrency(c.mrr)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Tab 5: Inadimplentes ─────────────────────────────────────────────────────

function TabInadimplentes() {
  const { condominioId } = useCondominio();
  const { data: dashboardRaw } = useReceivableDashboard({ condominio_id: condominioId });
  const dashboard = dashboardRaw as Record<string, unknown> | undefined;

  const [filtroValor, setFiltroValor] = useState('');

  // Modais
  const [lembreteModal, setLembreteModal]   = useState<LembreteModal | null>(null);
  const [acordoModal, setAcordoModal]       = useState<AcordoModal | null>(null);
  const [contatoModal, setContatoModal]     = useState<ContatoModal | null>(null);
  const [notas, setNotas]                   = useState<ContatoNota[]>([]);
  const [notaTexto, setNotaTexto]           = useState('');
  const [acordoForm, setAcordoForm]         = useState<AcordoForm>({ valor: '', parcelas: '1', data_primeiro: '' });

  // Dados reais — CRM clients
  const { data: crmData } = useQuery<{ items: CrmClientItem[]; total: number }>({
    queryKey: ['crm-clients-all'],
    queryFn: () => api.get<{ items: CrmClientItem[]; total: number }>('/api/v1/crm/clients?page=1&per_page=50').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const { data: crmResumo } = useQuery<CrmResumo>({
    queryKey: ['crm-resumo'],
    queryFn: () => api.get<CrmResumo>('/api/v1/crm/clients/resumo').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const { data: aiRecs } = useQuery<AiRecommendation[]>({
    queryKey: ['ai-recommendations'],
    queryFn: () => api.get<AiRecommendation[]>('/api/v1/financial/ai/advisor/recommendations').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  // CollectionNegotiatorAgent — dados reais de inadimplência com ações recomendadas
  const { data: collectionData } = useQuery<CollectionAnalysis>({
    queryKey: ['collection-analyze'],
    queryFn: () => api.get<CollectionAnalysis>('/api/v1/financial/ai/collection/analyze').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  // Billing rules — regras de cobrança automática
  const { data: billingRules = [] } = useQuery<BillingRule[]>({
    queryKey: ['billing-rules'],
    queryFn: () => api.get<BillingRule[]>('/api/v1/financial/billing-rules').then((r) => Array.isArray(r.data) ? r.data : []),
    staleTime: 5 * 60 * 1000,
  });

  // Receivables — contas a receber
  const { data: receivablesData } = useQuery<{ data: ReceivableAccount[]; meta: { total: number } }>({
    queryKey: ['receivables'],
    queryFn: () => api.get<{ data: ReceivableAccount[]; meta: { total: number } }>('/api/v1/financial/receivables?page=1&page_size=20').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  // Inadimplentes: CollectionNegotiatorAgent como fonte primária, CRM como fallback
  const inadimplentes = useMemo(() => {
    const acoes = collectionData?.acoes ?? [];
    if (acoes.length > 0) {
      const filtered = filtroValor
        ? acoes.filter((a) => a.valor >= parseFloat(filtroValor))
        : acoes;
      return { source: 'collection' as const, items: filtered };
    }
    // Fallback CRM
    const base = (crmData?.items ?? []).filter(
      (c) => c.is_defaulter === true || (c.total_debt !== null && c.total_debt !== undefined && c.total_debt > 0)
    );
    const filtered = filtroValor ? base.filter((c) => (c.total_debt ?? 0) >= parseFloat(filtroValor)) : base;
    return { source: 'crm' as const, items: filtered };
  }, [collectionData?.acoes, crmData?.items, filtroValor]);

  // KPIs: campos top-level do CollectionNegotiatorAgent (mais precisos que somar acoes[])
  const overdueCount       = collectionData?.qtd_inadimplentes ?? (dashboard?.overdue_count as number | undefined) ?? crmResumo?.inadimplentes ?? 0;
  const overdueAmount      = collectionData?.total_em_atraso ?? (dashboard?.overdue_amount as number | undefined) ?? 0;
  const maiorValor         = (collectionData?.acoes ?? []).reduce((mx, a) => a.valor > mx ? a.valor : mx, 0);
  const totalClientes      = crmResumo?.clientes_ativos ?? crmData?.total ?? 0;
  const taxaRecuperacao    = collectionData?.taxa_recuperacao_estimada ?? 0;
  const regrasAtivas       = billingRules.filter((r) => r.ativo).length;
  const totalRecebiveis    = receivablesData?.meta?.total ?? 0;
  // Painel de inadimplência exibido quando taxa > 5%
  const taxaInadimplencia  = totalClientes > 0 ? (overdueCount / totalClientes) * 100 : 0;

  const salvarNota = useCallback(() => {
    if (!contatoModal || !notaTexto.trim()) return;
    setNotas((prev) => [...prev, {
      inadimplente_id: contatoModal.id,
      texto: notaTexto.trim(),
      data: new Date().toLocaleDateString('pt-BR'),
    }]);
    setNotaTexto('');
    setContatoModal(null);
  }, [contatoModal, notaTexto]);

  const KPI_CARDS = [
    { label: 'Total em atraso',       value: formatCurrency(overdueAmount),       icon: <TrendingDown className="h-5 w-5" />,  cor: 'text-red-600',     bg: 'bg-red-500/10'     },
    { label: 'Qtd. inadimplentes',    value: String(overdueCount),                icon: <Users className="h-5 w-5" />,         cor: 'text-orange-600',  bg: 'bg-orange-500/10'  },
    { label: 'Taxa recuperação est.', value: `${taxaRecuperacao.toFixed(1)}%`,    icon: <TrendingDown className="h-5 w-5" />,  cor: 'text-emerald-600', bg: 'bg-emerald-500/10' },
    { label: 'Regras cobrança ativas',value: `${regrasAtivas} / ${billingRules.length}`, icon: <Settings className="h-5 w-5" />, cor: 'text-blue-600', bg: 'bg-blue-500/10'   },
    { label: 'Maior devedor',         value: formatCurrency(maiorValor),          icon: <AlertTriangle className="h-5 w-5" />, cor: 'text-yellow-600',  bg: 'bg-yellow-500/10'  },
    { label: 'Clientes ativos',       value: String(totalClientes),               icon: <CheckCircle className="h-5 w-5" />,   cor: 'text-blue-600',    bg: 'bg-blue-500/10'    },
    { label: 'Contas a receber',      value: String(totalRecebiveis),             icon: <FileText className="h-5 w-5" />,      cor: 'text-violet-600',  bg: 'bg-violet-500/10'  },
  ];

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {KPI_CARDS.map((k) => (
          <Card key={k.label}>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-muted-foreground leading-tight">{k.label}</p>
                  <p className={cn('text-lg font-bold mt-1', k.cor)}>{k.value}</p>
                </div>
                <div className={cn('h-9 w-9 rounded-lg flex items-center justify-center shrink-0', k.bg, k.cor)}>
                  {k.icon}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recomendações IA — exibido quando taxa de inadimplência > 5% */}
      {taxaInadimplencia > 5 && aiRecs && aiRecs.length > 0 && aiRecs.filter((r) => r.categoria === 'inadimplencia').map((rec, i) => (
        <div key={i} className="flex gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-700">{rec.titulo}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{rec.descricao}</p>
          </div>
        </div>
      ))}

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground whitespace-nowrap">Valor mínimo:</label>
          <Input
            type="number" min="0" step="100" placeholder="R$ 0"
            value={filtroValor}
            onChange={(e) => setFiltroValor(e.target.value)}
            className="w-32 h-9"
          />
        </div>
      </div>

      {/* Lista de inadimplentes — CollectionNegotiatorAgent */}
      {inadimplentes.items.length === 0 ? (
        <Card>
          <CardContent className="py-16 flex flex-col items-center gap-3 text-center">
            <div className="h-12 w-12 rounded-full bg-green-500/15 flex items-center justify-center">
              <CheckCircle className="h-6 w-6 text-green-600" />
            </div>
            <p className="text-sm font-medium">Carteira limpa!</p>
            <p className="text-xs text-muted-foreground">Nenhum cliente com dívida em aberto.</p>
          </CardContent>
        </Card>
      ) : inadimplentes.source === 'collection' ? (
        <div className="space-y-2">
          {(inadimplentes.items as CollectionAction[]).map((item) => {
            const critico = item.dias_atraso > 30 || item.prioridade === 'urgente';
            const notasItem = notas.filter((n) => n.inadimplente_id === item.id);

            return (
              <Card
                key={item.id}
                className={cn(
                  'overflow-hidden transition-colors',
                  critico ? 'border-red-500/40 bg-red-500/3' : 'border-orange-500/20'
                )}
                style={{ borderLeft: `4px solid ${critico ? '#ef4444' : '#f97316'}` }}
              >
                <CardContent className="py-3 px-4">
                  <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
                    {/* Info cliente */}
                    <div className="flex-1 min-w-0">
                      <p className={cn('text-sm font-semibold truncate', critico && 'text-red-700 dark:text-red-400')}>
                        {item.customer_name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {item.acao} · {item.canal}
                      </p>
                    </div>

                    {/* Valor e dias */}
                    <div className="text-right">
                      <p className={cn('text-sm font-bold', critico ? 'text-red-600' : 'text-orange-600')}>
                        {formatCurrency(item.valor)}
                      </p>
                      <p className="text-xs text-muted-foreground">{item.dias_atraso} dias em atraso</p>
                    </div>

                    {/* Prioridade badge */}
                    <span className={cn(
                      'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
                      item.prioridade === 'urgente' ? 'bg-red-500/10 text-red-600 border-red-500/30' :
                      item.prioridade === 'alta' ? 'bg-orange-500/10 text-orange-600 border-orange-500/30' :
                      'bg-yellow-500/10 text-yellow-600 border-yellow-500/30'
                    )}>
                      {item.prioridade}
                    </span>

                    {/* Ações */}
                    <div className="flex flex-wrap gap-1.5">
                      <Button
                        variant="outline" size="sm"
                        className="h-7 text-xs gap-1 border-blue-500/50 text-blue-600 hover:bg-blue-500/10"
                        onClick={() => setLembreteModal({ id: item.id, nome: item.customer_name, valor: item.valor, dias: item.dias_atraso })}
                      >
                        <MessageSquare className="h-3 w-3" />Lembrete
                      </Button>
                      <Button
                        variant="outline" size="sm"
                        className="h-7 text-xs gap-1 border-muted-foreground/40 text-muted-foreground hover:bg-muted/50"
                        onClick={() => setContatoModal({ id: item.id, nome: item.customer_name })}
                      >
                        <Clock className="h-3 w-3" />Contato
                      </Button>
                      <Button
                        variant="outline" size="sm"
                        className="h-7 text-xs gap-1 border-green-500/50 text-green-600 hover:bg-green-500/10"
                        onClick={() => setAcordoModal({ id: item.id, nome: item.customer_name, valor: item.valor })}
                      >
                        <Handshake className="h-3 w-3" />Acordo
                      </Button>
                    </div>
                  </div>

                  {/* Mensagem recomendada pelo agente */}
                  <div className="mt-2 pt-2 border-t border-dashed">
                    <p className="text-xs text-muted-foreground italic">{item.mensagem}</p>
                  </div>

                  {/* Notas registradas */}
                  {notasItem.length > 0 && (
                    <div className="mt-1 space-y-1">
                      {notasItem.map((n, idx) => (
                        <p key={idx} className="text-xs text-muted-foreground">
                          <span className="font-medium">{n.data}:</span> {n.texto}
                        </p>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2">
          {(inadimplentes.items as CrmClientItem[]).map((item) => {
            const debt = item.total_debt ?? 0;
            const critico = debt > 5000;
            const notasItem = notas.filter((n) => n.inadimplente_id === item.id);
            return (
              <Card key={item.id} className={cn('overflow-hidden', critico ? 'border-red-500/40' : 'border-orange-500/20')}
                style={{ borderLeft: `4px solid ${critico ? '#ef4444' : '#f97316'}` }}>
                <CardContent className="py-3 px-4">
                  <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
                    <div className="flex-1 min-w-0">
                      <p className={cn('text-sm font-semibold truncate', critico && 'text-red-700')}>{item.name}</p>
                      <p className="text-xs text-muted-foreground">{item.cnpj}</p>
                    </div>
                    <div className="text-right">
                      <p className={cn('text-sm font-bold', critico ? 'text-red-600' : 'text-orange-600')}>{formatCurrency(debt)}</p>
                      <p className="text-xs text-muted-foreground">em aberto</p>
                    </div>
                    <div className="flex gap-1.5">
                      <Button variant="outline" size="sm" className="h-7 text-xs gap-1 border-blue-500/50 text-blue-600 hover:bg-blue-500/10"
                        onClick={() => setLembreteModal({ id: item.id, nome: item.name, valor: debt, dias: 0 })}>
                        <MessageSquare className="h-3 w-3" />Lembrete
                      </Button>
                      <Button variant="outline" size="sm" className="h-7 text-xs gap-1 border-green-500/50 text-green-600 hover:bg-green-500/10"
                        onClick={() => setAcordoModal({ id: item.id, nome: item.name, valor: debt })}>
                        <Handshake className="h-3 w-3" />Acordo
                      </Button>
                    </div>
                  </div>
                  {notasItem.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-dashed space-y-1">
                      {notasItem.map((n, idx) => (
                        <p key={idx} className="text-xs text-muted-foreground"><span className="font-medium">{n.data}:</span> {n.texto}</p>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* ── Modal: Lembrete ──────────────────────────────────────────────── */}
      {lembreteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <Card className="w-full max-w-md">
            <CardContent className="pt-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold">Enviar Lembrete</h3>
                <button type="button" onClick={() => setLembreteModal(null)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="p-3 rounded-lg bg-muted/50 space-y-2">
                <p className="text-sm font-medium">{lembreteModal.nome}</p>
                <p className="text-xs text-muted-foreground">
                  Débito: {formatCurrency(lembreteModal.valor)} · {lembreteModal.dias} dias em atraso
                </p>
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Prévia da mensagem (WhatsApp):</p>
                <div className="p-3 rounded-lg bg-[#dcf8c6] dark:bg-green-900/30 text-xs text-foreground/90 leading-relaxed border">
                  Olá {lembreteModal.nome.split(' ')[0]}! Identificamos um débito de {formatCurrency(lembreteModal.valor)} em
                  atraso há {lembreteModal.dias} dias. Entre em contato para regularizar ou acessar nossa central de
                  atendimento. Estamos à disposição! 😊
                </div>
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20 text-xs text-muted-foreground leading-relaxed">
                  <span className="font-medium text-blue-600">E-mail:</span> Prezado(a) {lembreteModal.nome.split(' ')[0]}, identificamos
                  pendência de {formatCurrency(lembreteModal.valor)} há {lembreteModal.dias} dias. Solicitamos regularização.
                </div>
              </div>

              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1 gap-1.5" onClick={() => setLembreteModal(null)}>
                  <X className="h-3.5 w-3.5" />Cancelar
                </Button>
                <Button className="flex-1 gap-1.5 bg-[#25D366] hover:bg-[#20bd5a] text-white" onClick={() => setLembreteModal(null)}>
                  <MessageSquare className="h-3.5 w-3.5" />Enviar WhatsApp
                </Button>
                <Button variant="outline" className="flex-1 gap-1.5" onClick={() => setLembreteModal(null)}>
                  <Mail className="h-3.5 w-3.5" />Enviar E-mail
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Modal: Registrar Contato ─────────────────────────────────────── */}
      {contatoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <Card className="w-full max-w-md">
            <CardContent className="pt-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold">Registrar Contato</h3>
                <button type="button" onClick={() => setContatoModal(null)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <p className="text-sm text-muted-foreground">
                Registre o resultado do contato com <strong>{contatoModal.nome}</strong>.
              </p>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">Nota de contato</label>
                <textarea
                  rows={4}
                  placeholder="Ex: Falei com o responsável financeiro. Prometeu pagar até dia 15/03. Aguardando…"
                  value={notaTexto}
                  onChange={(e) => setNotaTexto(e.target.value)}
                  className={cn(
                    'w-full rounded-md border border-input bg-background px-3 py-2 text-sm',
                    'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none'
                  )}
                />
              </div>

              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1" onClick={() => setContatoModal(null)}>Cancelar</Button>
                <Button className="flex-1 gap-1.5" onClick={salvarNota} disabled={!notaTexto.trim()}>
                  <CheckCircle className="h-3.5 w-3.5" />Salvar Nota
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Modal: Fazer Acordo ──────────────────────────────────────────── */}
      {acordoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <Card className="w-full max-w-md">
            <CardContent className="pt-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold flex items-center gap-2">
                  <Handshake className="h-5 w-5 text-green-600" />Fazer Acordo
                </h3>
                <button type="button" onClick={() => setAcordoModal(null)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="p-3 rounded-lg bg-muted/50">
                <p className="text-sm font-medium">{acordoModal.nome}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Valor original: {formatCurrency(acordoModal.valor)}
                </p>
              </div>

              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Valor acordado (R$)</label>
                  <Input
                    type="number" min="0.01" step="0.01"
                    placeholder={String(acordoModal.valor.toFixed(2))}
                    value={acordoForm.valor}
                    onChange={(e) => setAcordoForm((p) => ({ ...p, valor: e.target.value }))}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">Nº de parcelas</label>
                    <select
                      value={acordoForm.parcelas}
                      onChange={(e) => setAcordoForm((p) => ({ ...p, parcelas: e.target.value }))}
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                      {[1, 2, 3, 4, 6, 12].map((n) => (
                        <option key={n} value={n}>{n}x {n === 1 ? '(à vista)' : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">1ª parcela em</label>
                    <Input
                      type="date"
                      value={acordoForm.data_primeiro}
                      min={new Date().toISOString().split('T')[0]}
                      onChange={(e) => setAcordoForm((p) => ({ ...p, data_primeiro: e.target.value }))}
                    />
                  </div>
                </div>

                {acordoForm.valor && parseInt(acordoForm.parcelas) > 1 && (
                  <div className="p-2.5 rounded-lg bg-green-500/10 border border-green-500/20 text-xs text-green-700">
                    Valor por parcela: {formatCurrency(parseFloat(acordoForm.valor) / parseInt(acordoForm.parcelas))}
                  </div>
                )}
              </div>

              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1" onClick={() => setAcordoModal(null)}>Cancelar</Button>
                <Button
                  className="flex-1 gap-1.5 bg-green-600 hover:bg-green-700 text-white"
                  disabled={!acordoForm.valor || !acordoForm.data_primeiro}
                  onClick={() => {
                    // Aqui seria chamada de API para registrar acordo
                    setAcordoModal(null);
                    setAcordoForm({ valor: '', parcelas: '1', data_primeiro: '' });
                  }}
                >
                  <Handshake className="h-3.5 w-3.5" />Confirmar Acordo
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Página Principal ─────────────────────────────────────────────────────────

const TABS: Array<{ key: TabType; label: string; icon: React.ReactNode }> = [
  { key: 'emit',          label: 'Emitir Cobrança',   icon: <Plus className="h-4 w-4" />          },
  { key: 'list',          label: 'Emitidas',           icon: <FileText className="h-4 w-4" />      },
  { key: 'recorrente',    label: 'PIX Recorrente',     icon: <QrCode className="h-4 w-4" />        },
  { key: 'regua',         label: 'Régua',              icon: <Bell className="h-4 w-4" />          },
  { key: 'inadimplentes', label: 'Inadimplentes',      icon: <AlertTriangle className="h-4 w-4" /> },
];

export default function CobrancasPage() {
  const { condominioId } = useCondominio();
  const [activeTab, setActiveTab] = useState<TabType>('emit');

  return (
    <div className="min-h-screen bg-background animate-fade-in">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-3">
          <Link href="/modulos/financeiro">
            <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />Voltar
            </Button>
          </Link>
          <div className="h-5 w-px bg-border" />
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: '#e85d26' }}>
              <Barcode className="h-4 w-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold leading-tight">Cobranças</h1>
              <p className="text-xs text-muted-foreground">Boletos, PIX, régua automática e inadimplentes</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6">
        <div className="flex gap-0 border-b mt-0 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap',
                activeTab === tab.key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.icon}
              <span className="hidden sm:inline">{tab.label}</span>
              <span className="sm:hidden">{tab.label.split(' ')[0]}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Conteúdo das tabs */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        {activeTab === 'emit'          && <TabEmitir />}
        {activeTab === 'list'          && <TabListagem />}
        {activeTab === 'recorrente'    && <TabRecorrente />}
        {activeTab === 'regua'         && <TabRegua />}
        {activeTab === 'inadimplentes' && <TabInadimplentes />}
      </div>
    </div>
  );
}
