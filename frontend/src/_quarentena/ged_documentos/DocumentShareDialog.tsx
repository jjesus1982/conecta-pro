'use client';

import { Share2, Link, Mail, User, Calendar, Download, Eye, Lock, Copy, Check } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState } from 'react';
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
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Link as LinkIcon } from 'lucide-react';
import { ShareType } from '@/types/generated/ged/schemas/shareType';
import { documentShareService } from '@/services/ged/documentShareService';
import { toast } from 'sonner';

interface DocumentShareDialogProps {
  documentId: string;
  open: boolean;
  onClose: () => void;
}

const SHARE_TYPES: { value: ShareType; label: string; icon: any }[] = [
  { value: 'usuario', label: 'Usuário Específico', icon: User },
  { value: 'email', label: 'Email Externo', icon: Mail },
  { value: 'grupo', label: 'Grupo', icon: User },
  { value: 'departamento', label: 'Departamento', icon: User },
  { value: 'externo', label: 'Link Público', icon: LinkIcon },
];

const PERMISSIONS = [
  { value: 'visualizar', label: 'Visualizar' },
  { value: 'baixar', label: 'Baixar' },
  { value: 'comentar', label: 'Comentar' },
  { value: 'editar', label: 'Editar' },
  { value: 'compartilhar', label: 'Compartilhar' },
];

