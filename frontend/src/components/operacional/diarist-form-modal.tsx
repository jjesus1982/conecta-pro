'use client';

import { AlertCircle, Loader2, User, Briefcase, DollarSign } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState, useEffect } from 'react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { getErrorMessage } from '@/lib/api';
import type { DiaristFormData } from './diarist-form-types';
import { INITIAL_FORM_DATA, formatCPF, formatCEP, formatPhone } from './diarist-form-types';
import { DiaristDadosPessoaisTab } from './diarist-dados-pessoais-tab';
import { DiaristServicosTab } from './diarist-servicos-tab';
import { DiaristPagamentoTab } from './diarist-pagamento-tab';

interface DiaristFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editData?: any | null;  // quando presente, o modal edita (PUT) em vez de criar (POST)
}

type TabId = 'dados' | 'servicos' | 'pagamento';

const TABS = [
  { id: 'dados' as const, label: 'Dados Pessoais', icon: User },
  { id: 'servicos' as const, label: 'Servicos', icon: Briefcase },
  { id: 'pagamento' as const, label: 'Pagamento', icon: DollarSign },
];

export function DiaristFormModal({ isOpen, onClose, onSuccess, editData }: DiaristFormModalProps) {
  const isEdit = !!editData?.id;
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingCPF, setIsFetchingCPF] = useState(false);
  const [cpfStatus, setCpfStatus] = useState<'idle' | 'found' | 'not_found'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('dados');
  const [formData, setFormData] = useState<DiaristFormData>({ ...INITIAL_FORM_DATA });

  useEffect(() => {
    if (isOpen) {
      if (editData) {
        // Edição: prefill só com as chaves que o formulário conhece (ignora id/status/etc.)
        const prefilled: any = { ...INITIAL_FORM_DATA };
        for (const k of Object.keys(INITIAL_FORM_DATA)) {
          if (editData[k] !== undefined && editData[k] !== null) prefilled[k] = editData[k];
        }
        setFormData(prefilled);
      } else {
        setFormData({ ...INITIAL_FORM_DATA });
      }
      setError(null);
      setActiveTab('dados');
    }
  }, [isOpen, editData]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setFormData((prev) => ({ ...prev, [name]: checked }));
    } else if (type === 'number') {
      setFormData((prev) => ({ ...prev, [name]: parseFloat(value) || 0 }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleTipoServicoChange = (tipo: string) => {
    setFormData((prev) => ({
      ...prev,
      tipos_servico: prev.tipos_servico.includes(tipo)
        ? prev.tipos_servico.filter((t) => t !== tipo)
        : [...prev.tipos_servico, tipo],
    }));
  };

  const handleDiaDisponivelChange = (dia: string) => {
    setFormData((prev) => ({
      ...prev,
      dias_disponiveis: prev.dias_disponiveis.includes(dia)
        ? prev.dias_disponiveis.filter((d) => d !== dia)
        : [...prev.dias_disponiveis, dia],
    }));
  };

  const fetchCPFData = async (cpf: string) => {
    const cleaned = cpf.replace(/\D/g, '');
    if (cleaned.length !== 11) return;

    setIsFetchingCPF(true);
    setCpfStatus('idle');

    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`/api/v1/operacional/diaristas/consulta-cpf/${cleaned}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        if (data.found && data.nome) {
          setFormData((prev) => ({
            ...prev,
            nome: prev.nome || data.nome,
            email: prev.email || data.email || '',
            telefone: prev.telefone || data.telefone || '',
            data_nascimento: prev.data_nascimento || data.data_nascimento || '',
          }));
          setCpfStatus('found');
          if (data.aviso) {
            setError(data.aviso);
          }
        } else {
          setCpfStatus('not_found');
        }
      } else {
        setCpfStatus('not_found');
      }
    } catch {
      setCpfStatus('not_found');
    } finally {
      setIsFetchingCPF(false);
    }
  };

  const handleCPFChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatCPF(e.target.value);
    setFormData((prev) => ({ ...prev, cpf: formatted }));
    setCpfStatus('idle');
    const cleaned = formatted.replace(/\D/g, '');
    if (cleaned.length === 11) {
      fetchCPFData(cleaned);
    }
  };

  const handleCEPChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatCEP(e.target.value);
    setFormData((prev) => ({ ...prev, cep: formatted }));
  };

  const handlePhoneChange = (field: 'telefone' | 'telefone_emergencia') => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const formatted = formatPhone(e.target.value);
    setFormData((prev) => ({ ...prev, [field]: formatted }));
  };

  const validateForm = (): boolean => {
    if (!formData.nome.trim()) {
      setError('Nome e obrigatorio');
      setActiveTab('dados');
      return false;
    }
    if (!formData.cpf || formData.cpf.replace(/\D/g, '').length !== 11) {
      setError('CPF invalido');
      setActiveTab('dados');
      return false;
    }
    if (!formData.pix || !formData.pix.trim()) {
      setError('Chave PIX é obrigatória — sem PIX o diarista fica impagável.');
      setActiveTab('pagamento');
      return false;
    }
    if (!formData.telefone?.trim() && !formData.email?.trim()) {
      setError('Informe ao menos um contato: telefone ou e-mail.');
      setActiveTab('dados');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      // Cadastro ÚNICO de diarista = tabela diaria_diaristas (a que alimenta o pagamento
      // VT+VR e as diárias). Só os campos que ela guarda e que o pagamento precisa.
      const apiData: Record<string, unknown> = {
        nome: formData.nome.trim(),
        cpf: formData.cpf.replace(/\D/g, ''),
        pix: formData.pix?.trim() || undefined,
        telefone: formData.telefone?.trim() || undefined,
        email: formData.email?.trim() || undefined,
      };

      const response = await fetch(
        isEdit
          ? `/api/v1/operacional/diarias/diaristas/${editData.id}`
          : '/api/v1/operacional/diarias/diaristas',
        {
          method: isEdit ? 'PATCH' : 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(apiData),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(msgFromDetail(errorData.detail) || `Erro ${response.status}`);
      }

      onSuccess();
      onClose();
    } catch (err) {
      const msg = getErrorMessage(err);
      // O 403 do backend vinha como "Role requerida: admin, sindico" (desatualizado —
      // o backend hoje aceita gestão operacional). Exibir mensagem honesta e atual.
      setError(
        /role requerida/i.test(msg)
          ? 'Sem permissão para cadastrar diarista. Disponível para gestão operacional e administradores.'
          : msg
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? 'Editar Diarista' : 'Novo Diarista'}
      description={isEdit ? 'Atualize os dados do diarista' : 'Cadastre um novo diarista no sistema'}
      size="xl"
    >
      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-start gap-2 text-red-500 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span className="flex-1">{error}</span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-[hsl(var(--border))]">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-[hsl(var(--primary))] text-[hsl(var(--primary))]'
                  : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="min-h-[350px]">
          {activeTab === 'dados' && (
            <DiaristDadosPessoaisTab
              formData={formData}
              onChange={handleChange}
              onCPFChange={handleCPFChange}
              onCEPChange={handleCEPChange}
              onPhoneChange={handlePhoneChange}
              isFetchingCPF={isFetchingCPF}
              cpfStatus={cpfStatus}
            />
          )}
          {activeTab === 'servicos' && (
            <DiaristServicosTab
              formData={formData}
              onChange={handleChange}
              onTipoServicoChange={handleTipoServicoChange}
              onDiaDisponivelChange={handleDiaDisponivelChange}
            />
          )}
          {activeTab === 'pagamento' && (
            <DiaristPagamentoTab
              formData={formData}
              onChange={handleChange}
            />
          )}
        </div>

        <ModalFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={isLoading}>
            {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {isEdit ? 'Salvar alterações' : 'Cadastrar Diarista'}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
