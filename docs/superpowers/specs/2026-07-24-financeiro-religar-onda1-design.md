# Financeiro — Onda 1 "RELIGAR" — Design (spec)

**Data:** 2026-07-24 · **Origem:** `auditoria/AUDITORIA_FINANCEIRO_DESLIGADO_2026-07-24.md`
**Autor:** T1 (Claude Opus 4.8) · **Aprovação:** Jordan delegou ("você define o quê e como, quero o resultado final")

## Goal
Religar as capacidades financeiras que **já existem no backend mas estão desligadas por wiring/agendador/re-apontamento** — sem construir features novas. Retorno rápido, risco baixo, e cada item vira músculo pronto pro CFO do T3 orquestrar.

## Global Constraints (inegociáveis — herdadas do projeto)
- **Nunca fabricar dado:** oráculo = exibido == banco (curl vs query). Vazio real = "aguardando dado".
- **Dinheiro que SAI = gate OTP humano.** Não testar caminho feliz (move dinheiro real).
- **Cobrança (dinheiro que ENTRA) que fatura cliente real = gate humano** (prévia → confirmar). Nunca disparo silencioso.
- Deploy backend **blue-green**; frontend **rebuild** (container). Verificar pela **rota da tela**, cache-bust.
- Mexer só no que serve a Onda 1. Sem refactor não relacionado.

## Escopo da Onda 1 (6 itens)

### 1. Insights financeiros — corrigir wiring (tela vazia → motor real)
- **Problema:** `redesign_builders/_fin_visao.py:55-57` chama `svc.identificar_riscos(None,90)` / `identificar_oportunidades(None,90)`; os métodos reais em `cashflow_ai_service.py` são `_identify_risks` (`:447`) e `_identify_opportunities` (`:504`), privados → `hasattr`=False → painel sempre vazio. Também passa `condominio_id=None`.
- **Design:** adicionar wrappers públicos `identificar_riscos(escopo, horizonte)` e `identificar_oportunidades(...)` em `CashFlowAIService` que chamam os privados com o escopo certo (empresa/global, não condomínio). Corrigir `_fin_visao` para usar o escopo real. Alternativa avaliada: plugar no `/financial/ai/command-center` (Motor A) — descartada por acoplar a tela a outro controller; wrapper é menor e local.
- **Verificação:** curl da rota `/redesign/data/financeiro` → grupo Visão mostra riscos/oportunidades reais; provar que os itens vêm de query (inadimplência/vencimentos reais), não hardcoded.
- **Risco:** baixo (read-only).

### 2. Balanço Patrimonial — re-apontar razão + expor
- **Problema:** `balance_sheet_service.py:328` lê `fin_journal_entries` (VAZIO) → sempre "sem dados". O razão real é `accounting_entries` (populado, usado pelo DRE fallback).
- **Design:** criar caminho que monta Ativo/Passivo/PL agregando `accounting_entries` por natureza da conta (mesmo padrão de `_dre_simplificado`). Expor no redesign (grupo Fiscal & Contábil, nova aba "Balanço Patrimonial") + PDF se trivial. Não apagar o serviço ORM; adicionar o caminho que lê o razão certo.
- **Verificação:** Ativo = Passivo + PL (fecha); números batem com soma do razão via query.
- **Risco:** baixo-médio (relatório read-only; cuidado com classificação de contas).

### 3. Orçado × Realizado — re-apontar realizado + ligar ao orçamento manual
- **Problema:** `budget_service.py:306` lê realizado do razão vazio; orçado do `cost_center.budget_monthly`. Existe tabela KV `financial_orcamentos` que Jordan/Pyetra já editam (`relatorios_controller.py:64`).
- **Design:** realizado ← `accounting_entries` por conta/período; orçado ← `financial_orcamentos` (KV). Comparar com variância + % + sinal (favorável/desfavorável) e alerta de estouro. Expor no redesign (grupo Custos & Orçamento).
- **Verificação:** realizado por categoria == query no razão; orçado == valor no KV.
- **Risco:** médio (mapear chave do KV ↔ conta/categoria).

### 4. Conciliação automática — expor no redesign + matar bug 500
- **Problema:** motor `reconciliation_service.py` (3 estratégias) e rotas `/financial/conciliar/*` funcionam, mas não há tela no redesign. E `GET /financial/bank-transactions/pending-reconciliation` dá **500**: `bank_transaction_controller.py:149` chama `repo.get_pending_reconciliation(acc, limit)` mas o repo exige `(acc, start_date, end_date)` (`cashflow_repository.py:277`).
- **Design:** (a) corrigir a assinatura — alinhar controller↔repo (passar datas ou aceitar `limit`). (b) Expor no grupo Bancos & Conciliação uma tela que lista pendentes (`/conciliar/pendentes`), roda auto-match (`/conciliar/auto`) e permite justificar. Auto-match é bookkeeping interno (não move dinheiro).
- **Verificação:** rota pending-reconciliation → 200; nº de conciliados/pendentes == query em `bank_transactions`.
- **Risco:** baixo (não move dinheiro; muda `reconciliation_status`).