export function DocumentShareDialog({ documentId, open, onClose }: DocumentShareDialogProps) {
  const [activeTab, setActiveTab] = useState<'share' | 'public'>('share');
  const [shareType, setShareType] = useState<ShareType>('email');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [permissions, setPermissions] = useState<string[]>(['visualizar']);
  const [canReshare, setCanReshare] = useState(false);
  const [withPassword, setWithPassword] = useState(false);
  const [password, setPassword] = useState('');
  const [withExpiry, setWithExpiry] = useState(false);
  const [expiryDays, setExpiryDays] = useState(7);
  const [maxDownloads, setMaxDownloads] = useState<number>();
  const [maxViews, setMaxViews] = useState<number>();
  const [publicLink, setPublicLink] = useState('');
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleShare = async () => {
    if (!email && shareType === 'email') {
      toast.error('Email é obrigatório');
      return;
    }

    setLoading(true);
    try {
      const expiresAt = withExpiry
        ? new Date(Date.now() + expiryDays * 24 * 60 * 60 * 1000).toISOString()
        : undefined;

      await documentShareService.create({
        document_id: documentId,
        share_type: shareType,
        shared_with_email: email || undefined,
        shared_with_name: name || undefined,
        permissions,
        can_reshare: canReshare,
        password_protected: withPassword,
        password: withPassword ? password : undefined,
        expires_at: expiresAt,
        is_perpetual: !withExpiry,
        message: message || undefined,
        max_downloads: maxDownloads,
        max_views: maxViews,
      });

      toast.success('Documento compartilhado com sucesso');
      resetForm();
      onClose();
    } catch (error: any) {
      toast.error('Erro ao compartilhar documento', {
        description: msgFromDetail(error.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePublicLink = async () => {
    setLoading(true);
    try {
      const result = await documentShareService.createPublicLink({
        expires_in_hours: withExpiry ? expiryDays * 24 : undefined,
        max_downloads: maxDownloads,
        max_views: maxViews,
        password: withPassword ? password : undefined,
        message: message || undefined,
      });

      const link = `${window.location.origin}/ged/share/${result.share_token}`;
      setPublicLink(link);
      toast.success('Link público criado');
    } catch (error: any) {
      toast.error('Erro ao criar link público', {
        description: msgFromDetail(error.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(publicLink);
    setCopied(true);
    toast.success('Link copiado para área de transferência');
    setTimeout(() => setCopied(false), 2000);
  };

  const resetForm = () => {
    setEmail('');
    setName('');
    setMessage('');
    setPermissions(['visualizar']);
    setCanReshare(false);
    setWithPassword(false);
    setPassword('');
    setWithExpiry(false);
    setExpiryDays(7);
    setMaxDownloads(undefined);
    setMaxViews(undefined);
    setPublicLink('');
  };

  const togglePermission = (perm: string) => {
    if (permissions.includes(perm)) {
      setPermissions(permissions.filter((p) => p !== perm));
    } else {
      setPermissions([...permissions, perm]);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Compartilhar Documento</DialogTitle>
          <DialogDescription>
            Compartilhe este documento com outras pessoas
          </DialogDescription>
        </DialogHeader>

        {/* Tabs */}
        <div className="flex gap-2 border-b">
          <button
            onClick={() => setActiveTab('share')}
            className={`px-4 py-2 font-medium ${
              activeTab === 'share'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-gray-500'
            }`}
          >
            <Share2 className="h-4 w-4 inline mr-2" />
            Compartilhar com Pessoa
          </button>
          <button
            onClick={() => setActiveTab('public')}
            className={`px-4 py-4 font-medium ${
              activeTab === 'public'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-gray-500'
            }`}
          >
            <LinkIcon className="h-4 w-4 inline mr-2" />
            Link Público
          </button>
        </div>

        <div className="space-y-4 mt-4">
          {activeTab === 'share' ? (
            <>
              {/* Tipo de compartilhamento */}
              <div>
                <Label>Tipo de Compartilhamento</Label>
                <Select value={shareType} onValueChange={(v) => setShareType(v as ShareType)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SHARE_TYPES.map((type) => {
                      const Icon = type.icon;
                      return (
                        <SelectItem key={type.value} value={type.value}>
                          <Icon className="h-4 w-4 inline mr-2" />
                          {type.label}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>

              {/* Email */}
              <div>
                <Label>Email *</Label>
                <Input
                  type="email"
                  placeholder="email@exemplo.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              {/* Nome */}
              <div>
                <Label>Nome (opcional)</Label>
                <Input
                  placeholder="Nome da pessoa"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              {/* Permissões */}
              <div>
                <Label>Permissões</Label>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {PERMISSIONS.map((perm) => (
                    <div key={perm.value} className="flex items-center space-x-2">
                      <Switch
                        checked={permissions.includes(perm.value)}
                        onCheckedChange={() => togglePermission(perm.value)}
                      />
                      <label className="text-sm">{perm.label}</label>
                    </div>
                  ))}
                </div>
              </div>

              {/* Pode recompartilhar */}
              <div className="flex items-center space-x-2">
                <Switch checked={canReshare} onCheckedChange={setCanReshare} />
                <label className="text-sm">Permitir recompartilhamento</label>
              </div>

              {/* Mensagem */}
              <div>
                <Label>Mensagem (opcional)</Label>
                <Textarea
                  placeholder="Mensagem personalizada para o destinatário"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={3}
                />
              </div>
            </>
          ) : (
            <>
              {/* Link público gerado */}
              {publicLink && (
                <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                  <Label>Link Público</Label>
                  <div className="flex items-center gap-2 mt-2">
                    <Input value={publicLink} readOnly className="font-mono text-sm" />
                    <Button onClick={handleCopyLink} size="sm">
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                  <p className="text-sm text-gray-600 mt-2">
                    Qualquer pessoa com este link poderá acessar o documento.
                  </p>
                </div>
              )}
            </>
          )}

          {/* Configurações comuns */}
          <div className="space-y-3 p-4 border rounded-lg bg-gray-50">
            <Label className="font-semibold">Configurações de Segurança</Label>

            {/* Proteger com senha */}
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <Switch checked={withPassword} onCheckedChange={setWithPassword} />
                <label className="text-sm flex items-center gap-1">
                  <Lock className="h-4 w-4" />
                  Proteger com senha
                </label>
              </div>
              {withPassword && (
                <Input
                  type="password"
                  placeholder="Digite a senha"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </div>

            {/* Data de expiração */}
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <Switch checked={withExpiry} onCheckedChange={setWithExpiry} />
                <label className="text-sm flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  Definir data de expiração
                </label>
              </div>
              {withExpiry && (
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    max={365}
                    value={expiryDays}
                    onChange={(e) => setExpiryDays(parseInt(e.target.value))}
                    className="w-20"
                  />
                  <span className="text-sm">dias</span>
                </div>
              )}
            </div>

            {/* Limite de downloads */}
            <div className="space-y-2">
              <Label className="text-sm flex items-center gap-1">
                <Download className="h-4 w-4" />
                Limite de Downloads
              </Label>
              <Input
                type="number"
                min={1}
                placeholder="Ilimitado"
                value={maxDownloads || ''}
                onChange={(e) => setMaxDownloads(parseInt(e.target.value) || undefined)}
              />
            </div>

            {/* Limite de visualizações */}
            <div className="space-y-2">
              <Label className="text-sm flex items-center gap-1">
                <Eye className="h-4 w-4" />
                Limite de Visualizações
              </Label>
              <Input
                type="number"
                min={1}
                placeholder="Ilimitado"
                value={maxViews || ''}
                onChange={(e) => setMaxViews(parseInt(e.target.value) || undefined)}
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          {activeTab === 'share' ? (
            <Button onClick={handleShare} disabled={loading}>
              {loading ? 'Compartilhando...' : 'Compartilhar'}
            </Button>
          ) : (
            <Button onClick={handleCreatePublicLink} disabled={loading || !!publicLink}>
              {loading ? 'Criando...' : publicLink ? 'Link Criado' : 'Gerar Link'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
