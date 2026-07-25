# Fechamento & Apuração de resultado — Design (spec)

**Data:** 2026-07-25 · **Onda 2, sub-projeto 1** · Autonomia total (Jordan). Método superpowers.

## Goal
Expor no redesign o que já existe REAL mas está órfão (recon confirmou): **Apuração de IRPJ/CSLL (Lucro Real, do razão)** e **DRE consolidado**, e o **fechamento de período** (travar/reabrir). Torna Balanço/DRE utilizáveis pelo contador e fecha o ciclo contábil na tela.

## Fato (investigado)
- `ApuracaoLucroRealService.apurar(ano, trimestre)` — REAL, do razão `accounting_entries` (honesto: prejuízo→zero, ressalvas explícitas). Retorna `base{receita_bruta, deducoes_iss, receita_liquida, despesas..., lucro_antes_ircsll}`, `apuracao{irpj_15, irpj_adicional_10, csll_9, total_irpj_csll, carga_sobre_receita_pct}`, `prejuizo_fiscal_compensavel`, `observacao`. Sync (psycopg2). Prova 2026: receita R$1.536.113, lucro R$509.926,68.
- Rotas órfãs (recon): `GET /relatorios/apuracao-lucro-real`, `GET /accounting/dre-consolidado`.
- `POST /accounting/periods/{id}/close` usa `repo.close_period` (flip de status; o PeriodClosingService completo fica pra depois — apuração de resultado→PL com provisões é outro sub-projeto).

## Global Constraints
- Read-only para relatório; fechamento de período = ação gated (write leve, não move dinheiro). Nunca fabricar (o serviço já é honesto). Deploy blue-green (lock). Oráculo. Superpowers.

## Arquitetura
### U1 — Tela "Apuração de resultado (Lucro Real)" (g-fiscal, read-only)
Builder `_fin_contabil.py` chama `apurar(ano_corrente)` via `run_in_threadpool` (sync). KPIs: Receita líquida, Lucro antes IR/CSLL, IRPJ+CSLL total, Carga %. Painéis: base de cálculo (breakdown) + apuração (IRPJ 15%/adicional/CSLL) + a `observacao` honesta + prejuízo fiscal compensável. Painel dos 4 trimestres (apurar por trimestre).
### U2 — Fechamento de período (g-fiscal): expor lista de períodos (já existe cadastro) + ação gated "Fechar período" / "Reabrir" → `/accounting/periods/{id}/close|reopen`. (Se a complexidade do id/uuid pesar, v1 = só a Apuração; fechamento fica sub-projeto próprio.)

## Testing / Oráculo
Apuração exibida == `apurar()` == query no razão. Fechamento: verificar que a rota existe/gated; NÃO fechar período real em teste sem necessidade.

## Pré-mortem
- **A.** apurar sync bloqueia o event loop no build. *Mit.:* run_in_threadpool.
- **B.** Números confundem (ressalvas de março). *Mit.:* exibir a `observacao` do serviço (já explica).
- **C.** Fechar período é irreversível-ish. *Mit.:* gated + reabrir disponível; v1 pode adiar o fechamento e entregar só a apuração.

## Escopo
- Nesta spec: **Apuração de resultado** (tela read-only) — o item de maior valor/menor risco. Fechamento de período gated se couber; senão, próximo sub-projeto.
- Fora: apuração de resultado→PL com provisões (PeriodClosingService completo) = sub-projeto "provisões/fechamento pleno".

---

## Extensão 2026-07-25 (Ondas 2/3 — itens isoláveis destravados)

Contexto: T2 leva tempo na folha, mas a razão (`accounting_entries`) já está populada e
tem schema estável (T2 *adiciona* linhas, não reestrutura) → **ler** a razão é seguro.
Isso destrava dois itens da auditoria (`🔴 AUSENTE`) que dependiam só de leitura:

1. **Índices de liquidez & endividamento** — do razão real, ao lado do Balanço.
   - Ativo Circulante = saldo das contas `1.1.*`; Passivo Circulante = `2.1.*`.
   - Liquidez corrente = AC/PC; Endividamento geral = Passivo/Ativo; Composição = PC/Passivo.
   - Só índices computáveis do dado real; nada de "seca" se estoque não for isolável no plano.
2. **DRE por regime de CAIXA** — dos fluxos bancários (`bank_transactions`), distinto da
   DRE por competência (get_dre). Receitas recebidas (credit+pix_recebido+boleto_recebido)
   − despesas pagas (debit+ted+pix_enviado+saque+boleto_pago), agrupado por `category`.
   Deixa explícito que é caixa (dinheiro que entrou/saiu), não competência.

Ambos read-only, isolados da folha, verificados por import fresco (oráculo), commit sem bake.
