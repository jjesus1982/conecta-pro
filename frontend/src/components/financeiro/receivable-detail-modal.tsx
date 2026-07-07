'use client';

import { useState } from 'react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Landmark, CheckCircle2, XCircle, Copy, Receipt, Zap } from 'lucide-react';

interface ReceivableDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  receivable: any;
}

const formatCurrency = (value: number | null | undefined) =>
  (value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const formatDate = (date: string | null | undefined) => {
  if (!date) return '-';
  try {
    return new Date(date).toLocaleDateString('pt-BR');
  } catch {
    return date;
  }
};

const getStatusBadge = (status?: string | null) => {
  switch (status) {
    case 'pending':
    case 'pendente':
      return <Badge className="bg-yellow-100 text-yellow-800">Pendente</Badge>;
    case 'overdue':
      return <Badge className="bg-red-100 text-red-800">Atrasada</Badge>;
    case 'paid':
    case 'recebido':
      return <Badge className="bg-green-100 text-green-800">Recebida</Badge>;
    case 'cancelled':
      return <Badge variant="secondary">Cancelada</Badge>;
    default:
      return <Badge variant="outline">{status || '-'}</Badge>;
  }
};

const CATEGORY_LABELS: Record<string, string> = {
  service: 'Servico',
  product: 'Produto',
  subscription: 'Assinatura',
  rental: 'Aluguel',
  other: 'Outros',
};

interface CobrancaData {
  tipo: 'boleto' | 'pix';
  barcode?: string;
  digitable_line?: string;
  pix_copy_paste?: string;
  boleto_id?: string;
  charge_id?: string;
  valor?: number;
}

export function ReceivableDetailModal({ isOpen, onClose, receivable }: ReceivableDetailModalProps) {
  const [cobrancaLoading, setCobrancaLoading] = useState(false);
  const [cobrancaMsg, setCobrancaMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [cobrancaData, setCobrancaData] = useState<CobrancaData | null>(null);

  if (!receivable) return null;

  const isPendente = ['pending', 'pendente', 'overdue'].includes(receivable.status);
  const temBoleto = receivable.boleto_generated || receivable.boleto_digitable_line || receivable.boleto_barcode;
  const temPix = receivable.pix_generated || receivable.pix_copy_paste;
  const valor = parseFloat(receivable.net_value || receivable.gross_value || '0');

  const getToken = () =>
    typeof window !== 'undefined' ? (localStorage.getItem('token') || '') : '';

  const handleGerarCobranca = async (tipo: 'boleto' | 'pix') => {
    setCobrancaLoading(true);
    setCobrancaMsg(null);
    try {
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      };

      if (tipo === 'boleto') {
        const r = await fetch('/api/v1/integrations/banking/boleto/generate', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            bank_code: '077',
            payer_name: receivable.customer_name || receivable.description || 'Cliente',
            payer_document: receivable.customer_document || receivable.client_document || '',
            amount: valor,
            due_date: receivable.due_date || new Date().toISOString().split('T')[0],
            description: receivable.description || 'Cobrança Conecta Mais',
            receivable_id: receivable.id,
            payer_city: 'Manaus',
            payer_state: 'AM',
            payer_zip: '69000000',
            payer_address: 'Endereço não informado',
            payer_number: 'S/N',
            payer_neighborhood: 'Centro',
          }),
        });
        const d = await r.json();
        if (d.success || d.boleto_id) {
          // Buscar detalhes completos do boleto (barcode + linha digitável)
          let barcode = d.barcode || '';
          let digitable_line = d.digitable_line || '';
          if (d.boleto_id && (!barcode || !digitable_line)) {
            try {
              const r2 = await fetch(
                `/api/v1/integrations/banking/boleto/${d.boleto_id}`,
                { headers: { Authorization: `Bearer ${getToken()}` } }
              );
              const d2 = await r2.json();
              barcode = d2.barcode || barcode;
              digitable_line = d2.digitable_line || d2.linha_digitavel || digitable_line;
            } catch { /* usa dados da geração */ }
          }
          setCobrancaData({
            tipo: 'boleto',
            barcode,
            digitable_line,
            boleto_id: d.boleto_id,
            valor,
          });
          setCobrancaMsg({ ok: true, text: 'Boleto gerado com sucesso!' });
        } else {
          setCobrancaMsg({ ok: false, text: d.detail || d.error || JSON.stringify(d) });
        }
      } else {
        const r = await fetch('/api/v1/integrations/banking/pix/generate', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            bank_code: '077',
            amount: valor,
            description: receivable.description || 'Cobrança PIX',
            payer_name: receivable.customer_name || 'Cliente',
            payer_document: receivable.customer_document || receivable.client_document || '',
            receivable_id: receivable.id,
          }),
        });
        const d = await r.json();
        if (d.success || d.charge_id || d.pix_copy_paste) {
          setCobrancaData({
            tipo: 'pix',
            pix_copy_paste: d.pix_copy_paste || '',
            charge_id: d.charge_id,
            valor,
          });
          setCobrancaMsg({ ok: true, text: 'PIX gerado com sucesso!' });
        } else {
          setCobrancaMsg({ ok: false, text: d.detail || d.error || JSON.stringify(d) });
        }
      }
    } catch (e) {
      setCobrancaMsg({ ok: false, text: `Erro: ${e}` });
    } finally {
      setCobrancaLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCobrancaMsg({ ok: true, text: 'Copiado!' });
    setTimeout(() => setCobrancaMsg(null), 2000);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Detalhes da Conta a Receber" size="lg">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Descricao</p>
            <p className="font-medium">{receivable.description || '-'}</p>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Cliente</p>
            <p className="font-medium">{receivable.customer_name || '-'}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Valor</p>
            <p className="text-xl font-semibold font-mono tabular-nums">{formatCurrency(valor || receivable.amount)}</p>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Vencimento</p>
            <p className="font-medium">{formatDate(receivable.due_date)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Status</p>
            <div className="mt-1">{getStatusBadge(receivable.status)}</div>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Categoria</p>
            <p className="font-medium">
              {receivable.category ? CATEGORY_LABELS[receivable.category] || receivable.category : '-'}
            </p>
          </div>
        </div>

        {receivable.paid_at && (
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Recebido em</p>
            <p className="font-medium">{formatDate(receivable.paid_at)}</p>
          </div>
        )}

        {receivable.observacoes && (
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Observações</p>
            <p className="font-medium whitespace-pre-wrap">{receivable.observacoes}</p>
          </div>
        )}

        {/* Dados de cobrança existentes */}
        {(temBoleto || temPix) && !cobrancaData && (
          <div className="border-t border-gray-200 pt-4 space-y-3">
            <p className="text-sm font-medium text-gray-700 flex items-center gap-1"><Landmark className="w-4 h-4" /> Cobrança Inter</p>

            {temBoleto && (
              <div className="space-y-1">
                <p className="text-xs text-gray-500">Linha digitável do boleto:</p>
                <div className="bg-gray-50 rounded p-2 text-xs font-mono break-all">
                  {receivable.boleto_digitable_line || receivable.boleto_barcode || '-'}
                </div>
                <button
                  onClick={() =>
                    copyToClipboard(receivable.boleto_digitable_line || receivable.boleto_barcode || '')
                  }
                  className="w-full py-1.5 text-xs border border-gray-300 rounded text-gray-600 hover:bg-gray-50 inline-flex items-center justify-center gap-1"
                >
                  <Copy className="w-3 h-3" /> Copiar boleto
                </button>
              </div>
            )}

            {temPix && receivable.pix_copy_paste && (
              <div className="space-y-1">
                <p className="text-xs text-gray-500">PIX Copia e Cola:</p>
                <div className="bg-gray-50 rounded p-2 text-xs font-mono break-all">
                  {receivable.pix_copy_paste.substring(0, 80)}...
                </div>
                <button
                  onClick={() => copyToClipboard(receivable.pix_copy_paste)}
                  className="w-full py-1.5 text-xs border border-gray-300 rounded text-gray-600 hover:bg-gray-50 inline-flex items-center justify-center gap-1"
                >
                  <Copy className="w-3 h-3" /> Copiar PIX
                </button>
              </div>
            )}
          </div>
        )}

        {/* Gerar nova cobrança */}
        {isPendente && (
          <div className="border-t border-gray-200 pt-4">
            <p className="text-sm font-medium text-gray-700 mb-3 flex items-center gap-1"><Landmark className="w-4 h-4" /> Gerar Cobrança — Banco Inter</p>

            {!cobrancaData ? (
              <div className="flex gap-2">
                <button
                  onClick={() => handleGerarCobranca('boleto')}
                  disabled={cobrancaLoading}
                  className="flex-1 py-2 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 transition-colors"
                >
                  {cobrancaLoading ? '...' : <span className="inline-flex items-center gap-1"><Receipt className="w-4 h-4" /> Boleto</span>}
                </button>
                <button
                  onClick={() => handleGerarCobranca('pix')}
                  disabled={cobrancaLoading}
                  className="flex-1 py-2 text-sm bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 transition-colors"
                >
                  {cobrancaLoading ? '...' : <span className="inline-flex items-center gap-1"><Zap className="w-4 h-4" /> PIX</span>}
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {cobrancaData.tipo === 'boleto' && (
                  <>
                    <p className="text-xs text-gray-500">Linha digitável:</p>
                    <div className="bg-gray-50 rounded p-2 text-xs font-mono break-all">
                      {cobrancaData.digitable_line || cobrancaData.barcode || '-'}
                    </div>
                    <button
                      onClick={() =>
                        copyToClipboard(cobrancaData.digitable_line || cobrancaData.barcode || '')
                      }
                      className="w-full py-1.5 text-xs border border-gray-300 rounded text-gray-600 hover:bg-gray-50 inline-flex items-center justify-center gap-1"
                    >
                      <Copy className="w-3 h-3" /> Copiar código
                    </button>
                  </>
                )}
                {cobrancaData.tipo === 'pix' && (
                  <>
                    <p className="text-xs text-gray-500">PIX Copia e Cola:</p>
                    <div className="bg-gray-50 rounded p-2 text-xs font-mono break-all">
                      {(cobrancaData.pix_copy_paste || '').substring(0, 80)}...
                    </div>
                    <button
                      onClick={() => copyToClipboard(cobrancaData.pix_copy_paste || '')}
                      className="w-full py-1.5 text-xs border border-gray-300 rounded text-gray-600 hover:bg-gray-50 inline-flex items-center justify-center gap-1"
                    >
                      <Copy className="w-3 h-3" /> Copiar PIX
                    </button>
                  </>
                )}
                <button
                  onClick={() => { setCobrancaData(null); setCobrancaMsg(null); }}
                  className="w-full py-1 text-xs text-gray-400 hover:text-gray-600"
                >
                  Gerar outra cobrança
                </button>
              </div>
            )}

            {cobrancaMsg && (
              <p className={`text-xs mt-2 inline-flex items-center gap-1 ${cobrancaMsg.ok ? 'text-emerald-500' : 'text-red-500'}`}>
                {cobrancaMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {cobrancaMsg.text}
              </p>
            )}
          </div>
        )}
      </div>

      <ModalFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </ModalFooter>
    </Modal>
  );
}
