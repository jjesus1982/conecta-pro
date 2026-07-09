'use client';

/**
 * Rollout de Assinaturas — Fichas de EPI x Portal do Funcionario.
 *
 * As fichas so saem de "pendente de assinatura" quando o PROPRIO funcionario
 * loga no Portal e assina digitalmente. Esta secao mostra, por funcionario
 * ativo, quem ja tem acesso ao Portal, quem ja logou e quem tem ficha
 * pendente — e permite ATIVAR os acessos em massa reusando o fluxo existente
 * de primeiro acesso (CPF + data de nascimento -> funcionario cria a senha;
 * nenhuma senha temporaria e gerada).
 */

import { AlertCircle, Download, KeyRound, Printer, RefreshCw, UserCheck } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { useAtivarAcessosPortal, useRolloutAssinaturas } from '@/hooks/sst';
import {
  apiErrorDetail,
  type AtivarAcessoResultado,
  type RolloutFuncionario,
} from '@/lib/services/sst';

function situacaoBadge(r: AtivarAcessoResultado) {
  const map: Record<string, { label: string; className: string }> = {
    ativado: { label: 'Acesso liberado', className: 'bg-green-100 text-green-800' },
    ja_tinha_senha: { label: 'Ja tinha senha', className: 'bg-blue-100 text-blue-800' },
    pendencia_cadastro: { label: 'Pendencia de cadastro', className: 'bg-yellow-100 text-yellow-800' },
    erro: { label: 'Erro', className: 'bg-red-100 text-red-800' },
  };
  const item = map[r.situacao] ?? { label: r.situacao, className: 'bg-gray-100 text-gray-800' };
  return <Badge className={item.className}>{item.label}</Badge>;
}

