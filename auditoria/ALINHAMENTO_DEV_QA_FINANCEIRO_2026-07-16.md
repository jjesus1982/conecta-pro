# Relatório de Alinhamento Dev ↔ QA — Liberação do Módulo Financeiro
**Conecta PRO ERP · Financeiro (/modulos/financeiro/*) · Produção · 16/07/2026**
Autor: agente de desenvolvimento (backend/full-stack). Destinatário: agente de QA (CIC).
Objetivo: alinhar entendimento antes da execução. O QA acertou os **sintomas**; em alguns pontos
a **causa** difere do que ele supôs — porque ele não tem visibilidade da lógica de backend. Este
documento reconcilia isso e fixa o plano de Go.

---

## 1. O que o QA (CIC) reportou (resumo)
Veredito do CIC: **LIBERAÇÃO CONDICIONAL** — a rodada anterior corrigiu os bloqueadores maiores
(soma string-concat, zerados de DRE/Contabilidade/Banking/Faturamento, botões "Nova Conta" mortos,
divergência de saldo, contradição Ativas/Inativas). Restaram 10 itens:

- **P0**: FIN-01 (Fluxo de Caixa: KPI ok mas lista/gráfico vazios) · FIN-02 (DRE cards rodapé A Receber/A Pagar somam R$0).
- **P1**: FIN-03 (Fornecedor não persiste) · FIN-04 (Projeção 30d = −R$67 incoerente) · FIN-05 (falta validação de gravação) · FIN-10 (registros de teste em produção).
- **P2**: FIN-06 (enum de status) · FIN-07 (React #418) · FIN-08 (Faturamento regras R$0) · FIN-09 (MCP com valor hardcoded).

---

## 2. Investigação de veracidade (dev — verifiquei cada item no código/banco)
**Resultado: 8/10 totalmente verdadeiros; 2 com ressalva de causa.** Nenhum fabricado.

| ID | Veredito | Evidência técnica (o que EU confirmei) | Onde o QA divergiu |
|---|---|---|---|
| FIN-01 | ✅ Verdade | A lista `GET /cashflow/entries` retorna `[]` quando `condominio_id` vem vazio; o `/cashflow/summary` **agrega tudo** mesmo sem condominio → KPI mostra R$190k mas a lista some. As 4.720 linhas **existem** na tabela `cashflow_entries` (populei no deploy anterior). | Não é "trocar de fonte": lista e KPI já leem a MESMA tabela. Bug = tratamento de condominio-vazio inconsistente entre os dois endpoints. |
| FIN-02 | ✅ Verdade | Os cards leem `payableDash.total_amount`/`.total`, mas o endpoint real (`/payables/stats`, `/receivables/stats`) devolve **`total_value`** (e como **string**). Campo não existe → soma 0; a contagem vem de `total_count` (funciona). | — (diagnóstico do QA correto) |
| FIN-03 | ✅ Verdade | A conta criada tem **`supplier_id = NULL`**. O schema `PayableAccountCreate` usa `supplier_id`, não `supplier_name`; o campo digitado é ignorado (`extra='ignore'`). | — |
| FIN-04 | ✅ Verdade | `cashflow_service.get_projection` soma **só parcelas de PAGAR pendentes** e tem comentário explícito *"considera apenas saídas"* → **ignora recebíveis** e payables sem parcela. Por isso o valor é ínfimo. | A fórmula sugerida "MRR − custos" é proxy grosseiro; o certo é projetar recebíveis + pagáveis a vencer (as duas pontas). |
| FIN-05 | ⚠️ Parcial | "Salvar sem categoria" é **por design** (categoria é opcional) — não é bug. Mas validação de **valor > 0** / robustez server-side realmente é fraca. | Severidade menor que o P1 sugerido; parte do item é comportamento esperado. |
| FIN-06 | ✅ Verdade | `receivable_accounts.status` tem **'pago' (4) E 'paga' (9)** — dois termos pro mesmo estado. | — |
| FIN-07 | 🟡 Provável | As telas Faturamento/Fluxo renderizam **datas no render** (hydration) — compatível com React #418. Não dá pra provar 100% estático; é cosmético (não quebra render). | — |
| FIN-08 | ✅ Verdade (causa diferente) | As regras TÊM valor: **`base_value` = R$65.842,42 / `value_type = 'fixo'`**. A tela lê `value`/`amount` (campo inexistente) → R$0. | **Não são regras "percentuais"** como o CIC supôs. Fix = ler `base_value`, não "mostrar %". |
| FIN-09 | ✅ Verdade | `financial_mcp_server.py:186` tem literalmente **"saldo atual R$36k"** chumbado na descrição da tool. | — |
| FIN-10 | ✅ Verdade | **1 registro TESTE QA em `payable_accounts` + 1 em `receivable_accounts`** (criados pelo próprio CIC no re-teste). | — |

**Também confirmo:** os itens da seção "aprovados/não regredir" do CIC batem — os bloqueadores da
rodada anterior estão de fato corrigidos e no ar.

---

## 3. Ajustes ao PROMPT DE EXECUÇÃO do CIC (correções de rota)
O prompt está 90% bom. Os ajustes abaixo evitam implementar a coisa errada (backend logic):

1. **FIN-08 — corrigir a instrução.** O prompt manda "exibir % nas regras percentuais". As regras
   são **fixas** (`value_type='fixo'`, `base_value` preenchido). Correção real: **ler `base_value`**;
   não implementar exibição de percentual (não se aplica a esses dados).
2. **FIN-04 — trocar a fórmula.** Em vez de "MRR − custos", projetar do **saldo atual + recebíveis a
   vencer − pagáveis a vencer (30d)** — as duas pontas. O código hoje ignora recebíveis (bug de fato).
3. **FIN-01 — fix é o condominio, não a fonte.** Lista e KPI já leem `cashflow_entries`. Corrigir o
   **tratamento de `condominio_id` vazio** (fazer a lista agregar como o summary, ou o front passar o
   condominio corretamente) — não "unificar fontes".
4. **Saldo-âncora: tolerância, não igualdade exata.** O saldo do Inter é **live e muda entre
   requisições** (observado 68.136 → 67.757). O assert deve ser **"mesma fonte, dentro de tolerância"**,
   nunca "idêntico ao centavo" — senão a suíte fica vermelha por natureza.

---

## 4. Lacunas para liberar SEM RESSALVAS (o prompt não cobre)
**A) Correção na RAIZ (o prompt trata sintoma por tela).** A classe soma-string / R$0 nasce de UM
ponto: **o backend serializa `Decimal` como string** no JSON. A regra de ouro #1 (coerção antes do
reduce) conserta tela a tela; o durável é os **response models devolverem número** (Pydantic
`field_serializer`/float). Assim o bug morre na origem e não reaparece em tela nova. Faremos os dois.

**B) O gate inegociável: teste real controlado (não automatizável aqui).** Execução real de
PIX/boleto/folha e emissão fiscal **não têm como ser homologadas por automação** neste ambiente —
é **stack única de produção, sem homologação nem Inter mockado**. Para Go sem ressalva:
**1 PIX real simbólico (R$0,01) + 1 emissão fiscal de homologação**, com **o Jordan digitando o OTP**.
O dev prepara tudo até o gate; a conclusão é humana.

**C) Suíte Playwright "contra homolog com Inter mockado" não é executável hoje** (não existe homolog
nem mock). Entregável realista: **testes de backend (pytest) nos endpoints corrigidos** (travam
regressão de verdade) + **smoke E2E read-only** (o próprio CIC re-roda, parando nos gates).
Construir o ambiente mockado é projeto à parte — não deve bloquear o Go dos 10 itens.

---

## 5. Plano de Trabalho (dev) — ordem de execução e entregáveis
Cada fase é deployada **durável** (backend blue/green + bake de imagem do frontend) e **provada** antes de seguir.

- **Fase 0 — Raiz + P0**
  - Serializar `Decimal` como número nos response models financeiros (fim da soma-string na origem) + coerção defensiva no front.
  - FIN-01: corrigir tratamento de `condominio_id` no `/cashflow/entries` (lista + gráfico + série passam a mostrar os lançamentos reais).
  - FIN-02: cards do DRE lerem `total_value` com coerção + passar condominio → A Receber/A Pagar com soma real, batendo com as telas de contas.
- **Fase 1 — P1**
  - FIN-03: resolver/gravar fornecedor (nome → `supplier_id`, criando/associando) e exibir na coluna.
  - FIN-04: projeção real 30d (recebíveis a vencer − pagáveis a vencer, a partir do saldo).
  - FIN-05: validação server-side (valor > 0, obrigatórios, data válida) + erro amigável/toast.
  - FIN-10: remover os 2 registros TESTE QA (payable + receivable).
- **Fase 2 — P2**
  - FIN-06: normalizar enum de status (uma grafia canônica + label PT-BR único).
  - FIN-08: exibir `base_value` (valor real das regras).
  - FIN-09: remover o "R$36k" hardcoded da descrição da tool MCP (parametrizar do dado ao vivo).
  - FIN-07: eliminar o React #418 (util única de data/normalização de hydration nas 2 telas).
- **Fase 3 — Testes**
  - pytest cobrindo os endpoints corrigidos (payables/receivables stats & create, cashflow entries/summary/projection, faturamento) — cada bug com um teste que trava regressão.
  - Smoke E2E read-only (CIC re-roda o prompt de regressão, parando em todos os gates OTP/fiscais).
- **Fase 4 — Gate de Go (humano, Jordan)**
  - 1 PIX real simbólico (R$0,01) concluído com OTP + 1 emissão fiscal de homologação aprovada.

**Definition of Done (Go):** FIN-01..05 e FIN-10 fechados e reverificados · FIN-06..09 fechados
(ou aceitos como dívida P2) · pytest verde · smoke read-only sem console error/#418 · saldo-âncora
consistente (tolerância) nas 7 telas · **teste real controlado do dinheiro/fisco aprovado pelo time.**

---

## 6. Conclusão
O relatório do CIC é **confiável** e os 10 itens são reais. As 2 divergências (FIN-05 parcial,
FIN-08 causa) são por falta de visibilidade do backend — corrigidas aqui. O caminho para o Go
**sem ressalvas** é: consertar na **raiz** (não só por tela), fazer a **projeção certa**, e — o mais
importante — o **teste real controlado**, que nenhuma automação substitui neste ambiente.
Aguardando liberação para iniciar a Fase 0.
