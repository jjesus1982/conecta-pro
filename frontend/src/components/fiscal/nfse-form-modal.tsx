'use client';

import { AlertCircle, Loader2 } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { listarTomadoresNFSe } from '@/services/government/nfse.service';

interface NfseFormData {
  numero_rps: string;
  serie_rps: string;
  tomador_cnpj: string;
  tomador_nome: string;
  tomador_logradouro: string;
  tomador_numero: string;
  tomador_bairro: string;
  tomador_cep: string;
  descricao_servico: string;
  valor_servico: number;
  aliquota_iss: number;
  codigo_servico: string;
}

interface Tomador {
  cnpj: string;
  razao_social: string;
  logradouro: string;
  numero: string;
  bairro: string;
  cep: string;
  codigo_municipio: string;
}

interface NfseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: NfseFormData) => void;
  isLoading?: boolean;
}

const defaultFormData: NfseFormData = {
  numero_rps: '',
  serie_rps: '',
  tomador_cnpj: '',
  tomador_nome: '',
  tomador_logradouro: '',
  tomador_numero: '',
  tomador_bairro: '',
  tomador_cep: '',
  descricao_servico: '',
  valor_servico: 0,
  aliquota_iss: 0,
  codigo_servico: '',
};

export function NfseFormModal({ isOpen, onClose, onSubmit, isLoading = false }: NfseFormModalProps) {
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState<NfseFormData>(defaultFormData);
  const [tomadores, setTomadores] = useState<Tomador[]>([]);
  const [tomadorSel, setTomadorSel] = useState<string>('');
  const [loadingTomadores, setLoadingTomadores] = useState(false);

  // Reset form when modal opens
  const resetForm = useCallback(() => {
    setFormData(defaultFormData);
    setTomadorSel('');
    setError(null);
  }, []);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Form sync
      resetForm();
      // Carrega condominios (tomadores) das notas ja emitidas
      setLoadingTomadores(true);
      listarTomadoresNFSe()
        .then((lista) => setTomadores(lista))
        .catch(() => setTomadores([]))
        .finally(() => setLoadingTomadores(false));
    }
  }, [isOpen, resetForm]);

  const handleSelectTomador = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const cnpj = e.target.value;
    setTomadorSel(cnpj);
    const t = tomadores.find((x) => x.cnpj === cnpj);
    if (!t) return;
    setFormData((prev) => ({
      ...prev,
      tomador_cnpj: t.cnpj,
      tomador_nome: t.razao_social,
      tomador_logradouro: t.logradouro,
      tomador_numero: t.numero,
      tomador_bairro: t.bairro,
      tomador_cep: t.cep,
    }));
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target;
    if (type === 'number') {
      setFormData((prev) => ({ ...prev, [name]: parseFloat(value) || 0 }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.numero_rps.trim()) {
      setError('Numero do RPS e obrigatorio');
      return;
    }
    if (!formData.tomador_cnpj.trim()) {
      setError('CNPJ do tomador e obrigatorio');
      return;
    }
    if (!formData.descricao_servico.trim()) {
      setError('Descricao do servico e obrigatoria');
      return;
    }
    if (formData.valor_servico <= 0) {
      setError('Valor do servico deve ser maior que zero');
      return;
    }

    onSubmit(formData);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Emitir NFS-e"
      description="Preencha os dados para emissao da Nota Fiscal de Servico"
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-start gap-2 text-red-500 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
            Condominio (preenche o tomador automaticamente)
          </label>
          <select
            value={tomadorSel}
            onChange={handleSelectTomador}
            disabled={loadingTomadores}
            aria-label="Selecionar condominio"
            className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
          >
            <option value="">
              {loadingTomadores
                ? 'Carregando condominios...'
                : tomadores.length
                  ? '— Selecione um condominio —'
                  : 'Nenhum condominio encontrado (preencha manualmente)'}
            </option>
            {tomadores.map((t) => (
              <option key={t.cnpj} value={t.cnpj}>
                {t.razao_social}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Numero RPS *
            </label>
            <Input
              name="numero_rps"
              value={formData.numero_rps}
              onChange={handleChange}
              placeholder="Ex: 001"
              required
             aria-label="Ex: 001" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Serie RPS
            </label>
            <Input
              name="serie_rps"
              value={formData.serie_rps}
              onChange={handleChange}
              placeholder="Ex: A"
             aria-label="Ex: A" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              CNPJ do Tomador *
            </label>
            <Input
              name="tomador_cnpj"
              value={formData.tomador_cnpj}
              onChange={handleChange}
              placeholder="00.000.000/0000-00"
              required
             aria-label="00.000.000/0000-00" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Nome do Tomador *
            </label>
            <Input
              name="tomador_nome"
              value={formData.tomador_nome}
              onChange={handleChange}
              placeholder="Razao Social"
              required
             aria-label="Razao Social" />
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <div className="col-span-2">
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Logradouro
            </label>
            <Input
              name="tomador_logradouro"
              value={formData.tomador_logradouro}
              onChange={handleChange}
              placeholder="Rua / Av."
             aria-label="Logradouro" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Numero
            </label>
            <Input
              name="tomador_numero"
              value={formData.tomador_numero}
              onChange={handleChange}
              placeholder="S/N"
             aria-label="Numero" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              CEP
            </label>
            <Input
              name="tomador_cep"
              value={formData.tomador_cep}
              onChange={handleChange}
              placeholder="69000-000"
             aria-label="CEP" />
          </div>
        </div>

        <div>
          <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
            Bairro
          </label>
          <Input
            name="tomador_bairro"
            value={formData.tomador_bairro}
            onChange={handleChange}
            placeholder="Bairro"
           aria-label="Bairro" />
        </div>

        <div>
          <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
            Descricao do Servico *
          </label>
          <textarea
            name="descricao_servico"
            value={formData.descricao_servico}
            onChange={handleChange}
            rows={3}
            placeholder="Descreva o servico prestado..."
            className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] resize-none"
            required
           aria-label="Descreva o servico prestado..." />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Valor do Servico (R$) *
            </label>
            <Input
              type="number"
              name="valor_servico"
              value={formData.valor_servico}
              onChange={handleChange}
              min={0}
              step={0.01}
              placeholder="0,00"
              required
             aria-label="0,00" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Aliquota ISS (%)
            </label>
            <Input
              type="number"
              name="aliquota_iss"
              value={formData.aliquota_iss}
              onChange={handleChange}
              min={0}
              max={100}
              step={0.01}
              placeholder="0,00"
             aria-label="0,00" />
          </div>
          <div>
            <label className="block text-sm text-[hsl(var(--muted-foreground))] mb-1">
              Codigo Servico
            </label>
            <Input
              name="codigo_servico"
              value={formData.codigo_servico}
              onChange={handleChange}
              placeholder="Ex: 17.01"
             aria-label="Ex: 17.01" />
          </div>
        </div>

        <ModalFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Cancelar
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Emitir NFS-e
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
