'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  MapPin,
  Pencil,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

// ── Tipos (contrato /operacional/instrucoes-posto) ──────────────────────────
interface PostoItem {
  post_id: string;
  post_nome: string;
  tem_instrucoes: boolean;
  versao: number;
  updated_at?: string | null;
}

interface InstrucoesPosto {
  post_id: string;
  post_nome: string;
  titulo: string;
  conteudo: string | null;
  versao: number;
  updated_at?: string | null;
  updated_by_nome?: string | null;
}

function formatarDataHora(raw?: string | null): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  return `${d.toLocaleDateString('pt-BR')} às ${d.toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

export default function InstrucoesPostoPage() {
  // Lista
  const [postos, setPostos] = useState<PostoItem[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [erroLista, setErroLista] = useState<string | null>(null);

  // Detalhe
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<InstrucoesPosto | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);

  // Editor (botão sempre visível; 403 do backend = "somente gestão edita")
  const [editando, setEditando] = useState(false);
  const [tituloEdit, setTituloEdit] = useState('');
  const [conteudoEdit, setConteudoEdit] = useState('');
  const [salvando, setSalvando] = useState(false);

  const carregarLista = useCallback(async () => {
    setCarregandoLista(true);
    try {
      const res = await api.get('/api/v1/operacional/instrucoes-posto/');
      setPostos(res.data?.items || []);
      setErroLista(null);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      if (e.response?.status === 403) {
        setErroLista('Sem posto vinculado ao seu usuário — sem acesso às instruções de posto.');
      } else {
        setErroLista('Não foi possível carregar os postos.');
      }
    } finally {
      setCarregandoLista(false);
    }
  }, []);

  const carregarDetalhe = useCallback(async (postId: string) => {
    setSelecionado(postId);
    setEditando(false);
    setCarregandoDetalhe(true);
    setDetalhe(null);
    try {
      const res = await api.get(`/api/v1/operacional/instrucoes-posto/${postId}`);
      setDetalhe(res.data || null);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      if (e.response?.status === 403) {
        toast.error('Este posto está fora do seu escopo.');
      } else {
        toast.error('Não foi possível carregar as instruções deste posto.');
      }
      setSelecionado(null);
    } finally {
      setCarregandoDetalhe(false);
    }
  }, []);

  useEffect(() => {
    carregarLista();
  }, [carregarLista]);

  const abrirEditor = () => {
    if (!detalhe) return;
    setTituloEdit(detalhe.titulo || 'Instruções do posto');
    setConteudoEdit(detalhe.conteudo || '');
    setEditando(true);
  };

  const salvar = async () => {
    if (!detalhe) return;
    const conteudo = conteudoEdit.trim();
    if (conteudo.length < 10) {
      toast.error('O conteúdo precisa ter pelo menos 10 caracteres.');
      return;
    }
    setSalvando(true);
    try {
      const payload: Record<string, unknown> = { conteudo };
      if (tituloEdit.trim()) payload.titulo = tituloEdit.trim();
      const res = await api.put(
        `/api/v1/operacional/instrucoes-posto/${detalhe.post_id}`,
        payload,
      );
      setDetalhe(res.data || null);
      setEditando(false);
      toast.success(`Instruções salvas (versão ${res.data?.versao ?? ''})`);
      carregarLista();
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (e.response?.status === 403) {
        toast.error('Somente a gestão edita as instruções do posto.');
      } else {
        const detail = e.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : 'Erro ao salvar as instruções.');
      }
    } finally {
      setSalvando(false);
    }
  };

  const voltarParaLista = () => {
    setSelecionado(null);
    setDetalhe(null);
    setEditando(false);
  };

  // ── Detalhe de um posto ────────────────────────────────────────────────────
  if (selecionado) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4 p-4 pb-24">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" aria-label="Voltar" onClick={voltarParaLista}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="flex items-center gap-2 truncate text-xl font-bold">
              <FileText className="h-5 w-5 text-blue-600" />
              {detalhe?.post_nome || 'Instruções do posto'}
            </h1>
            {detalhe && detalhe.versao > 0 && (
              <p className="text-sm text-muted-foreground">
                Versão {detalhe.versao}
                {detalhe.updated_by_nome && ` — atualizado por ${detalhe.updated_by_nome}`}
                {detalhe.updated_at && ` em ${formatarDataHora(detalhe.updated_at)}`}
              </p>
            )}
          </div>
          {detalhe && !editando && (
            <Button variant="outline" size="sm" onClick={abrirEditor}>
              <Pencil className="mr-1 h-4 w-4" /> Editar
            </Button>
          )}
        </div>

        {carregandoDetalhe ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              Carregando instruções…
            </CardContent>
          </Card>
        ) : editando && detalhe ? (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Editar instruções</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Título</label>
                <Input
                  value={tituloEdit}
                  onChange={(e) => setTituloEdit(e.target.value)}
                  maxLength={200}
                  placeholder="Instruções do posto"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Conteúdo</label>
                <Textarea
                  value={conteudoEdit}
                  onChange={(e) => setConteudoEdit(e.target.value)}
                  rows={14}
                  placeholder={'Ex.:\n1. Controle de acesso: ...\n2. Rondas: ...\n3. Emergências: ...'}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Mínimo de 10 caracteres. Ao salvar, a versão atual vai para o histórico.
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setEditando(false)} disabled={salvando}>
                  Cancelar
                </Button>
                <Button onClick={salvar} isLoading={salvando}>
                  Salvar instruções
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : detalhe ? (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{detalhe.titulo || 'Instruções do posto'}</CardTitle>
            </CardHeader>
            <CardContent>
              {detalhe.conteudo ? (
                <div className="whitespace-pre-wrap text-sm leading-relaxed">{detalhe.conteudo}</div>
              ) : (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Nenhuma instrução cadastrada para este posto.
                </p>
              )}
            </CardContent>
          </Card>
        ) : null}
      </div>
    );
  }

  // ── Lista de postos do escopo ──────────────────────────────────────────────
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4 pb-24">
      <div className="flex items-center gap-2">
        <Link href="/modulos/operacional">
          <Button variant="ghost" size="icon" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <FileText className="h-5 w-5 text-blue-600" />
            Instruções do Posto
          </h1>
          <p className="text-sm text-muted-foreground">
            O que fazer em cada posto — a gestão edita, o líder consulta no celular.
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Atualizar"
          onClick={carregarLista}
          disabled={carregandoLista}
        >
          <RefreshCw className={`h-4 w-4 ${carregandoLista ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {erroLista && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            {erroLista}
          </CardContent>
        </Card>
      )}

      {carregandoLista ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Carregando postos…
          </CardContent>
        </Card>
      ) : !erroLista && postos.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Nenhum posto ativo no seu escopo.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {postos.map((p) => (
            <button
              key={p.post_id}
              type="button"
              onClick={() => carregarDetalhe(p.post_id)}
              className="flex w-full items-center gap-3 rounded-lg border border-[hsl(var(--border))] bg-card p-3 text-left transition-colors hover:bg-muted/50"
            >
              <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{p.post_nome}</p>
                <p className="text-xs text-muted-foreground">
                  {p.tem_instrucoes
                    ? `Versão ${p.versao}${p.updated_at ? ` — ${formatarDataHora(p.updated_at)}` : ''}`
                    : 'Sem instruções cadastradas'}
                </p>
              </div>
              {p.tem_instrucoes ? (
                <Badge className="bg-green-100 text-green-800">v{p.versao}</Badge>
              ) : (
                <Badge className="bg-gray-100 text-gray-700">vazio</Badge>
              )}
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
