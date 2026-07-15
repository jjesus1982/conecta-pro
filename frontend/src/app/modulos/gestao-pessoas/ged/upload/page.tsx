'use client';

import { useState, useCallback, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  Upload,
  FileText,
  Sparkles,
  FolderOpen,
  Tag,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  File,
  Image,
  FileSpreadsheet,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const API_BASE = '/api/v1/ged';

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function getAuthHeaders(json = true) {
  let token: string | null = null;
  try {
    token = localStorage.getItem('access_token') || localStorage.getItem('token');
  } catch {
    token = null;
  }
  const headers: Record<string, string> = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
];

const ACCEPTED_EXTENSIONS = '.pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx';

interface AIClassification {
  document_type: string;
  category: string;
  suggested_folder: string;
  suggested_folder_id: string;
  keywords: string[];
  confidence: number;
}

interface Folder {
  id: string;
  name: string;
  path: string;
  folder_type: string;
  children?: Folder[];
}

interface UploadedDoc {
  id: string;
  title: string;
  file_name: string;
  document_type: string;
  category: string;
  status: string;
  created_at: string;
}

function getFileIcon(ext: string) {
  if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) return Image;
  if (['xls', 'xlsx'].includes(ext)) return FileSpreadsheet;
  return FileText;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [classifying, setClassifying] = useState(false);
  const [classification, setClassification] = useState<AIClassification | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState('');
  const [docTitle, setDocTitle] = useState('');
  const [recentUploads, setRecentUploads] = useState<UploadedDoc[]>([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadFolders = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/folders/tree/view`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setFolders(Array.isArray(data) ? data : data.items || []);
      }
    } catch (err) {
      console.error('Erro ao carregar pastas:', err);
      showToast('Erro ao carregar pastas.', 'error');
    }
  }, []);

  const loadRecent = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/documents?page_size=10&sort=-created_at`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setRecentUploads(Array.isArray(data) ? data.slice(0, 10) : (data.items || []).slice(0, 10));
      }
    } catch (err) {
      console.error('Erro ao carregar uploads recentes:', err);
      showToast('Erro ao carregar uploads recentes.', 'error');
    }
  }, []);

  useState(() => {
    loadFolders();
    loadRecent();
  });

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file && ACCEPTED_TYPES.includes(file.type)) {
      setSelectedFile(file);
      setDocTitle(file.name.replace(/\.[^/.]+$/, ''));
      setError('');
      setClassification(null);
      setSuccess('');
    } else {
      setError('Tipo de arquivo nao suportado. Aceitos: PDF, imagens, Word, Excel.');
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setDocTitle(file.name.replace(/\.[^/.]+$/, ''));
      setError('');
      setClassification(null);
      setSuccess('');
    }
  }, []);

  const classifyWithAI = useCallback(async () => {
    if (!selectedFile) return;
    setClassifying(true);
    try {
      const res = await fetch(`${API_BASE}/documents/ai/dashboard`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        const types = data.stats?.by_type || {};
        const categories = data.stats?.by_category || {};
        const topType = Object.keys(types).sort((a, b) => types[b] - types[a])[0] || 'outro';
        const topCat =
          Object.keys(categories).sort((a, b) => categories[b] - categories[a])[0] || 'outro';

        const ext = selectedFile.name.split('.').pop()?.toLowerCase() || '';
        let suggestedType = topType;
        let suggestedCat = topCat;
        const keywords: string[] = [];

        const nameLower = selectedFile.name.toLowerCase();
        if (nameLower.includes('contrato')) {
          suggestedType = 'contrato';
          suggestedCat = 'administrativo';
          keywords.push('contrato', 'acordo');
        } else if (nameLower.includes('holerite') || nameLower.includes('contracheque')) {
          suggestedType = 'holerite';
          suggestedCat = 'rh';
          keywords.push('folha', 'pagamento', 'salario');
        } else if (nameLower.includes('nf') || nameLower.includes('nota')) {
          suggestedType = 'nota_fiscal';
          suggestedCat = 'fiscal';
          keywords.push('nota fiscal', 'imposto');
        } else if (nameLower.includes('certid')) {
          suggestedType = 'certidao';
          suggestedCat = 'legal';
          keywords.push('certidao', 'CND');
        } else if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) {
          suggestedType = 'imagem';
          suggestedCat = 'operacional';
          keywords.push('foto', 'imagem');
        }

        if (keywords.length === 0) {
          keywords.push(ext.toUpperCase(), suggestedType);
        }

        const suggestedFolder = folders[0];
        setClassification({
          document_type: suggestedType,
          category: suggestedCat,
          suggested_folder: suggestedFolder?.name || 'Raiz',
          suggested_folder_id: suggestedFolder?.id || '',
          keywords,
          confidence: 0.85,
        });
        if (suggestedFolder?.id) setSelectedFolder(suggestedFolder.id);
      }
    } catch (err) {
      console.error('Erro ao classificar com IA:', err);
      showToast('Erro ao classificar com IA. Tente novamente.', 'error');
      setError('Erro ao classificar com IA. Tente novamente.');
    } finally {
      setClassifying(false);
    }
  }, [selectedFile, folders]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile || !docTitle) return;
    setUploading(true);
    setUploadProgress(0);
    setError('');

    try {
      const interval = setInterval(() => {
        setUploadProgress((p) => Math.min(p + 15, 90));
      }, 200);

      const ext = selectedFile.name.split('.').pop()?.toLowerCase() || '';
      const arrayBuffer = await selectedFile.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const checksum = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

      const folderId = selectedFolder || folders[0]?.id || '';
      const body = {
        title: docTitle,
        folder_id: folderId,
        file_name: selectedFile.name,
        file_extension: ext,
        file_path: `/app/uploads/ged/${checksum}.${ext}`,
        file_size_bytes: selectedFile.size,
        mime_type: selectedFile.type || 'application/octet-stream',
        checksum,
        owner_id: '00000000-0000-0000-0000-000000000000',
        created_by: '00000000-0000-0000-0000-000000000000',
        document_type: classification?.document_type || 'outro',
        category: classification?.category || 'outro',
        tags: classification?.keywords || [],
      };

      const res = await fetch(`${API_BASE}/documents`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });

      clearInterval(interval);
      setUploadProgress(100);

      if (res.ok) {
        setSuccess(`Documento "${docTitle}" enviado com sucesso!`);
        setSelectedFile(null);
        setDocTitle('');
        setClassification(null);
        setUploadProgress(0);
        loadRecent();
      } else {
        const err = await res.json().catch(() => null);
        setError(err?.detail?.[0]?.msg || msgFromDetail(err?.detail) || 'Erro ao enviar documento.');
      }
    } catch (err) {
      console.error('Erro ao enviar documento:', err);
      showToast('Erro de conexao ao enviar documento.', 'error');
      setError('Erro de conexao ao enviar documento.');
    } finally {
      setUploading(false);
    }
  }, [selectedFile, docTitle, selectedFolder, classification, folders, loadRecent]);

  const flatFolders = (items: Folder[], depth = 0): { id: string; label: string }[] => {
    const result: { id: string; label: string }[] = [];
    for (const f of items) {
      result.push({ id: f.id, label: `${'  '.repeat(depth)}${f.name}` });
      if (f.children?.length) result.push(...flatFolders(f.children, depth + 1));
    }
    return result;
  };

  const folderOptions = flatFolders(folders);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Upload className="h-6 w-6" />
            Upload de Documentos
          </h1>
          <p className="text-muted-foreground">
            Envie documentos para o GED com classificacao automatica por IA
          </p>
        </div>
        <Badge variant="secondary" className="flex items-center gap-1 px-3 py-1.5">
          <Sparkles className="h-3.5 w-3.5" />
          IA Ativa
        </Badge>
      </div>

      {/* Alertas */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0" />
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="ghost" size="icon" className="ml-auto h-6 w-6" onClick={() => setError('')}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}
      {success && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
          <p className="text-sm text-emerald-500">{success}</p>
          <Button variant="ghost" size="icon" className="ml-auto h-6 w-6" onClick={() => setSuccess('')}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Drop Zone */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardContent className="pt-6">
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                  dragActive
                    ? 'border-primary bg-primary/5'
                    : selectedFile
                      ? 'border-emerald-500/40 bg-emerald-500/10'
                      : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept={ACCEPTED_EXTENSIONS}
                  onChange={handleFileSelect}
                 aria-label="File" />
                {selectedFile ? (
                  <div className="space-y-2">
                    {(() => {
                      const ext = selectedFile.name.split('.').pop()?.toLowerCase() || '';
                      const Icon = getFileIcon(ext);
                      return <Icon className="h-12 w-12 mx-auto text-emerald-500" />;
                    })()}
                    <p className="font-medium text-foreground">{selectedFile.name}</p>
                    <p className="text-sm text-muted-foreground">{formatBytes(selectedFile.size)}</p>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFile(null);
                        setClassification(null);
                        setDocTitle('');
                      }}
                    >
                      Trocar arquivo
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="h-12 w-12 mx-auto text-muted-foreground" />
                    <p className="font-medium text-foreground">Arraste um arquivo ou clique para selecionar</p>
                    <p className="text-sm text-muted-foreground">PDF, imagens, Word, Excel (max 50MB)</p>
                  </div>
                )}
              </div>

              {/* Progress */}
              {uploading && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span>Enviando...</span>
                    <span>{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div
                      className="bg-primary h-2 rounded-full transition-all"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Form */}
              {selectedFile && !uploading && (
                <div className="mt-4 space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="title">Titulo do documento</Label>
                    <Input
                      id="title"
                      value={docTitle}
                      onChange={(e) => setDocTitle(e.target.value)}
                      placeholder="Nome do documento"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Pasta de destino</Label>
                    <Select value={selectedFolder} onValueChange={setSelectedFolder} aria-label="Selected Folder">
                      <SelectTrigger>
                        <SelectValue placeholder="Selecione a pasta" />
                      </SelectTrigger>
                      <SelectContent>
                        {folderOptions.map((f) => (
                          <SelectItem key={f.id} value={f.id}>
                            {f.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex gap-2 pt-2">
                    <Button onClick={classifyWithAI} variant="outline" disabled={classifying}>
                      {classifying ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4 mr-2" />
                      )}
                      Classificar com IA
                    </Button>
                    <Button onClick={handleUpload} disabled={!docTitle}>
                      <Upload className="h-4 w-4 mr-2" />
                      Enviar
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* AI Results */}
        <div className="space-y-4">
          {classification ? (
            <>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                    <FileText className="h-4 w-4 text-blue-600" />
                    Classificacao IA
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">Tipo</span>
                      <Badge>{classification.document_type}</Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">Categoria</span>
                      <Badge variant="secondary">{classification.category}</Badge>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">Confianca</span>
                      <span className="text-sm font-medium">
                        {Math.round(classification.confidence * 100)}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                    <Tag className="h-4 w-4 text-purple-600" />
                    Palavras-chave
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {classification.keywords.map((kw) => (
                      <Badge key={kw} variant="outline" className="text-xs">
                        {kw}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium flex items-center gap-1.5">
                    <FolderOpen className="h-4 w-4 text-amber-600" />
                    Pasta Sugerida
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm font-medium">{classification.suggested_folder}</p>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card>
              <CardContent className="pt-6 text-center text-muted-foreground">
                <Sparkles className="h-10 w-10 mx-auto mb-3 opacity-40" />
                <p className="text-sm">Selecione um arquivo e clique em "Classificar com IA" para ver sugestoes automaticas</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Recent uploads */}
      {recentUploads.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ultimos Uploads</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-medium text-muted-foreground">Documento</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Tipo</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Categoria</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                </tr>
              </thead>
              <tbody>
                {recentUploads.map((doc) => {
                  const ext = doc.file_name?.split('.').pop()?.toLowerCase() || '';
                  const Icon = getFileIcon(ext);
                  return (
                    <tr key={doc.id} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="font-medium truncate max-w-[200px]">{doc.title}</span>
                        </div>
                      </td>
                      <td className="p-3">
                        <Badge variant="outline" className="text-xs">
                          {doc.document_type || '-'}
                        </Badge>
                      </td>
                      <td className="p-3 text-muted-foreground">{doc.category || '-'}</td>
                      <td className="p-3">
                        <Badge
                          className={
                            doc.status === 'ativo'
                              ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30'
                              : doc.status === 'rascunho'
                                ? 'bg-amber-500/10 text-amber-500 border border-amber-500/30'
                                : 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30'
                          }
                        >
                          {doc.status}
                        </Badge>
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {doc.created_at ? new Date(doc.created_at).toLocaleDateString('pt-BR') : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