### 5. Import OFX — corrigir 2 bugs de gravação + expor upload
- **Problema:** parser OFX ok, mas grava `TransactionCategory.OUTROS` (membro inexistente — só `OUTRAS_RECEITAS`/`OUTRAS_DESPESAS`) e `statement_reference` (coluna inexistente; o campo é `reference`) → 400. Em `bank_transaction_controller.py:580,584` (e a rota `import` genérica `:507,516`).
- **Design:** trocar por membro válido (por sinal do valor: crédito→`OUTRAS_RECEITAS`, débito→`OUTRAS_DESPESAS`) e `statement_reference`→`reference`. Expor upload OFX na tela de Bancos.
- **Verificação:** subir um OFX de teste → 200 e linhas gravadas == linhas do arquivo (via query). Sem tocar dado real de produção.
- **Risco:** baixo.

### 6. Cobrança recorrente mensal — expor como AÇÃO GATED (não beat automático)
- **Problema:** motor `recurring_billing_service.py:131 gerar_cobrancas_mensais` gera PIX/boleto REAL (Inter/Cora) e insere em `receivable_accounts`; só roda por POST manual. **Fatura cliente real.**
- **Design (decisão de segurança):** **NÃO** criar beat que dispara sozinho. Expor no grupo Receber uma ação **gated**: (1) `/preview` mostra o que seria cobrado (clientes, valores, banco credor) — read-only; (2) botão "Gerar cobranças do mês" com **confirmação humana explícita** → chama o POST real. Sem OTP (não é dinheiro que sai), mas com confirmação obrigatória e mensagem clara "isto emite cobranças reais aos clientes".
- **Verificação:** só o `/preview` (read-only). **NUNCA** executar o POST real em teste (emitiria cobranças a clientes reais). Provar que o preview == query de clientes ativos/MRR.
- **Risco:** médio-alto se disparado — mitigado pelo gate humano + nunca testar o caminho feliz.

## Out of scope (Ondas 2 e 3)
Régua ativa (dispara), provisões/depreciação/rateio no razão, fechamento contábil (apuração), EFD-Reinf demais, negativação, antecipação, DSO/DPO/liquidez, DRE caixa, SPED ECF, Open Finance, CNAB, consolidação intercompany.

## Data flow (comum)
Tela redesign (`ModuleView`/`_fin_*` builder) → GET `/redesign/data/financeiro` (backend baked) → serviços/repos financeiros → Postgres (`accounting_entries`, `bank_transactions`, `receivable_accounts`, `financial_orcamentos`). Ações gated → POST `/redesign/action/*` ou rotas `/financial/*` existentes.

## Error handling
- Serviço sem dado real → "aguardando dado" honesto, nunca zero fabricado.
- Import OFX inválido → 400 com motivo claro.
- Conciliação sem match → `requires_justification=TRUE` (já é o comportamento).
- Cobrança recorrente → falha parcial por cliente não aborta os demais; relatório do que foi/não foi gerado.

## Testing / Oráculo
Cada item: **curl da rota da tela** vs **query no banco** (exibido == banco). Deploy blue-green + rebuild frontend + cache-bust. Browser E2E (Playwright) nos itens com tela. **Nunca** executar cobrança recorrente real nem qualquer caminho de dinheiro.

## Pré-mortem (o que poderia dar errado)
- **A.** Insights wrapper com escopo errado (condominio_id) → volta vazio de novo. *Mit.:* validar escopo empresa/global; provar itens reais no curl.
- **B.** Balanço não fecha (Ativo≠Passivo+PL) por classificação de conta errada. *Mit.:* conferir soma por natureza vs razão; marcar "não fechado" honesto se divergir.
- **C.** Orçado×Realizado com chave KV que não casa com conta → variância sem sentido. *Mit.:* mapa explícito KV↔conta; onde não houver, exibir "sem orçamento" honesto.
- **D.** Fix da assinatura de pending-reconciliation quebra outro caller. *Mit.:* grep callers antes; manter compat.
- **E.** OFX fix grava categoria errada em massa. *Mit.:* categoria por sinal; testar com arquivo isolado, não produção.
- **F.** Cobrança recorrente disparada sem querer → cobra clientes. *Mit.:* gate humano obrigatório + jamais testar o POST; só `/preview`.
- **G.** Deploy de builder não bakeia (docker cp volátil). *Mit.:* sempre blue-green; verificar no app rodando.
- **H.** Dois razões confundem (accounting_entries vs fin_journal_entries). *Mit.:* padronizar em accounting_entries (o populado), documentar no código.

## Decomposição da execução
Ordem por risco crescente: **1 (insights) → 4 (conciliação+500) → 5 (OFX) → 2 (balanço) → 3 (orçado×realizado) → 6 (cobrança gated)**. Cada item: editar host → deploy → verificar oráculo → (se tela) rebuild+browser. Commit por item.