function csvEscape(value: string | null | undefined): string {
  const v = (value ?? '').replace(/"/g, '""');
  return `"${v}"`;
}

export function RolloutAssinaturasSection() {
  const { data, isLoading, error, refetch } = useRolloutAssinaturas();
  const ativarAcessos = useAtivarAcessosPortal();

  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [resultados, setResultados] = useState<AtivarAcessoResultado[] | null>(null);

  const funcionarios = useMemo(() => data?.funcionarios ?? [], [data]);
  const resumo = data?.resumo;

  const semAcessoIds = useMemo(
    () => funcionarios.filter((f) => !f.tem_acesso_portal && f.pre_requisitos_ok).map((f) => f.employee_id),
    [funcionarios],
  );

  const toggle = (id: string) => {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selecionarSemAcesso = () => setSelecionados(new Set(semAcessoIds));
  const limparSelecao = () => setSelecionados(new Set());

  const handleAtivar = async () => {
    const ids = Array.from(selecionados);
    if (ids.length === 0) return;
    try {
      const res = await ativarAcessos.mutateAsync(ids);
      setResultados(res.resultados);
      setSelecionados(new Set());
      toast.success(`${res.ativados} acesso(s) ao Portal liberado(s)`, { duration: 5000 });
    } catch (err) {
      toast.error(apiErrorDetail(err, 'Erro ao ativar acessos ao Portal'), { duration: 6000 });
    }
  };

  const linhasCredenciais = (): AtivarAcessoResultado[] =>
    (resultados ?? []).filter((r) => r.situacao === 'ativado' || r.situacao === 'ja_tinha_senha');

  const exportarCSV = () => {
    const linhas = linhasCredenciais();
    if (linhas.length === 0) {
      toast.info('Nenhuma credencial para exportar. Ative acessos primeiro.');
      return;
    }
    const header = ['Nome', 'Cargo', 'CPF (mascarado)', 'Situacao', 'Credencial inicial', 'Link', 'Instrucoes'];
    const csv = [
      header.join(';'),
      ...linhas.map((r) =>
        [
          csvEscape(r.nome),
          csvEscape(r.cargo ?? ''),
          csvEscape(r.cpf_mascarado ?? ''),
          csvEscape(r.situacao === 'ativado' ? 'Acesso liberado' : 'Ja tinha senha'),
          csvEscape(r.credencial_inicial ?? ''),
          csvEscape(r.situacao === 'ativado' ? r.link_primeiro_acesso ?? '' : r.link_login ?? ''),
          csvEscape(r.instrucoes_funcionario ?? ''),
        ].join(';'),
      ),
    ].join('\n');
    const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rollout_assinaturas_portal_${new Date().toISOString().substring(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const imprimirLista = () => {
    const linhas = linhasCredenciais();
    if (linhas.length === 0) {
      toast.info('Nenhuma credencial para imprimir. Ative acessos primeiro.');
      return;
    }
    const origem = window.location.origin;
    const html = `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8" />
      <title>Rollout de Assinaturas — Acessos ao Portal do Funcionario</title>
      <style>
        body { font-family: Arial, sans-serif; font-size: 12px; margin: 24px; color: #111; }
        h1 { font-size: 16px; margin-bottom: 4px; }
        p.meta { color: #555; margin-top: 0; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #999; padding: 6px 8px; text-align: left; vertical-align: top; }
        th { background: #f0f0f0; }
        .instr { background: #f8f8f8; border: 1px solid #ccc; padding: 10px; margin-top: 16px; }
      </style></head><body>
      <h1>Acessos ao Portal do Funcionario — Assinatura das Fichas de EPI</h1>
      <p class="meta">Gerado em ${new Date().toLocaleString('pt-BR')} — entregar em maos nos postos.</p>
      <table><thead><tr><th>Funcionario</th><th>Cargo</th><th>CPF</th><th>Como entrar</th></tr></thead><tbody>
      ${linhas
        .map(
          (r) =>
            `<tr><td>${r.nome ?? ''}</td><td>${r.cargo ?? ''}</td><td>${r.cpf_mascarado ?? ''}</td><td>${
              r.situacao === 'ativado'
                ? `Primeiro acesso: ${origem}${r.link_primeiro_acesso ?? '/portal-funcionario/primeiro-acesso'} — informar CPF + data de nascimento e criar a propria senha.`
                : `Ja tem senha: ${origem}${r.link_login ?? '/portal-funcionario/login'} — CPF + senha (esqueceu? Redefinir com CPF + data de nascimento).`
            }</td></tr>`,
        )
        .join('')}
      </tbody></table>
      <div class="instr"><strong>Depois de entrar:</strong> no Portal, abrir <strong>Minhas Fichas de EPI</strong>,
      conferir os itens recebidos e tocar em <strong>Assinar</strong>. A assinatura e digital (hash SHA-256) e vale para a NR-6.</div>
      </body></html>`;
    const w = window.open('', '_blank');
    if (!w) {
      toast.error('Bloqueador de pop-up impediu a impressao. Libere pop-ups e tente de novo.');
      return;
    }
    w.document.write(html);
    w.document.close();
    w.focus();
    w.print();
  };

  return (
    <div className="space-y-4">
      {/* Cabecalho da secao */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Rollout de Assinaturas — Portal do Funcionario
            </CardTitle>
            <CardDescription>
              A ficha de EPI so e assinada pelo PROPRIO funcionario, logado no Portal. Aqui voce ve quem
              esta pronto e libera os acessos em massa.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Resumo */}
          {resumo && (
            <div className="grid gap-3 md:grid-cols-5">
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Funcionarios ativos</p>
                <p className="font-data text-xl font-semibold tabular-nums">{resumo.total_ativos}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Com acesso ao Portal</p>
                <p className="font-data text-xl font-semibold tabular-nums text-green-600">
                  {resumo.com_acesso_portal}
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Sem acesso</p>
                <p className="font-data text-xl font-semibold tabular-nums text-yellow-600">
                  {resumo.sem_acesso_portal}
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Fichas pendentes</p>
                <p className="font-data text-xl font-semibold tabular-nums text-yellow-600">
                  {resumo.total_fichas_pendentes}
                </p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-xs text-muted-foreground">Prontos p/ assinar</p>
                <p className="font-data text-xl font-semibold tabular-nums text-blue-600">
                  {resumo.prontos_para_assinar}
                </p>
              </div>
            </div>
          )}

          {/* Card explicativo do fluxo */}
          <div className="rounded-lg border bg-muted/40 p-4 text-sm space-y-1">
            <p className="font-medium">Fluxo para o funcionario (entregar em maos nos postos):</p>
            <ol className="list-decimal ml-5 space-y-0.5 text-muted-foreground">
              <li>
                Abrir o Portal do Funcionario e tocar em <strong>Primeiro acesso</strong>{' '}
                (<span className="font-mono text-xs">/portal-funcionario/primeiro-acesso</span>).
              </li>
              <li>Informar <strong>CPF + data de nascimento</strong> e criar a propria senha.</li>
              <li>
                Entrar no Portal e abrir <strong>Minhas Fichas de EPI</strong> → conferir os itens →{' '}
                <strong>Assinar</strong>.
              </li>
            </ol>
            <p className="text-xs text-muted-foreground">
              Nenhuma senha temporaria e gerada: a ativacao reusa o mecanismo existente do Portal
              (validacao por CPF + data de nascimento). A assinatura e digital, com hash SHA-256 e
              rastreio de IP — vale como ficha de EPI da NR-6.
            </p>
          </div>

          {/* Acoes de selecao */}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={selecionarSemAcesso}>
              Selecionar sem acesso ({semAcessoIds.length})
            </Button>
            <Button variant="outline" size="sm" onClick={limparSelecao} disabled={selecionados.size === 0}>
              Limpar selecao
            </Button>
            <Button
              size="sm"
              onClick={handleAtivar}
              disabled={ativarAcessos.isPending || selecionados.size === 0}
            >
              <UserCheck className="h-4 w-4 mr-2" />
              {ativarAcessos.isPending ? 'Ativando...' : `Ativar acessos (${selecionados.size})`}
            </Button>
          </div>

          {/* Tabela */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : error ? (
            <div className="px-2 py-6 text-sm text-destructive flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              {apiErrorDetail(error, 'Erro ao carregar o rollout de assinaturas')}
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : (
            <div className="rounded-lg border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[36px]"></TableHead>
                    <TableHead>Funcionario</TableHead>
                    <TableHead>Cargo</TableHead>
                    <TableHead>Posto</TableHead>
                    <TableHead>Acesso ao Portal</TableHead>
                    <TableHead>Ja logou</TableHead>
                    <TableHead className="text-right">Fichas pendentes</TableHead>
                    <TableHead className="text-right">Entregas sem ficha</TableHead>
                    <TableHead>Pronto p/ assinar</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {funcionarios.map((f: RolloutFuncionario) => (
                    <TableRow key={f.employee_id}>
                      <TableCell>
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-primary"
                          checked={selecionados.has(f.employee_id)}
                          onChange={() => toggle(f.employee_id)}
                          aria-label={`Selecionar ${f.nome}`}
                        />
                      </TableCell>
                      <TableCell className="font-medium">
                        {f.nome}
                        {!f.pre_requisitos_ok && (
                          <p className="text-xs text-destructive">
                            Cadastro incompleto (CPF/data de nascimento) — corrigir no DP
                          </p>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">{f.cargo || '—'}</TableCell>
                      <TableCell className="text-sm">{f.posto || '—'}</TableCell>
                      <TableCell>
                        {f.tem_acesso_portal ? (
                          <Badge className="bg-green-100 text-green-800">Com acesso</Badge>
                        ) : (
                          <Badge className="bg-yellow-100 text-yellow-800">Sem acesso</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {f.ja_logou ? (
                          <span className="text-green-700">
                            Sim
                            {f.ultimo_login
                              ? ` (${new Date(f.ultimo_login).toLocaleDateString('pt-BR')})`
                              : ''}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Nunca</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.fichas_pendentes > 0 ? (
                          <span className="font-semibold text-yellow-700">{f.fichas_pendentes}</span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.entregas_sem_ficha > 0 ? (
                          <span className="text-muted-foreground">{f.entregas_sem_ficha}</span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {f.pronto_para_assinar ? (
                          <Badge className="bg-blue-100 text-blue-800">Pronto</Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {f.fichas_pendentes === 0 ? 'Sem ficha pendente' : 'Falta acesso'}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Notas de honestidade do dado */}
          {(data?.notas ?? []).length > 0 && (
            <ul className="text-xs text-muted-foreground list-disc ml-4 space-y-0.5">
              {(data?.notas ?? []).map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Resultado da ativacao + export */}
      {resultados && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Credenciais iniciais para distribuir</CardTitle>
              <CardDescription>
                Lista para o gestor entregar em maos nos postos. Nenhuma senha foi gerada — o
                funcionario cria a propria no primeiro acesso.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={exportarCSV}>
                <Download className="h-4 w-4 mr-2" />
                Exportar CSV
              </Button>
              <Button variant="outline" size="sm" onClick={imprimirLista}>
                <Printer className="h-4 w-4 mr-2" />
                Imprimir
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>CPF</TableHead>
                  <TableHead>Situacao</TableHead>
                  <TableHead>Como entrar</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resultados.map((r) => (
                  <TableRow key={r.employee_id}>
                    <TableCell className="font-medium">{r.nome || r.employee_id.substring(0, 8)}</TableCell>
                    <TableCell className="text-sm font-mono">{r.cpf_mascarado || '—'}</TableCell>
                    <TableCell>{situacaoBadge(r)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-[420px]">
                      {r.instrucoes_funcionario || r.detalhe || '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
