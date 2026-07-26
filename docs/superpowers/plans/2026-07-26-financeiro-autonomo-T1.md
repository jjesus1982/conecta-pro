# Plano de Trabalho — Financeiro Autônomo (faixa T1) · Implementation Plan

> **Executar via:** superpowers:executing-plans, task-a-task, no loop autônomo. Verificação por ORÁCULO
> (curl/query vs banco). Master design: `docs/PRD_financeiro_autonomo.md`.

**Goal:** Ligar tudo que já existe no backend financeiro à UI/UX + acender o CFO agente proativo, na
faixa T1 (razão/SPED/guias/banco/CFO/UI). Sem tocar o motor de folha (T2). Sem reconstruir o que existe.

**Guardrails (sempre):** oráculo (exibido==banco, nunca fabricar) · money-out=OTP fora dos agentes ·
agentes propõem, humano decide+OTP · legal/fiscal não se inventa · deploy blue-green backend +
`docker-compose.yml` (NÃO prod.yml) frontend · árvore compartilhada (commit, bake em janela limpa).

---

## FASE 1 — Quick wins UI (infra pronta, só emitir o campo) · reusa gráficos
### Task A1: Drill-down (emitir `to` nos KPIs → renderer já navega)
- [x] Balanço: Ativo/Passivo→balancete, PL→apuracao-resultado (commit feito)
- [ ] Visão/projeção: saldo→consolidacao-grupo, entradas→contas-receber, saídas→contas-pagar
- [ ] Indicadores DSO/DPO: AR→contas-receber, AP→contas-pagar
- [ ] DAS/tributos: →apuracao-resultado; DRE-caixa: →bancos
- [ ] Oráculo: curl /redesign/data/financeiro → KPIs têm `to` válido (slug existe). Commit por bloco.

### Task A2: Tendências temporais (alimentar `charts:[{type:'line'}]` das queries mensais que já rodam)
- [ ] Faturamento NFS-e por mês (12m) → linha (query existe em financeiro.py)
- [ ] Saldo bancário / recebido por mês → linha (conciliação por mês _fin_bancos.py:77-98)
- [ ] Orçado×Realizado 12m (financeiro.py:325) → linha realizado
- [ ] DAS/tributos por competência → linha
- [ ] Oráculo: import fresco → charts type='line' com N pontos reais. Commit.

### Task A5: Export de gráfico (hoje só tabela/doc tem ExportMenu)
- [ ] Botão "baixar PNG/PDF" no RdChart (client-side, sem backend). Commit.

## FASE 2 — B1 Skills→cérebro (maior alavanca de IA)
### Task B1: cfo_service.consultar injeta as skills cirúrgicas por lente
- [ ] Mapear lente→skills (fluxo_caixa→[projecao,fluxo-real,kpis], resultado→[dre-gerencial,margem],
      tributos→[...], estrategico→[diagnostico,riscos]) — as 16 .md em skills/financeiro
- [ ] `cfo_service.consultar`: antes do `_hub.gerar`, `SkillLoader.load_multiple(skills_da_lente)` e
      colar no system_prompt (já vai pro Hermes) — SEM quebrar o contexto_conhecimento atual
- [ ] Oráculo: perguntar ao CFO uma questão de precificação → resposta cita o framework da skill
      (comparar com/sem skill injetada); provar que a skill chegou ao modelo
- [ ] Commit. (Deploy backend blue-green quando janela limpa.)

## FASE 3 — Interatividade profunda + CFO proativo
### Task A3: Filtros globais (período + CNPJ) — ligar `filterCol` no financeiro + estado compartilhado
- [ ] `filterCol` nas telas com competência (orçamentos, conciliação, tributos)
- [ ] Seletor CNPJ (Eletrônica/Patrimonial) que refiltra telas multi-CNPJ
- [ ] Oráculo: seletor muda os dados exibidos == query com o filtro. Commit.

### Task A4: Cockpit executivo (compor o g-visao numa landing única)
- [ ] Tela `cockpit`: KPIs-chave + 3-4 gráficos principais + alertas IA + resumo do CFO, num painel só
- [ ] Vira a primeira tela do financeiro. Oráculo: tudo dado real. Commit.

### Task B2: CFO proativo (regra 5.3 → mini-diagnóstico do CFO num achado)
- [ ] Regra que, ao detectar achado financeiro, chama cfo_service p/ um parágrafo de diagnóstico no sino
- [ ] Oráculo: achado real dispara → sino tem o diagnóstico do CFO. Commit.

### Task B3: Mais regras financeiras no sino (proativo 5.3)
- [ ] Vencimento de recebível por cliente · margem/DRE fora de meta · tributo/guia a vencer ·
      concentração de pagáveis — cada uma SQL determinística, fail-closed, RBAC
- [ ] Oráculo por regra: dispara quando a condição real ocorre. Commit por regra.

## FASE 4 — Ações gated + hook eSocial (desbloqueia T2)
### Task H1: Hook eSocial-propor (entregável de coordenação p/ T2)
- [ ] `/action/propor-esocial-sst` (redesign) → chama `base.propor()` da 5.4 (onda_c propor_esocial),
      grava PENDENTE, aprovador ROLES_MONEY, execução real fica no fluxo SST do T2
- [ ] Entregar ao T2 o endpoint + shape do payload. Oráculo: propõe sem transmitir. Commit.

### Task B4: Mais ações 5.4 financeiras (propor→aprovar, gated)
- [ ] propor_provisionar · propor_baixa/quitação de recebível · propor_acordo de inadimplência
      (collection_negotiator já analisa; falta PROPOR). Cada uma fail-closed, propositor≠aprovador
- [ ] Oráculo: propõe PENDENTE, nunca executa. Commit por ação.

## FASE 5 — Contabilidade/fisco próprios (T1) — coordenado com folha do T2
### Task C3: Postar folha→razão (consome a folha autoritativa do T2)
- [ ] Quando T2 entregar `hr_payslips source='conecta'`: `ledger_auto` posta com encargos completos
      (INSS patronal + FGTS + provisões). Oráculo: razão fecha, apuração reflete. (Aguarda C1 do T2.)

### Task C4: Guias reais (código de barras/PIX válido — hoje simulado)
- [ ] DAS (PGDAS-D), FGTS Digital (Caixa), DARF (barcode SERPRO/Sicalc), GPS. Cada uma: gera doc pagável
- [ ] Oráculo: barcode/linha digitável válidos (checksum). Commit por guia.

### Task C5: Geradores SPED (T1)
- [ ] ECD completa (plano referencial I051 + saldos abertura + blocos J + encerramento)
- [ ] ECF (novo), EFD-Contribuições (novo), DEFIS, PGDAS-D declaração
- [ ] Fonte = Onvio/Domínio (importador) OU razão próprio. Oráculo: arquivo valida (0 erros PVA). Commit.

## Consolidação
### Task B5: Aposentar orchestrator legado (manter só gedeon_financial_orchestrator)
- [ ] Confirmar callers do legado; migrar; remover. Commit.

## Ordem no loop
FASE 1 (A1→A2→A5) → FASE 2 (B1) → FASE 3 (A3→A4→B2→B3) → FASE 4 (H1→B4) → FASE 5 (C4→C5; C3 quando T2 entregar) → B5.
Bake quando a árvore compartilhada estiver limpa; frontend via docker-compose.yml.
