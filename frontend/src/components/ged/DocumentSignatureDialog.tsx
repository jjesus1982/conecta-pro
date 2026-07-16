'use client';

import { PenTool, User, Mail, Phone, FileText, Calendar, Plus, X, Check, AlertCircle, Send } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState, useRef, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { documentSignatureService } from '@/services/ged/documentSignatureService';
import type { SignatureRole } from '@/types/generated/ged/schemas/signatureRole';
import type { SignatureType } from '@/types/generated/ged/schemas/signatureType';

interface DocumentSignatureDialogProps {
  documentId: string;
  open: boolean;
  onClose: () => void;
  mode?: 'request' | 'sign';
  signatureId?: string;
}

const SIGNATURE_ROLES: { value: SignatureRole; label: string }[] = [
  { value: 'parte', label: 'Parte' },
  { value: 'testemunha', label: 'Testemunha' },
  { value: 'aprovador', label: 'Aprovador' },
  { value: 'fiador', label: 'Fiador' },
  { value: 'representante', label: 'Representante' },
  { value: 'outro', label: 'Outro' },
];

const SIGNATURE_TYPES: { value: SignatureType; label: string }[] = [
  { value: 'simples', label: 'Simples' },
  { value: 'eletronica', label: 'Eletrônica' },
  { value: 'digital', label: 'Digital (ICP-Brasil)' },
  { value: 'biometrica', label: 'Biométrica' },
  { value: 'carimbo', label: 'Carimbo do Tempo' },
];

interface Signer {
  name: string;
  email: string;
  document?: string;
  phone?: string;
  role: SignatureRole;
  order: number;
}

