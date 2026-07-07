'use client';

import { Lock, Unlock, Copy, RefreshCw, Shield, Loader2, CheckCircle2 } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
;
import { useEncryptData, useDecryptData, useAlgorithms } from '@/hooks/security-lgpd';

const defaultAlgorithms = [
  {
    name: 'AES-256-GCM',
    description: 'Advanced Encryption Standard com modo GCM. Criptografia autenticada de alta seguranca.',
    strength: 'high',
  },
  {
    name: 'AES-256-CBC',
    description: 'Advanced Encryption Standard com modo CBC. Algoritmo padrao da industria.',
    strength: 'standard',
  },
  {
    name: 'Fernet',
    description: 'Criptografia simetrica com autenticacao. Ideal para tokens e sessoes.',
    strength: 'standard',
  },
  {
    name: 'ChaCha20-Poly1305',
    description: 'Cifra de stream moderna e rapida com autenticacao.',
    strength: 'high',
  },
  {
    name: 'RSA-OAEP',
    description: 'Criptografia assimetrica RSA. Ideal para chaves e pequenos dados.',
    strength: 'medium',
  },
];

const strengthLabels: Record<string, string> = {
  high: 'Alta',
  medium: 'Media',
  standard: 'Padrao',
};

const strengthVariants: Record<string, 'default' | 'secondary' | 'outline'> = {
  high: 'default',
  medium: 'secondary',
  standard: 'outline',
};

export default function CriptografiaPage() {
  // Encrypt state
  const [encryptInput, setEncryptInput] = useState('');
  const [encryptAlgorithm, setEncryptAlgorithm] = useState('AES-256-GCM');
  const [encryptResult, setEncryptResult] = useState('');
  const [encryptCopied, setEncryptCopied] = useState(false);

  // Decrypt state
  const [decryptInput, setDecryptInput] = useState('');
  const [decryptResult, setDecryptResult] = useState('');
  const [decryptCopied, setDecryptCopied] = useState(false);

  // Hooks
  const encryptMutation = useEncryptData();
  const decryptMutation = useDecryptData();
  const { data: algorithmsData, isLoading: algorithmsLoading } = useAlgorithms();

  // Parse algorithms from API or use defaults
  const algorithms =
    (algorithmsData as any)?.data?.algorithms ||
    (algorithmsData as any)?.data?.data?.algorithms ||
    defaultAlgorithms;

  const handleEncrypt = async () => {
    if (!encryptInput.trim()) return;

    try {
      const result = await encryptMutation.mutateAsync({
        data: encryptInput,
        algorithm: encryptAlgorithm as any,
      });

      const encrypted =
        (result as any)?.data?.encrypted_data ||
        (result as any)?.data?.data?.encrypted_data ||
        String(result);

      setEncryptResult(encrypted);
    } catch {
      setEncryptResult('Erro ao criptografar dados');
    }
  };

  const handleDecrypt = async () => {
    if (!decryptInput.trim()) return;

    try {
      const result = await decryptMutation.mutateAsync({
        encryptedData: decryptInput,
      });

      const decrypted =
        (result as any)?.data?.decrypted_data ||
        (result as any)?.data?.data?.decrypted_data ||
        String(result);

      setDecryptResult(decrypted);
    } catch {
      setDecryptResult('Erro ao descriptografar dados');
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Lock className="h-6 w-6" />
          Criptografia
        </h1>
        <p className="text-muted-foreground">
          Ferramentas de criptografia e descriptografia de dados sensiveis
        </p>
      </div>

      {/* Encrypt / Decrypt Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Encrypt Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Lock className="h-5 w-5 text-green-600" />
              Criptografar
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="encrypt-input">Dados de Entrada</Label>
              <Textarea
                id="encrypt-input"
                value={encryptInput}
                onChange={(e) => {
                  setEncryptInput(e.target.value);
                  setEncryptResult('');
                }}
                placeholder="Insira os dados a serem criptografados..."
                rows={4}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="encrypt-algorithm">Algoritmo</Label>
              <Select
                value={encryptAlgorithm}
                onValueChange={(v) => {
                  setEncryptAlgorithm(v);
                  setEncryptResult('');
                }}
              >
                <SelectTrigger id="encrypt-algorithm">
                  <SelectValue placeholder="Selecione o algoritmo" />
                </SelectTrigger>
                <SelectContent>
                  {algorithms.map((algo: any) => (
                    <SelectItem
                      key={algo.name || algo}
                      value={algo.name || algo}
                    >
                      {algo.name || algo}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleEncrypt}
              disabled={!encryptInput.trim() || encryptMutation.isPending}
              className="w-full"
            >
              {encryptMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Criptografando...
                </>
              ) : (
                <>
                  <Lock className="h-4 w-4 mr-2" />
                  Criptografar
                </>
              )}
            </Button>

            {encryptResult && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Resultado</Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy(encryptResult, setEncryptCopied)}
                  >
                    {encryptCopied ? (
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
                </div>
                <Textarea
                  value={encryptResult}
                  readOnly
                  rows={4}
                  className="font-mono text-sm"
                 aria-label="Encrypt Result"/>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Decrypt Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Unlock className="h-5 w-5 text-blue-600" />
              Descriptografar
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="decrypt-input">Dados Criptografados</Label>
              <Textarea
                id="decrypt-input"
                value={decryptInput}
                onChange={(e) => {
                  setDecryptInput(e.target.value);
                  setDecryptResult('');
                }}
                placeholder="Insira os dados criptografados (base64)..."
                rows={4}
                className="font-mono text-sm"
              />
            </div>

            <Button
              onClick={handleDecrypt}
              disabled={!decryptInput.trim() || decryptMutation.isPending}
              className="w-full"
            >
              {decryptMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Descriptografando...
                </>
              ) : (
                <>
                  <Unlock className="h-4 w-4 mr-2" />
                  Descriptografar
                </>
              )}
            </Button>

            {decryptResult && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Resultado</Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy(decryptResult, setDecryptCopied)}
                  >
                    {decryptCopied ? (
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
                </div>
                <Textarea
                  value={decryptResult}
                  readOnly
                  rows={4}
                 aria-label="Decrypt Result"/>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Algorithms Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Algoritmos Disponiveis
          </CardTitle>
        </CardHeader>
        <CardContent>
          {algorithmsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(algorithms.length > 0 ? algorithms : defaultAlgorithms).map(
                (algo: any) => {
                  const name = algo.name || algo;
                  const description = algo.description || '';
                  const strength = algo.strength || 'standard';

                  return (
                    <div
                      key={name}
                      className="p-4 rounded-lg border border-[hsl(var(--border))] space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <h4 className="font-semibold text-sm">{name}</h4>
                        <Badge variant={strengthVariants[strength] || 'outline'}>
                          {strengthLabels[strength] || strength}
                        </Badge>
                      </div>
                      {description && (
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">
                          {description}
                        </p>
                      )}
                    </div>
                  );
                }
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
