'use client';

import { Eye, EyeOff, Copy, RefreshCw, Loader2, CheckCircle2 } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
;
import {
  useMaskData,
  useMaskCPF,
  useMaskEmail,
  useMaskPhone,
  useMaskBatch,
} from '@/hooks/security-lgpd';
import type { MaskDataRequestCategory } from '@/services/security-lgpd';

const categoryOptions: Array<{ value: MaskDataRequestCategory; label: string }> = [
  { value: 'cpf', label: 'CPF' },
  { value: 'email', label: 'E-mail' },
  { value: 'phone', label: 'Telefone' },
  { value: 'name', label: 'Nome' },
  { value: 'address', label: 'Endereco' },
  { value: 'credit_card', label: 'Cartao de Credito' },
];

const categoryPlaceholders: Record<MaskDataRequestCategory, string> = {
  cpf: '123.456.789-00',
  email: 'usuario@exemplo.com',
  phone: '(11) 98765-4321',
  name: 'Joao Silva Santos',
  address: 'Rua das Flores, 123',
  credit_card: '1234 5678 9012 3456',
};

export default function MascaramentoPage() {
  // Single masking state
  const [category, setCategory] = useState<MaskDataRequestCategory>('cpf');
  const [inputValue, setInputValue] = useState('');
  const [maskedResult, setMaskedResult] = useState('');
  const [copied, setCopied] = useState(false);

  // Batch masking state
  const [batchCategory, setBatchCategory] = useState<MaskDataRequestCategory>('cpf');
  const [batchInput, setBatchInput] = useState('');
  const [batchResult, setBatchResult] = useState('');
  const [batchCopied, setBatchCopied] = useState(false);

  // Mutations
  const maskData = useMaskData();
  const maskCPF = useMaskCPF();
  const maskEmail = useMaskEmail();
  const maskPhone = useMaskPhone();
  const maskBatch = useMaskBatch();

  const handleMaskSingle = async () => {
    if (!inputValue.trim()) return;

    try {
      let result: any;

      switch (category) {
        case 'cpf':
          result = await maskCPF.mutateAsync({ cpf: inputValue });
          break;
        case 'email':
          result = await maskEmail.mutateAsync({ email: inputValue });
          break;
        case 'phone':
          result = await maskPhone.mutateAsync({ phone: inputValue });
          break;
        default:
          result = await maskData.mutateAsync({
            data: inputValue,
            category,
          });
          break;
      }

      // O resultado pode vir como string direta ou dentro de um objeto
      const masked =
        typeof result === 'string'
          ? result
          : result?.data?.masked_data || result?.data?.data?.masked_data || String(result);

      setMaskedResult(masked);
    } catch {
      setMaskedResult('Erro ao mascarar dado');
    }
  };

  const handleMaskBatch = async () => {
    if (!batchInput.trim()) return;

    try {
      const lines = batchInput
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean);

      const items = lines.map((data) => ({
        data,
        category: batchCategory,
      }));

      const results = await maskBatch.mutateAsync(items);

      const resultText = results
        .map(
          (r: any) =>
            typeof r === 'string' ? r : r?.masked || r?.data?.masked_data || String(r)
        )
        .join('\n');

      setBatchResult(resultText);
    } catch {
      setBatchResult('Erro ao mascarar dados em lote');
    }
  };

  const handleCopy = async (text: string, setter: (v: boolean) => void) => {
    try {
      await navigator.clipboard.writeText(text);
      setter(true);
      setTimeout(() => setter(false), 2000);
    } catch {
      // silenced
    }
  };

  const isSingleLoading =
    maskData.isPending || maskCPF.isPending || maskEmail.isPending || maskPhone.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <EyeOff className="h-6 w-6" />
          Mascaramento de Dados
        </h1>
        <p className="text-muted-foreground">
          Ferramentas para mascaramento de dados pessoais sensiveis (PII)
        </p>
      </div>

      {/* Single Masking Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Mascaramento Individual
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="mask-category">Tipo de Dado</Label>
              <Select
                value={category}
                onValueChange={(v) => {
                  setCategory(v as MaskDataRequestCategory);
                  setMaskedResult('');
                }}
              >
                <SelectTrigger id="mask-category">
                  <SelectValue placeholder="Selecione o tipo" />
                </SelectTrigger>
                <SelectContent>
                  {categoryOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="mask-value">Valor</Label>
              <Input
                id="mask-value"
                value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value);
                  setMaskedResult('');
                }}
                placeholder={categoryPlaceholders[category]}
              />
            </div>

            <div className="space-y-2">
              <Label>&nbsp;</Label>
              <Button
                onClick={handleMaskSingle}
                disabled={!inputValue.trim() || isSingleLoading}
                className="w-full"
              >
                {isSingleLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Mascarando...
                  </>
                ) : (
                  <>
                    <EyeOff className="h-4 w-4 mr-2" />
                    Mascarar
                  </>
                )}
              </Button>
            </div>
          </div>

          {maskedResult && (
            <div className="space-y-2">
              <Label>Resultado</Label>
              <div className="flex items-center gap-2">
                <Input value={maskedResult} readOnly className="font-mono" />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => handleCopy(maskedResult, setCopied)}
                >
                  {copied ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Batch Masking Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Mascaramento em Lote
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="batch-category">Formato</Label>
                <Select
                  value={batchCategory}
                  onValueChange={(v) => {
                    setBatchCategory(v as MaskDataRequestCategory);
                    setBatchResult('');
                  }}
                >
                  <SelectTrigger id="batch-category">
                    <SelectValue placeholder="Selecione o formato" />
                  </SelectTrigger>
                  <SelectContent>
                    {categoryOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="batch-input">Valores (um por linha)</Label>
                <Textarea
                  id="batch-input"
                  value={batchInput}
                  onChange={(e) => {
                    setBatchInput(e.target.value);
                    setBatchResult('');
                  }}
                  placeholder={`Insira os valores a mascarar, um por linha.\nExemplo:\n${categoryPlaceholders[batchCategory]}`}
                  rows={8}
                  className="font-mono text-sm"
                />
              </div>

              <Button
                onClick={handleMaskBatch}
                disabled={!batchInput.trim() || maskBatch.isPending}
                className="w-full"
              >
                {maskBatch.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Mascarando Lote...
                  </>
                ) : (
                  <>
                    <EyeOff className="h-4 w-4 mr-2" />
                    Mascarar Lote
                  </>
                )}
              </Button>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Resultado</Label>
                {batchResult && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy(batchResult, setBatchCopied)}
                  >
                    {batchCopied ? (
                      <>
                        <CheckCircle2 className="h-4 w-4 mr-1 text-green-600" />
                        Copiado
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-1" />
                        Copiar
                      </>
                    )}
                  </Button>
                )}
              </div>
              <Textarea
                value={batchResult}
                readOnly
                placeholder="Os resultados mascarados aparecerao aqui..."
                rows={8}
                className="font-mono text-sm"
               aria-label="Os resultados mascarados aparecerao aqui..." />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
