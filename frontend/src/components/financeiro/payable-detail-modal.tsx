'use client';

import { useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useProcessPayment } from '@/hooks/financial/useFinancial';
import { Landmark, CheckCircle2, XCircle, CreditCard, PenLine } from 'lucide-react';

interface PayableDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  payable: any;
  onSuccess?: () => void;
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
      return <Badge className="bg-yellow-100 text-yellow-800">Pendente</Badge>;
    case 'overdue':
      return <Badge className="bg-red-100 text-red-800">Atrasada</Badge>;
    case 'paid':
      return <Badge className="bg-green-100 text-green-800">Paga</Badge>;
    case 'cancelled':
      return <Badge variant="secondary">Cancelada</Badge>;
    default:
      return <Badge variant="outline">{status || '-'}</Badge>;
  }
};

const CATEGORY_LABELS: Record<string, string> = {
  utilities: 'Utilidades',
  rent: 'Aluguel',
  payroll: 'Folha de Pagamento',
  supplies: 'Suprimentos',
  services: 'Servicos',
  taxes: 'Impostos',
  other: 'Outros',
};

export function PayableDetailModal({ isOpen, onClose, payable, onSuccess }: PayableDetailModalProps) {
  const [showPayment, setShowPayment] = useState(false);
  const [paymentForm, setPaymentForm] = useState({
    codigo_barras: '',
    via_inter: true,
    data_pagamento: new Date().toISOString().split('T')[0],
  });
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [paymentMsg, setPaymentMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const processPayment = useProcessPayment();

  const handlePagar = async () => {
    setPaymentLoading(true);
    setPaymentMsg(null);
    try {
      if (paymentForm.via_inter && paymentForm.codigo_barras) {
        // Pagar via Inter API
        const token = localStorage.getItem('token') || '';
        const r = await fetch('/api/v1/banking/payment/barcode', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            codigo_barras: paymentForm.codigo_barras,
            data_pagamento: paymentForm.data_pagamento,
            descricao: payable?.description || '',
            payable_id: payable?.id,
          }),
        });
        const d = await r.json();
        if (d.success) {
          setPaymentMsg({ ok: true, text: 'Pagamento realizado via Banco Inter!' });
          setTimeout(() => {
            onClose();
            onSuccess?.();
          }, 2000);
        } else {
          setPaymentMsg({ ok: false, text: msgFromDetail(d.detail) || JSON.stringify(d) });
        }
      } else {
        // Registrar pagamento manual
        await processPayment.mutateAsync({
          installmentId: payable?.id,
          data: {
            installment_id: payable?.id,
            paid_value: parseFloat(payable?.net_value || payable?.amount || '0'),
            payment_date: paymentForm.data_pagamento ?? '',
          },
        });
        setPaymentMsg({ ok: true, text: 'Pagamento registrado!' });
        setTimeout(() => {
          onClose();
          onSuccess?.();
        }, 2000);
      }
    } catch (e) {
      setPaymentMsg({ ok: false, text: `Erro: ${e}` });
    } finally {
      setPaymentLoading(false);
    }
  };

  if (!payable) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Detalhes da Conta a Pagar" size="lg">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Descricao</p>
            <p className="font-medium">{payable.description || '-'}</p>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Fornecedor</p>
            <p className="font-medium">{payable.supplier_name || '-'}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Valor</p>
            <p className="text-xl font-semibold font-mono tabular-nums">{formatCurrency(payable.amount)}</p>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Vencimento</p>
            <p className="font-medium">{formatDate(payable.due_date)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Status</p>
            <div className="mt-1">{getStatusBadge(payable.status)}</div>
          </div>
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Categoria</p>
            <p className="font-medium">
              {payable.category ? CATEGORY_LABELS[payable.category] || payable.category : '-'}
            </p>
          </div>
        </div>

        {payable.paid_at && (
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Pago em</p>
            <p className="font-medium">{formatDate(payable.paid_at)}</p>
          </div>
        )}

        {payable.observacoes && (
          <div>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Observações</p>
            <p className="font-medium whitespace-pre-wrap">{payable.observacoes}</p>
          </div>
        )}

        {/* Botão Pagar — apenas para pendentes */}
        {(payable?.status === 'pending' ||
          payable?.status === 'pendente' ||
          payable?.status === 'overdue') && (
          <div className="mt-4 border-t border-gray-200 pt-4">
            {!showPayment ? (
              <button
                onClick={() => setShowPayment(true)}
                className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
              >
                <CreditCard className="w-4 h-4" /> Registrar Pagamento
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">Registrar Pagamento</p>

                <div className="flex gap-2">
                  <button
                    onClick={() => setPaymentForm((f) => ({ ...f, via_inter: true }))}
                    className={`flex-1 py-2 text-sm rounded-lg border transition-colors ${
                      paymentForm.via_inter
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-gray-600 border-gray-300'
                    }`}
                  >
                    <span className="inline-flex items-center gap-1"><Landmark className="w-4 h-4" /> Via Inter</span>
                  </button>
                  <button
                    onClick={() => setPaymentForm((f) => ({ ...f, via_inter: false }))}
                    className={`flex-1 py-2 text-sm rounded-lg border transition-colors ${
                      !paymentForm.via_inter
                        ? 'bg-gray-800 text-white border-gray-800'
                        : 'bg-white text-gray-600 border-gray-300'
                    }`}
                  >
                    <span className="inline-flex items-center gap-1"><PenLine className="w-4 h-4" /> Manual</span>
                  </button>
                </div>

                {paymentForm.via_inter && (
                  <input
                    type="text"
                    placeholder="Código de barras do boleto"
                    value={paymentForm.codigo_barras}
                    onChange={(e) =>
                      setPaymentForm((f) => ({ ...f, codigo_barras: e.target.value }))
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                )}

                <input
                  type="date"
                  value={paymentForm.data_pagamento}
                  onChange={(e) =>
                    setPaymentForm((f) => ({ ...f, data_pagamento: e.target.value }))
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />

                {paymentMsg && (
                  <p
                    className={`text-sm inline-flex items-center gap-1 ${
                      paymentMsg.ok ? 'text-emerald-500' : 'text-red-500'
                    }`}
                  >
                    {paymentMsg.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    {paymentMsg.text}
                  </p>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => setShowPayment(false)}
                    className="flex-1 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={handlePagar}
                    disabled={paymentLoading}
                    className="flex-1 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {paymentLoading ? 'Pagando...' : <span className="inline-flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Confirmar</span>}
                  </button>
                </div>
              </div>
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
