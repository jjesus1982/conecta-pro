'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  Clock,
  Send,
  UserX,
  Wrench,
  Zap,
  Users,
  MoreHorizontal,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// ── Tipos ────────────────────────────────────────────────────────────────────
interface MembroEquipe {
  employee_id: string;
  nome: string;
  cargo?: string;
  post_id?: string;
  post_name?: string;
  posto?: string;
  posto_nome?: string;
}

interface CategoriaChip {
  key: string;
  label: string;
  occurrence_type: string;
  category: string;
  icon: ReactNode;
}

const CATEGORIAS: CategoriaChip[] = [
  { key: 'falta', label: 'Falta', occurrence_type: 'falta_injustificada', category: 'assiduidade', icon: <UserX className="h-5 w-5" /> },
  { key: 'atraso', label: 'Atraso', occurrence_type: 'atraso', category: 'assiduidade', icon: <Clock className="h-5 w-5" /> },
  { key: 'incidente', label: 'Incidente', occurrence_type: 'incidente', category: 'operacional', icon: <AlertTriangle className="h-5 w-5" /> },
  { key: 'manutencao', label: 'Manutenção', occurrence_type: 'manutencao', category: 'operacional', icon: <Wrench className="h-5 w-5" /> },
  { key: 'conflito', label: 'Conflito', occurrence_type: 'conflito', category: 'conduta', icon: <Users className="h-5 w-5" /> },
  { key: 'elogio', label: 'Elogio', occurrence_type: 'elogio', category: 'conduta', icon: <Award className="h-5 w-5" /> },
  { key: 'outro', label: 'Outro', occurrence_type: 'outros', category: 'outros', icon: <MoreHorizontal className="h-5 w-5" /> },
];

const SEVERIDADES = [
  { value: 'leve', label: 'Leve', selected: 'bg-green-600 text-white border-green-600', idle: 'border-green-500 text-green-600 hover:bg-green-50' },
  { value: 'moderada', label: 'Moderada', selected: 'bg-yellow-500 text-white border-yellow-500', idle: 'border-yellow-500 text-yellow-600 hover:bg-yellow-50' },
  { value: 'grave', label: 'Grave', selected: 'bg-orange-600 text-white border-orange-600', idle: 'border-orange-500 text-orange-600 hover:bg-orange-50' },
  { value: 'gravissima', label: 'Gravíssima', selected: 'bg-red-600 text-white border-red-600', idle: 'border-red-500 text-red-600 hover:bg-red-50' },
];

const MIN_DESC = 10;

