'use client';

import { useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { cn, formatCurrency, formatDate } from '@/lib/utils';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

interface BankTransactionDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  transaction: any;
  onSuccess?: () => void;
}

const CATEGORIAS = [
  { value: 'salario', label: 'Salário / Pró-labore' },
  { value: 'adiantamento', label: 'Adiantamento a funcionário' },
  { value: 'reembolso', label: 'Reembolso de despesas' },
  { value: 'taxa_bancaria', label: 'Tarifas bancárias' },
  { value: 'imposto', label: 'Impostos e guias' },
  { value: 'servico_sem_nf', label: 'Serviço sem obrigação fiscal' },
  { value: 'transferencia_interna', label: 'Transferência interna' },
  { value: 'outros', label: 'Outros' },
];

export function BankTransactionDetailModal({
  isOpen,
  onClose,
  transaction,
  onSuccess,
}: BankTransactionDetailModalProps) {
  const [showJustif, setShowJustif] = useState(false);
  const [justifForm, setJustifForm] = useState({
    categoria: 'outros',
    descricao: '',
    responsavel: 'Jordan Jesus',
  });
  const [justifLoading, setJustifLoading] = useState(false);
  const [justifMsg, setJustifMsg] = useState('');

  const handleJustificar = async () => {
    if (justifForm.descricao.length < 10) {
      setJustifMsg('❌ Descrição muito curta (mínimo 10 caracteres)');
      return;
    }
    setJustifLoading(true);
    try {
      const token =
        typeof window !== 'undefined' ? localStorage.getItem('token') || '' : '';
      const txId = transaction?.id;
      const r = await fetch(`/api/v1/financial/conciliar/${txId}/justificar`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          justificativa: justifForm.descricao,
          categoria: justifForm.categoria,
          responsavel: justifForm.responsavel,
        }),
      });
      const d = await r.json();
      if (d.status === 'justificado') {
        setJustifMsg('✅ Justificativa registrada — Lucro Real OK');
        setTimeout(() => {
          onClose();
          onSuccess?.();
        }, 1800);
      } else {
        setJustifMsg(`❌ ${d.detail || d.erro || JSON.stringify(d)}`);
      }
    } catch (e) {
      setJustifMsg(`❌ Erro: ${String(e)}`);
    } finally {
      setJustifLoading(false);
    }
  };

  const handleClose = () => {
    setShowJustif(false);
    setJustifForm({ categoria: 'outros', descricao: '', responsavel: 'Jordan Jesus' });
    setJustifMsg('');
    onClose();
  };

  if (!transaction) return null;

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'credit':
        return 'bg-green-500/10 text-green-500 border-green-500/30';
      case 'debit':
        return 'bg-red-500/10 text-red-500 border-red-500/30';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/30';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'conciliado':
      case 'matched':
        return 'bg-green-500/10 text-green-500 border-green-500/30';
      case 'justificado':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/30';
      case 'pendente':
      case 'unmatched':
      case 'pending':
        return 'bg-orange-500/10 text-orange-500 border-orange-500/30';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/30';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'conciliado':
      case 'matched':
        return 'Conciliado';
      case 'justificado':
        return 'Justificado';
      case 'pendente':
      case 'pending':
        return 'Pendente';
      default:
        return status || 'Pendente';
    }
  };

  const needsJustification =
    transaction.requires_justification === true ||
    (transaction.transaction_type === 'debit' &&
      transaction.reconciliation_status !== 'conciliado' &&
      transaction.reconciliation_status !== 'justificado');

  const fields = [
    {
      label: 'Data',
      value: transaction.transaction_date
        ? formatDate(transaction.transaction_date)
        : transaction.date
          ? formatDate(transaction.date)
          : '-',
    },
    {
      label: 'Descrição',
      value: transaction.description || '-',
    },
    {
      label: 'Valor',
      value: formatCurrency(Math.abs(transaction.amount || 0)),
      className:
        transaction.transaction_type === 'credit' ? 'text-green-500' : 'text-red-500',
    },
    {
      label: 'Tipo',
      value: transaction.transaction_type === 'credit' ? 'Crédito' : 'Débito',
      badge: true,
      badgeColor: getTypeColor(transaction.transaction_type),
    },
    {
      label: 'Banco',
      value: transaction.bank_name || transaction.bank_account_name || '-',
    },
    {
      label: 'Status',
      value: getStatusLabel(
        transaction.reconciliation_status || transaction.match_status || 'pendente'
      ),
      badge: true,
      badgeColor: getStatusColor(
        transaction.reconciliation_status || transaction.match_status || 'pendente'
      ),
    },
    {
      label: 'Referência',
      value: transaction.reference || transaction.external_id || '-',
    },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Detalhes da Transação"
      description="Informações completas da transação bancária"
      size="md"
    >
      <div className="space-y-4">
        {/* Valor em destaque */}
        <div className="bg-[hsl(var(--muted))] rounded-lg p-4 text-center">
          <p className="text-sm text-[hsl(var(--muted-foreground))] mb-1">Valor</p>
          <p
            className={cn(
              'font-data text-2xl font-semibold tabular-nums',
              transaction.transaction_type === 'credit' ? 'text-green-500' : 'text-red-500'
            )}
          >
            {transaction.transaction_type === 'credit' ? '+' : '-'}
            {formatCurrency(Math.abs(transaction.amount || 0))}
          </p>
        </div>

        {/* Campos */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {fields.map((field) => (
            <div key={field.label}>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mb-1">{field.label}</p>
              {field.badge ? (
                <span
                  className={cn(
                    'inline-flex px-2 py-1 text-xs font-medium rounded-full border',
                    field.badgeColor
                  )}
                >
                  {field.value}
                </span>
              ) : (
                <p
                  className={cn(
                    'text-sm font-medium text-[hsl(var(--foreground))]',
                    field.className
                  )}
                >
                  {field.value}
                </p>
              )}
            </div>
          ))}
        </div>

        {/* Justificativa — Lucro Real */}
        {needsJustification && (
          <div className="mt-4 border-t border-orange-200 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-orange-500" />
              <p className="text-sm font-medium text-orange-700">
                Saída sem nota fiscal — Justificativa obrigatória (Lucro Real)
              </p>
            </div>

            {!showJustif ? (
              <button
                onClick={() => setShowJustif(true)}
                className="w-full bg-orange-500 text-white py-2 px-4 rounded-lg text-sm font-medium hover:bg-orange-600 transition-colors"
              >
                📝 Registrar Justificativa
              </button>
            ) : (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Categoria</label>
                  <select
                    value={justifForm.categoria}
                    onChange={(e) =>
                      setJustifForm((f) => ({ ...f, categoria: e.target.value }))
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800"
                  >
                    {CATEGORIAS.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Descrição detalhada{' '}
                    <span className="text-orange-500">
                      ({justifForm.descricao.length}/10 mín.)
                    </span>
                  </label>
                  <textarea
                    rows={3}
                    value={justifForm.descricao}
                    onChange={(e) =>
                      setJustifForm((f) => ({ ...f, descricao: e.target.value }))
                    }
                    placeholder="Descreva o motivo desta saída sem nota fiscal..."
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-400"
                  />
                </div>

                <div>
                  <label className="block text-xs text-gray-500 mb-1">Responsável</label>
                  <input
                    type="text"
                    value={justifForm.responsavel}
                    onChange={(e) =>
                      setJustifForm((f) => ({ ...f, responsavel: e.target.value }))
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  />
                </div>

                {justifMsg && (
                  <p
                    className={cn(
                      'text-sm',
                      justifMsg.startsWith('✅') ? 'text-green-600' : 'text-red-600'
                    )}
                  >
                    {justifMsg}
                  </p>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setShowJustif(false);
                      setJustifMsg('');
                    }}
                    className="flex-1 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
                  >
                    Cancelar
                  </button>
                  <button
                    onClick={handleJustificar}
                    disabled={justifLoading || justifForm.descricao.length < 10}
                    className="flex-1 py-2 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {justifLoading ? 'Salvando...' : <span className="inline-flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Confirmar</span>}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex justify-end pt-4 border-t border-[hsl(var(--border))]">
          <Button variant="outline" onClick={handleClose}>
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  );
}
