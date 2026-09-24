# DGX F11 — Financeiro/Faturamento: os cadastros pequenos do DGX

**Data:** 24/09/2026 · **Branch:** `dgx/f11-financeiro` · **Módulo:** financeiro · **Sandbox:** cópia de produção de 23/09
**Deep-link:** `/redesign/financeiro?t=<id>` (ids na §3)

## §1 — Estado antes (medido no sandbox)

| Item DGX | O que já existia aqui | Medido |
|---|---|---|
| Condições de pagamento | Nada como entidade. `payment_term` só como texto em fornecedor/cliente/proposta. Os forms «Registrar conta a pagar/receber» pedem UM vencimento | 0 tabelas |
| Contas fixas (recorrência que gera o título) | `financial_custos_recorrentes` = **só projeção** do CFO (fluxo de caixa); não gera título. `payable_accounts.is_recurring` + `process_recurring_accounts` gera o PRÓXIMO só de conta **já paga** (aba «Gerar recorrentes») | 3 custos (todos inativos, de teste); 15 pagáveis `is_recurring` (1 paga) |
| CFOP / natureza | `cfops` existe e está vazia. **As NFS-e daqui não usam CFOP**: usam cTribNac (LC 116). O emissor Manaus (`nfse_multi_empresa_service.py:387`) manda `ItemListaServico` **fixo 17.19** | cTribNac emitidos: 110201 ×50 · 140601 ×32 · 071002 ×16 · 140101 ×9 · 071001 ×7 |
| Recibos de venda | `build_recibo_pdf` (`crm/services/doc_pdf.py`) já é o recibo timbrado «Recebemos de…» via `POST /crm/growth/docs/recibo/pdf` — **sem número, sem registro** | 0 recibos guardados |
| Fechamento de comissões | `commissions` 15 pendentes (todas «auto — proposta»), `commission_rules` 1 (5% on_first_payment), `commission_payments` 0, `seller_commission_rules` 0. Tela `comissoes` no CRM só lista | 15 abertas, R$ 5.110,62 |
| Análise orçamentária | `orcado-realizado` (g-custos) = razão 5.x × `financial_orcamentos` chave `month_AAAA_MM` (1 linha, 9.999 em 11/2026). `fin_cost_centers` **vazia**; `payable_accounts.cost_center` **NULL em 369/369**; `payable_accounts.category_id` NULL nas pagas. O centro que a casa usa de fato é **`bank_transactions.category`** (100% das saídas classificadas desde 04/2026: Folha, Fornecedor, Impostos, Diaristas…) | 0 centros formais |
| Pensionistas | DP tem `employee_deductions.tipo='pensao_alimenticia'` (form «Novo desconto»); `financial_beneficiarios` (106) tem categoria funcionario/diarista/avulso/pessoa — **sem tipo pensionista nem vínculo com o colaborador** | 0 pensões ativas; 0 pensionistas |

## §2 — O que o DGX tem

