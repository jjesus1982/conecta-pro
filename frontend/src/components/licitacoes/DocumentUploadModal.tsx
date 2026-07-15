'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import { X, Upload, FileUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

const GED_UPLOAD_URL = '/api/v1/ged/documents/upload';
const GED_LICITACOES_FOLDER = 'abcbebd2-88af-419e-8907-43b11f38f90b';
const ACCEPT_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.xlsx,.xls';
const MAX_SIZE_MB = 10;

interface DocumentUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => void;
  isLoading?: boolean;
}

const defaultFormData = {
  tipo_documento: 'contrato_social',
  nome: '',
  data_validade: '',
  observacoes: '',
};

export function DocumentUploadModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: DocumentUploadModalProps) {
  const [formData, setFormData] = useState(defaultFormData);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetForm = useCallback(() => {
    setFormData(defaultFormData);
    setArquivo(null);
    setDragOver(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  useEffect(() => {
    if (!isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Form sync
      resetForm();
    }
  }, [isOpen, resetForm]);

  const handleFileSelect = (file: File) => {
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`Arquivo muito grande. Máximo: ${MAX_SIZE_MB}MB`, { duration: 5000 });
      return;
    }
    setArquivo(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!arquivo) {
      toast.error('Selecione um arquivo', { duration: 5000 });
      return;
    }
    setUploading(true);
    try {
      const token = typeof window !== 'undefined'
        ? (localStorage.getItem('access_token') || localStorage.getItem('token'))
        : null;
      const fd = new FormData();
      fd.append('file', arquivo);
      fd.append('title', formData.nome || arquivo.name);
      fd.append('folder_id', GED_LICITACOES_FOLDER);
      fd.append('category', 'comercial');
      fd.append('document_type', formData.tipo_documento);
      if (formData.observacoes) fd.append('description', formData.observacoes);
      const res = await fetch(GED_UPLOAD_URL, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao enviar arquivo', { duration: 5000 });
        return;
      }
      const gedDoc = await res.json();
      onSubmit({
        ...formData,
        arquivo_url: gedDoc.file_path || gedDoc.url || '',
        arquivo_nome: arquivo.name,
        arquivo_tamanho: arquivo.size,
      });
    } catch {
      toast.error('Erro de conexão', { duration: 5000 });
    } finally {
      setUploading(false);
    }
  };

  const tiposDocumento = [
    { value: 'contrato_social', label: 'Contrato Social' },
    { value: 'estatuto', label: 'Estatuto Social' },
    { value: 'ata_eleicao', label: 'Ata de Eleição' },
    { value: 'procuracao', label: 'Procuração' },
    { value: 'rg_cnh', label: 'RG/CNH' },
    { value: 'balanco_patrimonial', label: 'Balanço Patrimonial' },
    { value: 'declaracao_mei', label: 'Declaração MEI' },
    { value: 'alvara', label: 'Alvará de Funcionamento' },
    { value: 'certidao_cnd', label: 'Certidão Negativa' },
    { value: 'atestado_capacidade', label: 'Atestado de Capacidade Técnica' },
    { value: 'registro_profissional', label: 'Registro Profissional' },
    { value: 'outros', label: 'Outros' },
  ];

  const busy = isLoading || uploading;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload de Documento</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="tipo_documento">Tipo de Documento *</Label>
            <Select
              value={formData.tipo_documento}
              onValueChange={(value) =>
                setFormData({ ...formData, tipo_documento: value })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {tiposDocumento.map((tipo) => (
                  <SelectItem key={tipo.value} value={tipo.value}>
                    {tipo.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="nome">Nome/Descrição *</Label>
            <Input
              id="nome"
              value={formData.nome}
              onChange={(e) =>
                setFormData({ ...formData, nome: e.target.value })
              }
              required
              placeholder="Ex: Contrato Social Atualizado 2024"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="data_validade">Data de Validade</Label>
            <Input
              id="data_validade"
              type="date"
              value={formData.data_validade}
              onChange={(e) =>
                setFormData({ ...formData, data_validade: e.target.value })
              }
            />
            <p className="text-xs text-muted-foreground">
              Deixe em branco se o documento não possui validade
            </p>
          </div>

          <div className="space-y-2">
            <Label>Arquivo *</Label>
            <div
              className={`w-full border-2 border-dashed rounded-md p-4 text-center cursor-pointer transition-colors ${dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:border-primary/50'}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f); }}
            >
              {arquivo ? (
                <div className="flex items-center justify-center gap-2 text-sm">
                  <FileUp className="h-4 w-4 text-primary" />
                  <span className="font-medium text-primary truncate max-w-[220px]">{arquivo.name}</span>
                  <span className="text-muted-foreground">({(arquivo.size / 1024).toFixed(0)} KB)</span>
                  <button type="button" className="ml-1 text-muted-foreground hover:text-destructive" onClick={ev => { ev.stopPropagation(); setArquivo(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}>
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-1 text-muted-foreground">
                  <Upload className="h-6 w-6" />
                  <p className="text-sm">Clique ou arraste o arquivo aqui</p>
                  <p className="text-xs">PDF, DOC, DOCX, JPG, PNG, XLSX — máx. {MAX_SIZE_MB}MB</p>
                </div>
              )}
            </div>
            <input ref={fileInputRef} type="file" accept={ACCEPT_TYPES} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="observacoes">Observações</Label>
            <Textarea
              id="observacoes"
              value={formData.observacoes}
              onChange={(e) =>
                setFormData({ ...formData, observacoes: e.target.value })
              }
              placeholder="Informações adicionais sobre o documento"
              rows={3}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={busy}
            >
              <X className="h-4 w-4 mr-2" />
              Cancelar
            </Button>
            <Button type="submit" disabled={busy}>
              <Upload className="h-4 w-4 mr-2" />
              {busy ? 'Enviando...' : 'Enviar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
