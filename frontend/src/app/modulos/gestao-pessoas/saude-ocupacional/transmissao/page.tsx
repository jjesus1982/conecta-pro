'use client';

/**
 * CENTRAL DE TRANSMISSÃO eSocial (Missão M2) — backlog SST em lotes assistidos.
 *
 * HONESTIDADE: transmissão = evento LEGAL REAL (ESOCIAL_AMBIENTE=producao).
 * - Itens já existentes no governo (espelho oficial) NUNCA aparecem na fila.
 * - "Enfileirado" ≠ "aceito": o recibo real vem do beat esocial-pull-recibos (2h).
 * - S-2240 de ASG fica bloqueado no gate humano MB (código biológico em disputa).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FileCheck,
  Loader2,
  Lock,
  RefreshCw,
  Send,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import api from '@/lib/api';

// ---------------------------------------------------------------------------
// Tipos (espelham GET /sst/esocial/fila e /sst/esocial/acompanhamento)
// ---------------------------------------------------------------------------

interface FilaItem {
  tipo: string;
  ref_id: string;
  funcionario: string;
  cargo: string | null;
  detalhe: string;
  situacao_espelho: 'ja_no_governo' | 'ausente' | 'nao_verificado';
  esocial_status: string | null;
  dry_run_ok: boolean | null;
  dry_run_erro: string | null;
  pronto: boolean;
  motivo_bloqueio: string | null;
}

interface FilaResumo {
  candidatos: number;
  prontos: number;
  erro_dado: number;
  ja_no_governo: number;
  aguardando_recibo: number;
  gate_mb: number;
}

interface FilaTipo {
  resumo: FilaResumo;
  itens: FilaItem[];
}

interface FilaResponse {
  gerado_em: string;
  ambiente: string;
  honestidade: string;
  gate_mb: string;
  resumo_geral: FilaResumo;
  tipos: Record<string, FilaTipo>;
}

interface AcompanhamentoEvento {
  tipo: string;
  ref_id: string;
  funcionario: string;
  esocial_status: string | null;
  esocial_protocolo: string | null;
  recibo: string | null;
  updated_at: string | null;
  grupo: 'aguardando_recibo' | 'recibo_casado' | 'rejeitado_ou_erro' | 'outro';
}

interface AcompanhamentoResponse {
  gerado_em: string;
  honestidade: string;
  contagem: Record<string, number>;
  eventos: AcompanhamentoEvento[];
}

interface LoteResponse {
  tipo: string;
  total_enfileirados: number;
  total_pulados: number;
  enfileirados: { ref_id: string; funcionario: string; task_id: string }[];
  pulados: { ref_id: string; motivo: string }[];
  nota: string;
}

const TIPO_LABEL: Record<string, string> = {
  'S-2220': 'S-2220 — Monitoramento da Saúde (ASO)',
  'S-2230': 'S-2230 — Afastamento Temporário',
  'S-2240': 'S-2240 — Condições Ambientais (Riscos)',
};

const MAX_LOTE = 20;

// ---------------------------------------------------------------------------
// Badges honestos por estado
// ---------------------------------------------------------------------------

function ItemBadge({ item }: { item: FilaItem }) {
  if (item.motivo_bloqueio && item.dry_run_ok === null) {
    return (
      <Badge className="bg-amber-100 text-amber-900" title={item.motivo_bloqueio}>
        <Lock className="mr-1 h-3 w-3" /> gate-MB
      </Badge>
    );
  }
  if (item.pronto) {
    return (
      <Badge className="bg-green-100 text-green-800">
        <CheckCircle className="mr-1 h-3 w-3" /> pronto
      </Badge>
    );
  }
  return (
    <Badge className="bg-red-100 text-red-800" title={item.dry_run_erro || undefined}>
      <XCircle className="mr-1 h-3 w-3" /> erro-dado
    </Badge>
  );
}

function EspelhoBadge({ situacao }: { situacao: FilaItem['situacao_espelho'] }) {
  if (situacao === 'ja_no_governo') {
    return <Badge className="bg-blue-100 text-blue-800">já no governo</Badge>;
  }
  if (situacao === 'ausente') {
    return <Badge variant="outline">ausente no governo (espelho verificado)</Badge>;
  }
  return (
    <Badge variant="outline" className="text-muted-foreground">
      espelho não verificado
    </Badge>
  );
}

function GrupoBadge({ grupo }: { grupo: AcompanhamentoEvento['grupo'] }) {
  if (grupo === 'recibo_casado') {
    return (
      <Badge className="bg-green-100 text-green-800">
        <FileCheck className="mr-1 h-3 w-3" /> recibo casado
      </Badge>
    );
  }
  if (grupo === 'rejeitado_ou_erro') {
    return (
      <Badge className="bg-red-100 text-red-800">
        <XCircle className="mr-1 h-3 w-3" /> rejeitado/erro
      </Badge>
    );
  }
  return (
    <Badge className="bg-blue-100 text-blue-800">
      <Clock className="mr-1 h-3 w-3" /> aguardando recibo (pull 2h)
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Card de um tipo de evento (fila + seleção + lote)
// ---------------------------------------------------------------------------

function TipoCard({
  tipo,
  fila,
  ambiente,
  onTransmitido,
}: {
  tipo: string;
  fila: FilaTipo;
  ambiente: string;
  onTransmitido: () => void;
}) {
  const [selecionados, setSelecionados] = useState<string[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const queryClient = useQueryClient();

  const prontos = useMemo(() => fila.itens.filter((i) => i.pronto), [fila.itens]);

  const transmitir = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<LoteResponse>('/api/v1/people-management/sst/esocial/transmitir-lote', {
        tipo,
        ref_ids: selecionados,
        max_itens: MAX_LOTE,
      });
      return data;
    },
    onSuccess: (data) => {
      toast.success(
        `${tipo}: ${data.total_enfileirados} evento(s) ENFILEIRADO(S) na fila gov.esocial` +
          (data.total_pulados ? ` — ${data.total_pulados} pulado(s) com motivo` : ''),
        { description: 'Enfileirado ≠ aceito: o recibo real vem do pull de 2h.' }
      );
      data.pulados.forEach((p) =>
        toast.warning(`Pulado ${p.ref_id.slice(0, 12)}…`, { description: p.motivo })
      );
      setSelecionados([]);
      setConfirmOpen(false);
      onTransmitido();
      queryClient.invalidateQueries({ queryKey: ['esocial-acompanhamento'] });
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        String(err);
      toast.error(`Falha no lote ${tipo}`, { description: detail });
      setConfirmOpen(false);
    },
  });

  const toggle = (refId: string) => {
    setSelecionados((prev) =>
      prev.includes(refId)
        ? prev.filter((r) => r !== refId)
        : prev.length >= MAX_LOTE
          ? prev
          : [...prev, refId]
    );
  };

  const selecionarProntos = () => {
    setSelecionados(prontos.slice(0, MAX_LOTE).map((i) => i.ref_id));
  };

  const r = fila.resumo;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">{TIPO_LABEL[tipo] || tipo}</CardTitle>
            <CardDescription>
              {r.candidatos} candidato(s) no backlog — fila mostra apenas o que NÃO está no
              governo
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-1 text-xs">
            <Badge className="bg-green-100 text-green-800">prontos: {r.prontos}</Badge>
            <Badge className="bg-red-100 text-red-800">erro-dado: {r.erro_dado}</Badge>
            <Badge className="bg-blue-100 text-blue-800">
              já no governo: {r.ja_no_governo}
            </Badge>
            <Badge className="bg-sky-100 text-sky-800">
              aguardando recibo: {r.aguardando_recibo}
            </Badge>
            {r.gate_mb > 0 && (
              <Badge className="bg-amber-100 text-amber-900">gate-MB: {r.gate_mb}</Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={selecionarProntos}
            disabled={prontos.length === 0}
          >
            Selecionar prontos (máx. {MAX_LOTE})
          </Button>
          {selecionados.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setSelecionados([])}>
              Limpar seleção
            </Button>
          )}
          <div className="grow" />
          <Button
            size="sm"
            disabled={selecionados.length === 0 || transmitir.isPending}
            onClick={() => setConfirmOpen(true)}
          >
            {transmitir.isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-1 h-4 w-4" />
            )}
            Transmitir lote ({selecionados.length})
          </Button>
        </div>

        <div className="max-h-80 overflow-y-auto rounded border">
          {fila.itens.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              Nada a transmitir neste tipo — backlog zerado ou tudo já no governo/aguardando
              recibo.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/80 text-left text-xs uppercase">
                <tr>
                  <th className="w-8 p-2" />
                  <th className="p-2">Funcionário</th>
                  <th className="p-2">Detalhe</th>
                  <th className="p-2">Espelho</th>
                  <th className="p-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {fila.itens.map((item) => (
                  <tr key={item.ref_id} className="border-t align-top">
                    <td className="p-2">
                      <input
                        type="checkbox"
                        aria-label={`Selecionar ${item.funcionario}`}
                        checked={selecionados.includes(item.ref_id)}
                        disabled={!item.pronto}
                        onChange={() => toggle(item.ref_id)}
                      />
                    </td>
                    <td className="p-2">
                      <div className="font-medium">{item.funcionario}</div>
                      <div className="text-xs text-muted-foreground">{item.cargo}</div>
                    </td>
                    <td className="p-2">
                      <div>{item.detalhe}</div>
                      {item.dry_run_erro && (
                        <div className="mt-1 text-xs text-red-700">{item.dry_run_erro}</div>
                      )}
                      {item.motivo_bloqueio && item.dry_run_ok === null && (
                        <div className="mt-1 text-xs text-amber-800">
                          {item.motivo_bloqueio}
                        </div>
                      )}
                    </td>
                    <td className="p-2">
                      <EspelhoBadge situacao={item.situacao_espelho} />
                    </td>
                    <td className="p-2">
                      <ItemBadge item={item} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </CardContent>

      {/* CONFIRMAÇÃO EXPLÍCITA — evento legal real */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-700">
              <ShieldAlert className="h-5 w-5" />
              Confirmar transmissão REAL ao eSocial
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="font-semibold">
              Você vai transmitir {selecionados.length} evento(s) {tipo} LEGAIS REAIS ao
              eSocial {ambiente === 'producao' ? 'PRODUÇÃO' : ambiente} (CNPJ
              35.710.481/0001-03).
            </p>
            <p>
              Isto não é simulação: cada evento entra no registro oficial do governo e a
              retificação/exclusão posterior exige eventos próprios (S-3000).
            </p>
            <p className="text-muted-foreground">
              Enfileirado ≠ aceito: as tasks transmitem com 2s de intervalo e o recibo
              oficial só aparece quando o pull de 2h o casar. Acompanhe no painel abaixo.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              disabled={transmitir.isPending}
              onClick={() => transmitir.mutate()}
            >
              {transmitir.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Transmitir {selecionados.length} evento(s) REAIS
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export default function TransmissaoESocialPage() {
  const {
    data: fila,
    isLoading: filaLoading,
    isFetching: filaFetching,
    refetch: refetchFila,
    error: filaError,
  } = useQuery<FilaResponse>({
    queryKey: ['esocial-fila'],
    queryFn: async () => {
      const { data } = await api.get<FilaResponse>('/api/v1/people-management/sst/esocial/fila');
      return data;
    },
    staleTime: 60_000, // a fila roda dry-run item a item — não martelar o backend
    refetchOnWindowFocus: false,
  });

  const { data: acomp, isFetching: acompFetching } = useQuery<AcompanhamentoResponse>({
    queryKey: ['esocial-acompanhamento'],
    queryFn: async () => {
      const { data } = await api.get<AcompanhamentoResponse>(
        '/api/v1/people-management/sst/esocial/acompanhamento'
      );
      return data;
    },
    refetchInterval: 30_000, // protocolo → recibo ao vivo
  });

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Central de Transmissão eSocial</h1>
          <p className="text-sm text-muted-foreground">
            Backlog SST (S-2220 / S-2230 / S-2240) em lotes assistidos — anti-duplicidade
            pelo espelho oficial do governo
          </p>
        </div>
        <div className="flex items-center gap-2">
          {fila && (
            <Badge
              className={
                fila.ambiente === 'producao'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-yellow-100 text-yellow-800'
              }
            >
              ambiente: {fila.ambiente}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={() => refetchFila()}>
            <RefreshCw className={`mr-1 h-4 w-4 ${filaFetching ? 'animate-spin' : ''}`} />
            Recarregar fila
          </Button>
        </div>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Honestidade operacional</AlertTitle>
        <AlertDescription>
          Transmitir aqui gera evento LEGAL REAL no eSocial produção. Enfileirado ≠ aceito:
          o recibo oficial vem do pull automático a cada 2h. Itens já existentes no governo
          (espelho) nunca entram na fila; dado faltante aparece como erro honesto — nunca é
          fabricado. S-2240 da função ASG está bloqueado até a Márcia/MB confirmar o código
          biológico (03.01.999 vs 03.01.007).
        </AlertDescription>
      </Alert>

      {filaLoading && (
        <div className="flex items-center gap-2 p-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Montando a fila (dry-run item a item, sem transmitir)…
        </div>
      )}
      {filaError != null && (
        <Alert variant="destructive">
          <AlertTitle>Falha ao carregar a fila</AlertTitle>
          <AlertDescription>{String(filaError)}</AlertDescription>
        </Alert>
      )}

      {fila &&
        (['S-2220', 'S-2230', 'S-2240'] as const).map(
          (tipo) =>
            fila.tipos[tipo] && (
              <TipoCard
                key={tipo}
                tipo={tipo}
                fila={fila.tipos[tipo]}
                ambiente={fila.ambiente}
                onTransmitido={() => refetchFila()}
              />
            )
        )}

      {/* Acompanhamento: protocolo → recibo ao vivo */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">
                Acompanhamento (protocolo → recibo)
              </CardTitle>
              <CardDescription>
                Últimas transmissões próprias — atualiza a cada 30s; o recibo real é casado
                pelo beat esocial-pull-recibos (2h)
              </CardDescription>
            </div>
            {acompFetching && <Loader2 className="h-4 w-4 animate-spin" />}
          </div>
          {acomp && (
            <div className="flex flex-wrap gap-1 pt-2 text-xs">
              <Badge className="bg-blue-100 text-blue-800">
                aguardando recibo: {acomp.contagem.aguardando_recibo ?? 0}
              </Badge>
              <Badge className="bg-green-100 text-green-800">
                recibos casados: {acomp.contagem.recibo_casado ?? 0}
              </Badge>
              <Badge className="bg-red-100 text-red-800">
                rejeitados/erro: {acomp.contagem.rejeitado_ou_erro ?? 0}
              </Badge>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {!acomp || acomp.eventos.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma transmissão própria registrada ainda.
            </p>
          ) : (
            <div className="max-h-96 overflow-y-auto rounded border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted/80 text-left text-xs uppercase">
                  <tr>
                    <th className="p-2">Evento</th>
                    <th className="p-2">Funcionário</th>
                    <th className="p-2">Protocolo</th>
                    <th className="p-2">Recibo</th>
                    <th className="p-2">Situação</th>
                    <th className="p-2">Atualizado</th>
                  </tr>
                </thead>
                <tbody>
                  {acomp.eventos.map((ev) => (
                    <tr key={`${ev.tipo}-${ev.ref_id}`} className="border-t">
                      <td className="p-2 font-mono text-xs">{ev.tipo}</td>
                      <td className="p-2">{ev.funcionario}</td>
                      <td className="p-2 font-mono text-xs">
                        {ev.esocial_protocolo || '—'}
                      </td>
                      <td className="p-2 font-mono text-xs">{ev.recibo || '—'}</td>
                      <td className="p-2">
                        <GrupoBadge grupo={ev.grupo} />
                      </td>
                      <td className="p-2 text-xs text-muted-foreground">
                        {ev.updated_at ? new Date(ev.updated_at).toLocaleString('pt-BR') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