Faturamento: CFOP (código + operação) · Recibos de Venda (cliente, CFOP, emitente, data, pagamento) · Fechamento de Comissões (período, origem avulsa/nota, status Aberto→Aprovado→Conta Gerada, `comissoesFechamento/recibo`). Financeiro: Condições de Pagamento · Contas Fixas (tipo pagar/receber, pessoa fornecedor/cliente/colaborador/prestador/**pensionista**, centro de custo, período semanal…anual, «Gerado Até», `gerar?quantidade=`) · Análise Orçamentária (View) · `RH/Pensionistas/combo`; tipos de pessoa nas contas: Fornecedor · Prestador · Pensionista · Advogado · Representante.

## §3 — O que foi feito

**Arquivos**
- `backend/modules/operacional/controllers/redesign_builders/_dgx_f11_financeiro.py` — DDL (`_ensure`), 17 telas, 12 ações, 2 GETs de PDF, regras puras (`vencimentos`, `parcelas`, `por_extenso`), serviços (`emitir_recibo`, `fechar_comissoes`, `orcado_realizado`, `pensoes_sem_beneficiario`).
- `backend/modules/financial/services/contas_fixas.py` — `gerar_titulos_do_mes(db, 'AAAA-MM', user_id)` idempotente, pelo `PayableService.create_account` (mesmo caminho da tela «Registrar conta»).
- `financeiro.py` (+3 linhas: include do router, `telas(db, out)` antes de `montar_grupos`) · `_fin_grupos.py` (17 abas, no fim de cada grupo).
- `backend/scripts/orq/test_oraculo_financeiro_cadastros.py`.

**DDL que `_ensure` aplica no 1º acesso (idempotente)**
`CREATE TABLE IF NOT EXISTS fin_condicoes_pagamento`, `fin_contas_fixas_geradas` (PK custo_id+competencia), `fin_codigos_servico`, `fin_recibos` (numero UNIQUE), `fin_comissoes_fechamentos` (UNIQUE competencia+seller); `ALTER TABLE financial_custos_recorrentes ADD COLUMN IF NOT EXISTS favorecido, encerrado_em`; `ALTER TABLE financial_beneficiarios ADD COLUMN IF NOT EXISTS tipo, employee_id` + índice. Seeds `ON CONFLICT DO NOTHING`: 4 condições (À vista, 30, 30/60, 30/60/90), 8 códigos de serviço (os 5 emitidos + 11.03/11.04/11.05 do mapa de vigilância; alíquota = a da última NFS-e emitida com o código, NULL se nunca emitiu), CFOP 5933/6933.

**Telas (id · grupo)**
1. `condicoes-pagamento` / `condicao-pagamento-nova` · g-cadastros — editar e inativar por linha. **`registrar-conta-pagar` e `registrar-conta-receber` ganharam o select «Condição de pagamento»** e passam a enviar para `payable-condicao` / `receivable-condicao`, que criam N parcelas (i/n) com vencimentos = data-base + dias e valores fechando ao centavo (entrada % na 1ª). Sem condição = comportamento anterior. Provado por HTTP: 30/60 de 31/01 → 02/03 R$ 500,01 · 01/04 R$ 500,00.
2. `contas-fixas` / `conta-fixa-nova` / `contas-fixas-gerar` · g-pagar-contas — lista com «Gerado até», encerrar por linha, form de incluir (categoria, valor, dia, parcelas, favorecido), botão «Gerar títulos do mês» com `confirm` + `showResult`.
3. `codigos-servico` / `codigo-servico-novo` / `cfop-natureza` / `cfop-novo` · g-fiscal — códigos com contagem de notas emitidas, editar por linha; cTribNac derivado por `ctribnac_de_lc116` (o mesmo do emissor nacional).
4. `recibos` / `recibo-novo` · g-receber — `POST /redesign/action/recibo-pdf` (`gated` — OTP humano pelo `redesign_write_gate.money_gov`, `confirm`) → grava `fin_recibos` com número sequencial (lock `pg_advisory_xact_lock`) e devolve `doc` → `GET /redesign/recibo/{numero}/pdf` (timbrado `build_recibo_pdf`, CNPJ Patrimonial, valor por extenso).
5. `comissoes-fechamento` / `comissoes-fechar` · g-custos — em aberto por vendedor × competência (sem `commission_payments`), painel de fechamentos; «Fechar período» (`gated`+`confirm`) cria `commission_payments` (`is_confirmed=false`, ref `FECH-AAAA-MM`), marca `approved`, registra o fechamento; demonstrativo `GET /redesign/comissoes-fechamento/{id}/pdf` (timbrado).
6. `orcamento-vs-realizado` / `orcamento-centro-novo` · g-custos — centro = categoria do extrato; orçado em `financial_orcamentos` chave `cc:<centro>:<AAAA-MM>` (sem tabela nova); desvio e %; filtro por mês.
7. `pensionistas` / `pensionista-novo` · g-pagar-pessoas — junta desconto de pensão (DP) + beneficiário `tipo='pensionista'` + chave PIX; linha «sem beneficiário — não paga» e painel de pendências.

## §4 — Oráculo

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_financeiro_cadastros.py
```
**Antes (vermelho):**
```
FALHOU: módulo _dgx_f11_financeiro não importa: cannot import name '_dgx_f11_financeiro' from 'modules.operacional.controllers.redesign_builders'
TOTAL financeiro_cadastros: 1 falha
exit=1
```
**Depois (verde):**
```
TOTAL financeiro_cadastros: 28 checagens · 0 falha(s)
OK financeiro_cadastros: telas com porta, condições contam certo, conta fixa não duplica, recibo sem buraco, fechamento único, realizado bate com o extrato, pensão sem beneficiário acusada
exit=0
```
Blocos: (a) 17 telas com aba · (b) 4 condições, 30/60 de 31/01 → 02/03 e 01/04, parcelas(100,3) fecha · (c) gerar 2× em 2099-01 → 1 título, 1 vínculo, vencimento 10/01/2099 · (d) recibos consecutivos, count == max−min+1, extenso de 1.234,56 · (e) fechar 2× → 2 pagamentos, 1 fechamento, status approved · (f) realizado Folha/mês da tela == SQL do extrato, desvio = orçado − realizado · (g) pensão sem beneficiário 1 → 0 ao cadastrar. Fixtures `'FIXTURE DGX F11'` apagadas ao fim (conferido: 0 linhas restantes).

Prova HTTP (container `teste-dgx-f11`, porta 8211, já parado): `GET /redesign/data/financeiro` 200 com as 17 telas nos grupos certos; ações `condicao-pagamento-salvar`, `orcamento-centro-salvar`, `codigo-servico-salvar`, `contas-fixas-gerar`, `payable-condicao` (2 parcelas) OK; `recibo-pdf` recusa valor 0; `cfop-salvar` recusa duplicado. PDFs do recibo (37 KB) e do demonstrativo (37 KB) gerados por chamada direta (`%PDF-`), sem disparar OTP.

## §5 — O que NÃO foi feito e por quê

- **Contas fixas «a receber»** do DGX: a recorrência de receita já existe («Recorrência (MRR)» / «Gerar do mês» em g-receber). Só pagar aqui.
- **Períodos semanal/quinzenal/bimestral…** da conta fixa: a tabela existente é mensal por dia; sem caso real na casa. Adicionar `periodo` quando aparecer.
- **CFOP no fluxo de NF-e** de compra: `cfops` só ganhou seed e cadastro; nenhum emissor lê dela. **Achado:** o emissor Manaus manda `ItemListaServico=17.19` fixo (`nfse_multi_empresa_service.py:387`) enquanto as 27 `nfses` estão com 11.02 — não mexi (caminho fiscal, fora do mandato).
- **Confirmar pagamento de comissão / gerar conta a pagar** do fechamento: «Conta Gerada» do DGX não foi feita — pagar comissão é caminho do dinheiro (OTP no CRM/ordens). O fechamento para em `approved` + pagamento a confirmar.
- **Editor genérico de `tipo` dos 106 beneficiários** (fornecedor/prestador/advogado/representante): a coluna existe; só o tipo `pensionista` tem tela. Os outros ficam para quando houver uso.
- **Pensionista não recebe automaticamente**: a tela acusa quem não tem chave; pagar segue pelos lotes existentes.
- Não tocado: `_frente_*.py`, `alembic/`, `frontend/`, `checar_regressao.py`, `ordem_pagamento_service`, adapter Inter, produção. JSON de menu: nenhum (tudo por aba em `_fin_grupos`).

## §6 — Como o Jordan testa amanhã

1. Financeiro › **Cadastros & Suprimentos › Condições de pagamento**: veja as 4; «Nova condição» → «Entrada + 30/60», dias `0,30,60`, entrada 40.
2. **Pagar › Registrar conta**: descrição, R$ 1.000,00, vencimento (= data-base), condição «30/60» → mensagem lista 02 parcelas com datas; confira em «Contas a Pagar».
3. **Contas & Impostos › Contas fixas**: «Nova conta fixa» (Contador, 2.500, dia 10) → «Gerar títulos do mês» (09/2026) → 1 criado; clique de novo → 0 criados, 1 já existia.
4. **Fiscal & Contábil › Códigos de serviço**: 8 linhas, coluna «Notas» com a contagem real; editar a alíquota de 11.02.
5. **Receber › Emitir recibo**: cliente, valor, referente → confirma → OTP no e-mail → PDF abre numerado 00001; «Recibos de venda» lista com o PDF.
6. **Custos & Orçamento › Lançar orçamento**: Folha, 09/2026, 300.000 → «Análise orçamentária» mostra orçado × realizado e o desvio.
7. **Custos & Orçamento › Fechamento de comissões**: 3 grupos abertos (admin 06/2026 e 09/2026, mcp-service 09/2026) → «Fechar período» → OTP → demonstrativo PDF; tentar de novo → «já fechado».
8. **Pessoas & Folha › Pensionistas**: vazio hoje. Crie em DP › Novo desconto tipo «Pensão alimentícia» para alguém → aparece «sem beneficiário — não paga» → «Cadastrar pensionista» → fica «pronto para pagar».

## §7 — Decisões que só o dono pode tomar

1. As 15 comissões «auto — proposta» de 06–09/2026 (R$ 5.110,62, 14 do admin) são reais ou lixo de teste? Fechar período em cima delas cria pagamentos a confirmar.
2. `ItemListaServico=17.19` fixo no emissor Manaus vs 11.02 nas notas gravadas — qual é o certo para a Patrimonial? (o cadastro novo já tem 11.02 = 110201, 50 notas nacionais).
3. Os 3 custos recorrentes de teste (`[TESTE] Parcelamento`, `[TESTE] Contador`, `E2E_TESTE_CUSTO`) podem ser apagados? Estão inativos e aparecem como «Encerrada» na tela.
4. Recibo de venda sai no CNPJ da **Patrimonial** (é quem fatura os serviços). Se a Eletrônica também emitir recibo, precisa de um seletor de emitente.
5. Orçamento por «centro» = categoria do extrato. Se quiser centro de custo formal (`fin_cost_centers`), é preciso começar a classificar as saídas por ele.