export default function OcorrenciaRapidaPage() {
  const [equipe, setEquipe] = useState<MembroEquipe[]>([]);
  const [equipeCarregada, setEquipeCarregada] = useState(false);

  // Form
  const [categoria, setCategoria] = useState<CategoriaChip | null>(null);
  const [severidade, setSeveridade] = useState<string>('leve');
  const [employeeId, setEmployeeId] = useState<string>('');
  const [postId, setPostId] = useState<string>('');
  const [titulo, setTitulo] = useState('');
  const [descricao, setDescricao] = useState('');
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    let ativo = true;
    api
      .get('/api/v1/operacional/avaliacoes/equipe')
      .then((res) => {
        if (!ativo) return;
        const lista = Array.isArray(res.data) ? res.data : res.data?.items || [];
        setEquipe(lista);
      })
      .catch(() => {
        // Equipe é opcional na tela — segue sem select de funcionário
      })
      .finally(() => ativo && setEquipeCarregada(true));
    return () => {
      ativo = false;
    };
  }, []);

  // Postos distintos derivados da equipe (escopada no backend)
  const postos = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const m of equipe) {
      const id = m.post_id;
      if (id) {
        mapa.set(id, m.post_name || m.posto_nome || m.posto || 'Posto');
      }
    }
    return Array.from(mapa.entries()).map(([id, nome]) => ({ id, nome }));
  }, [equipe]);

  const multiplosPostos = postos.length > 1;
  const postoUnico = postos.length === 1 ? postos[0] : null;

  const nomePostoSelecionado = useMemo(() => {
    if (multiplosPostos && postId) return postos.find((p) => p.id === postId)?.nome;
    if (postoUnico) return postoUnico.nome;
    return undefined;
  }, [multiplosPostos, postId, postos, postoUnico]);

  const tituloAuto = useMemo(() => {
    if (!categoria) return '';
    const sufixo = nomePostoSelecionado || new Date().toLocaleDateString('pt-BR');
    return `${categoria.label} — ${sufixo}`;
  }, [categoria, nomePostoSelecionado]);

  const descOk = descricao.trim().length >= MIN_DESC;
  const podeEnviar = !!categoria && !!severidade && descOk && !enviando;

  const limpar = useCallback(() => {
    setCategoria(null);
    setSeveridade('leve');
    setEmployeeId('');
    setPostId('');
    setTitulo('');
    setDescricao('');
  }, []);

  const enviar = async () => {
    if (!categoria) {
      toast.error('Escolha uma categoria');
      return;
    }
    if (!descOk) {
      toast.error(`Descreva o que aconteceu (mínimo ${MIN_DESC} caracteres)`);
      return;
    }
    setEnviando(true);
    try {
      const payload: Record<string, unknown> = {
        title: titulo.trim() || tituloAuto,
        description: descricao.trim(),
        occurrence_type: categoria.occurrence_type,
        severity: severidade,
        category: categoria.category,
      };
      const postEscolhido = multiplosPostos ? postId : postoUnico?.id;
      if (postEscolhido) payload.post_id = postEscolhido;
      if (employeeId) payload.employee_id = employeeId;

      const res = await api.post('/api/v1/operacional/occurrences/', payload);
      const dado = res.data || {};
      const codigo = dado.codigo || dado.code || dado.numero || dado.id;
      toast.success(
        codigo ? `Ocorrência registrada — código ${codigo}` : 'Ocorrência registrada',
      );
      limpar();
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (e.response?.status === 403) {
        toast.error('Sem permissão para registrar ocorrência neste posto. Fale com a gestão operacional.');
      } else {
        const detail = e.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : 'Erro ao registrar a ocorrência. Tente novamente.');
      }
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-lg space-y-4 p-4 pb-24">
      <div className="flex items-center gap-2">
        <Link href="/modulos/operacional">
          <Button variant="ghost" size="icon" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Zap className="h-5 w-5 text-amber-500" />
            Ocorrência Rápida
          </h1>
          <p className="text-sm text-muted-foreground">Registre em menos de 30 segundos</p>
        </div>
      </div>

      {/* Categoria */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">O que aconteceu?</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2">
            {CATEGORIAS.map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={() => setCategoria(c)}
                className={`flex min-h-[56px] items-center justify-center gap-2 rounded-xl border-2 px-3 py-3 text-sm font-semibold transition-colors ${
                  categoria?.key === c.key
                    ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]'
                    : 'border-[hsl(var(--border))] text-foreground hover:bg-[hsl(var(--secondary))]'
                }`}
              >
                {c.icon}
                {c.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Severidade */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Gravidade</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2">
            {SEVERIDADES.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setSeveridade(s.value)}
                className={`min-h-[48px] rounded-xl border-2 px-3 py-2 text-sm font-semibold transition-colors ${
                  severidade === s.value ? s.selected : s.idle
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Detalhes */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Detalhes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {equipe.length > 0 && (
            <div>
              <label className="mb-1 block text-sm font-medium">Funcionário (opcional)</label>
              <Select value={employeeId || undefined} onValueChange={(v) => setEmployeeId(v === '__none__' ? '' : v)}>
                <SelectTrigger className="h-12">
                  <SelectValue placeholder="Sem funcionário específico" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Sem funcionário específico</SelectItem>
                  {equipe.map((m) => (
                    <SelectItem key={m.employee_id} value={m.employee_id}>
                      {m.nome}
                      {m.cargo ? ` — ${m.cargo}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {equipeCarregada && equipe.length === 0 && (
            <p className="text-xs text-muted-foreground">
              Sem equipe vinculada ao seu acesso — a ocorrência será registrada sem funcionário.
            </p>
          )}

          {multiplosPostos && (
            <div>
              <label className="mb-1 block text-sm font-medium">Posto</label>
              <Select value={postId || undefined} onValueChange={setPostId}>
                <SelectTrigger className="h-12">
                  <SelectValue placeholder="Selecione o posto" />
                </SelectTrigger>
                <SelectContent>
                  {postos.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.nome}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium">
              Descrição <span className="text-red-500">*</span>
            </label>
            <Textarea
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              placeholder="Descreva o que aconteceu…"
              rows={4}
              className="text-base"
            />
            <p className={`mt-1 text-xs ${descOk ? 'text-muted-foreground' : 'text-amber-600'}`}>
              {descOk
                ? `${descricao.trim().length} caracteres`
                : `Mínimo ${MIN_DESC} caracteres (faltam ${Math.max(0, MIN_DESC - descricao.trim().length)})`}
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Título (opcional)</label>
            <Input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder={tituloAuto || 'Gerado automaticamente'}
              className="h-12 text-base"
            />
          </div>
        </CardContent>
      </Card>

      <Button
        onClick={enviar}
        disabled={!podeEnviar}
        isLoading={enviando}
        size="lg"
        className="w-full"
      >
        <Send className="mr-2 h-5 w-5" />
        Registrar ocorrência
      </Button>
    </div>
  );
}