export function DocumentSignatureDialog({
  documentId,
  open,
  onClose,
  mode = 'request',
  signatureId,
}: DocumentSignatureDialogProps) {
  const [signers, setSigners] = useState<Signer[]>([
    { name: '', email: '', role: 'parte', order: 1 },
  ]);
  const [sequential, setSequential] = useState(false);
  const [deadlineDays, setDeadlineDays] = useState(7);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // Canvas de assinatura
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [signatureData, setSignatureData] = useState('');

  useEffect(() => {
    if (mode === 'sign' && canvasRef.current) {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
      }
    }
  }, [mode]);

  const handleAddSigner = () => {
    setSigners([
      ...signers,
      { name: '', email: '', role: 'parte', order: signers.length + 1 },
    ]);
  };

  const handleRemoveSigner = (index: number) => {
    setSigners(signers.filter((_, i) => i !== index));
  };

  const handleSignerChange = (index: number, field: keyof Signer, value: any) => {
    const updated = [...signers];
    const current = updated[index];
    if (current) {
      updated[index] = { ...current, [field]: value };
    }
    setSigners(updated);
  };

  const handleRequestSignatures = async () => {
    // Validação
    const invalidSigner = signers.find((s) => !s.name || !s.email);
    if (invalidSigner) {
      toast.error('Preencha nome e email de todos os signatários');
      return;
    }

    setLoading(true);
    try {
      await documentSignatureService.requestSignature(documentId, {
        document_id: documentId,
        signers: signers.map((s) => ({
          signer_name: s.name,
          signer_email: s.email,
          signer_role: s.role,
        })),
        sequential,
        deadline_days: deadlineDays,
        message: message || undefined,
      });

      toast.success('Solicitações de assinatura enviadas');
      onClose();
    } catch (error: any) {
      toast.error('Erro ao solicitar assinaturas', {
        description: msgFromDetail(error.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  // Canvas handlers
  const startDrawing = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      setIsDrawing(true);
    }
  };

  const draw = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.lineTo(x, y);
      ctx.stroke();
    }
  };

  const stopDrawing = () => {
    setIsDrawing(false);
    if (canvasRef.current) {
      setSignatureData(canvasRef.current.toDataURL());
    }
  };

  const clearSignature = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      setSignatureData('');
    }
  };

  const handleSign = async () => {
    if (!signatureData) {
      toast.error('Por favor, desenhe sua assinatura');
      return;
    }

    if (!signatureId) {
      toast.error('ID de assinatura não informado');
      return;
    }

    setLoading(true);
    try {
      await documentSignatureService.sign(documentId, signatureId, {
        signature_data: signatureData,
      });

      toast.success('Documento assinado com sucesso');
      onClose();
    } catch (error: any) {
      toast.error('Erro ao assinar documento', {
        description: msgFromDetail(error.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {mode === 'request' ? 'Solicitar Assinaturas' : 'Assinar Documento'}
          </DialogTitle>
          <DialogDescription>
            {mode === 'request'
              ? 'Configure os signatários e envie solicitações de assinatura'
              : 'Desenhe sua assinatura no campo abaixo'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {mode === 'request' ? (
            <>
              {/* Lista de signatários */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-semibold">Signatários</Label>
                  <Button variant="outline" size="sm" onClick={handleAddSigner}>
                    <Plus className="h-4 w-4 mr-1" />
                    Adicionar
                  </Button>
                </div>

                {signers.map((signer, index) => (
                  <div key={index} className="p-4 border rounded-lg space-y-3">
                    <div className="flex items-center justify-between">
                      <Badge>Signatário {index + 1}</Badge>
                      {signers.length > 1 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveSigner(index)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-sm">Nome *</Label>
                        <Input
                          placeholder="Nome completo"
                          value={signer.name}
                          onChange={(e) => handleSignerChange(index, 'name', e.target.value)}
                        />
                      </div>

                      <div>
                        <Label className="text-sm">Email *</Label>
                        <Input
                          type="email"
                          placeholder="email@exemplo.com"
                          value={signer.email}
                          onChange={(e) => handleSignerChange(index, 'email', e.target.value)}
                        />
                      </div>

                      <div>
                        <Label className="text-sm">CPF/CNPJ</Label>
                        <Input
                          placeholder="000.000.000-00"
                          value={signer.document || ''}
                          onChange={(e) => handleSignerChange(index, 'document', e.target.value)}
                        />
                      </div>

                      <div>
                        <Label className="text-sm">Telefone</Label>
                        <Input
                          placeholder="(00) 00000-0000"
                          value={signer.phone || ''}
                          onChange={(e) => handleSignerChange(index, 'phone', e.target.value)}
                        />
                      </div>

                      <div>
                        <Label className="text-sm">Função</Label>
                        <Select
                          value={signer.role}
                          onValueChange={(v) =>
                            handleSignerChange(index, 'role', v as SignatureRole)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {SIGNATURE_ROLES.map((role) => (
                              <SelectItem key={role.value} value={role.value}>
                                {role.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label className="text-sm">Ordem</Label>
                        <Input
                          type="number"
                          min={1}
                          value={signer.order}
                          onChange={(e) =>
                            handleSignerChange(index, 'order', parseInt(e.target.value))
                          }
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Configurações */}
              <div className="space-y-3 p-4 border rounded-lg bg-gray-50">
                <Label className="font-semibold">Configurações</Label>

                {/* Assinatura sequencial */}
                <div className="flex items-center space-x-2">
                  <Switch checked={sequential} onCheckedChange={setSequential} />
                  <div>
                    <label className="text-sm font-medium">Assinatura Sequencial</label>
                    <p className="text-xs text-gray-500">
                      Cada signatário só poderá assinar após o anterior
                    </p>
                  </div>
                </div>

                {/* Prazo */}
                <div>
                  <Label className="text-sm">Prazo para Assinatura (dias)</Label>
                  <Input
                    type="number"
                    min={1}
                    max={90}
                    value={deadlineDays}
                    onChange={(e) => setDeadlineDays(parseInt(e.target.value))}
                  />
                </div>

                {/* Mensagem */}
                <div>
                  <Label className="text-sm">Mensagem para Signatários (opcional)</Label>
                  <Textarea
                    placeholder="Mensagem que será enviada junto com a solicitação"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={3}
                  />
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Canvas de assinatura */}
              <div className="space-y-3">
                <Label className="font-semibold">Assinatura</Label>
                <div className="border-2 border-dashed rounded-lg p-4">
                  <canvas
                    ref={canvasRef}
                    width={600}
                    height={200}
                    className="border rounded bg-white cursor-crosshair w-full"
                    onMouseDown={startDrawing}
                    onMouseMove={draw}
                    onMouseUp={stopDrawing}
                    onMouseLeave={stopDrawing}
                  />
                  <div className="flex justify-between items-center mt-2">
                    <p className="text-sm text-gray-500">Desenhe sua assinatura acima</p>
                    <Button variant="outline" size="sm" onClick={clearSignature}>
                      <X className="h-4 w-4 mr-1" />
                      Limpar
                    </Button>
                  </div>
                </div>
              </div>

              {/* Aviso legal */}
              <div className="flex items-start gap-2 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5" />
                <div className="text-sm text-blue-900">
                  <p className="font-medium mb-1">Declaração de Concordância</p>
                  <p>
                    Ao assinar este documento, você declara que leu, compreendeu e concorda com
                    todo o conteúdo. Esta assinatura tem validade jurídica.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          {mode === 'request' ? (
            <Button onClick={handleRequestSignatures} disabled={loading}>
              <Send className="h-4 w-4 mr-2" />
              {loading ? 'Enviando...' : 'Enviar Solicitações'}
            </Button>
          ) : (
            <Button onClick={handleSign} disabled={loading || !signatureData}>
              <PenTool className="h-4 w-4 mr-2" />
              {loading ? 'Assinando...' : 'Confirmar Assinatura'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
