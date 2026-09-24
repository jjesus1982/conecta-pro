# DGX T4 — Faturamento + Financeiro: passagem por dentro e as 5 lacunas fechadas

**Data:** 24/09/2026 · **Branch:** `dgx/t4-faturamento-financeiro` · **Módulo:** financeiro
**Sandbox:** cópia de produção de 23/09 (`conecta_pro_staging`) · **Container efêmero:** `teste-dgx-t4`, porta 8224 (parado)
**Deep-link:** `/redesign/financeiro?t=<id>`

## §1 — Estado antes (medido)

Cavado com grep, abas de `_fin_grupos` (156 telas do Financeiro) e o relatório da F11. O financeiro
da casa é o mais construído; o que faltava eram cinco pontas do DGX:

| Item | O que já existia | Medido |
|---|---|---|
| Cobrança por e-mail | Régua (`regua_cobranca_service`) entrega texto pronto; beat `propor_cobranca_vencidos` cria rascunho na Central; `core.mailer.send_email` existe. Parâmetros `financeiro.cobranca_dias_a_vencer_email`/`_vencidos_email` (F4) **semeados vazios, sem leitor** | 7 recebíveis vencidos (R$ 43.880); 26/29 clientes com e-mail |
| Importar OFX | `_parse_ofx` em `bank_transaction_controller.py` (90 linhas, **0 rotas**); Inter/Cora por API; card da conciliação dizia «backend pronto via API — UI próxima» (falso) | Asaas IP (Patrimonial): 0 transações; índice `idx_bank_tx_external_id` único parcial já existe |
| Fluxo de caixa por dia | `fluxo-caixa` = extrato passado; `projecao`/`cockpit` = agregado. Sem visão diária de vencimentos com saldo | front sem tipo calendário |
| Comissões → conta a pagar | F11 fecha o período (`commission_payments` + `approved`) e para | 0 pagáveis de comissão |
| Recebível proporcional | `gerar_recebiveis` cobra `monthly_value` **cheio** mesmo com `start_date` no meio do mês; parâmetro `fiscal.nfse_valor_proporcional_dias` (F4) sem leitor | 0/14 contratos ativos começam fora do dia 1 (nada muda hoje) |

## §2 — O que o DGX tem (Fase A, exercitado)

Trial financeiro **vazio** (0 contas/plano/centros/bancos). Criei `TESTE CP` e o servidor impôs:
datas ISO, enums como inteiro (`tipoPessoa` 0=…, `segmento` 1=…), conta a receber **recusa valor acima
do limite da condição**, conta fixa exige favorecido+conta, fechamento de comissões **único por período**.
Layouts de exportação: cobrança CNAB (remessa/retorno, nosso número), pagamento CNAB, **OFX** na
conciliação (`POST /api/financeiro/conciliacoes/extrato` → `fitID`, `chaveComposta = banco|conta|fitid|data|valor|tipo`),
relatórios PDF/Excel/Word (`ListagemReport?Tipo=`). Telas React: Análise Orçamentária, Conciliação (Grid/OFX/API),
Fluxo de Caixa em **calendário** (mês/semana/dia), Dashboard Financeiro, Cobrança, Contas Fixas.
Parâmetros: `NotaServicoContratoValorProporcional=false`+`Dias=30`, `CRDias*EmailAuto=0`, `PERMITIR_RETROCEDER_NOTA_STATUS_ENVIADO=false`,
`FaturamentoSistema=MANUAL`. Detalhe completo em `docs/dgx/lacunas/faturamento_financeiro.md`.

## §3 — O que foi feito (Fase D)

**Arquivos**
- `backend/modules/operacional/controllers/redesign_builders/_dgx_t4_faturamento_financeiro.py` — 4 telas, 3 ações, regras puras (`candidatos_cobranca`, `montar_email`, `importar_ofx`, `agenda_fluxo`, `gerar_conta_comissoes`).
- `backend/modules/financial/services/receivable_contract_service.py` — `valor_proporcional()` + `_base_proporcional()`; `gerar_recebiveis` passa o valor pela regra (paralelo cego).
- `_fin_grupos.py` — 4 abas; `financeiro.py` — `telas(db, out)` + `include_router` (2+1 linhas).
- `backend/scripts/orq/test_oraculo_t4_faturamento_financeiro.py`.

**DDL que `_ensure` aplica no 1º acesso (idempotente):** `ALTER TABLE fin_comissoes_fechamentos ADD COLUMN IF NOT EXISTS payable_id uuid`.

**Telas (id · grupo · deep-link)**
1. `cobranca-email` · g-receber · `/redesign/financeiro?t=cobranca-email` — lista quem está na janela dos parâmetros F4; botão por linha «Enviar e-mail» (gate = clique + confirm; anti-spam 1/dia; registra a tentativa no recebível). Parâmetros vazios = tela não lista ninguém.
2. `importar-ofx` · g-bancos · `?t=importar-ofx` — form multipart (arquivo OFX + conta opcional); `external_id=ofx:banco:conta:fitid`; reconhece a conta por BANKID/ACCTID; roda `conciliar_todas` depois.
3. `fluxo-caixa-agenda` · g-visao · `?t=fluxo-caixa-agenda` — tabela por dia (mês atual + próximo), saldo projetado = bancos + Σ recebíveis − Σ pagáveis em aberto até a data; 1ª linha = atrasados em aberto.
4. `comissoes-conta-gerada` · g-custos · `?t=comissoes-conta-gerada` — fechamentos da F11 com botão «Gerar conta a pagar» (registrar ≠ pagar), idempotente por `payable_id`.

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_t4_faturamento_financeiro.py` — afirma a REGRA (SQL próprio), fixtures `FIXTURE DGX T4`/competência 2099-01, apagadas ao fim, parâmetros restaurados.

**Antes (vermelho):**
```
FALHOU: módulo _dgx_t4_faturamento_financeiro não importa: cannot import name '_dgx_t4_faturamento_financeiro' ...
TOTAL t4_faturamento_financeiro: 1 falha
exit=1
```
**Depois (verde, rodado 2×, restaura os parâmetros a vazio):**
```
TOTAL t4_faturamento_financeiro: 19 checagens · 0 falha(s)
OK t4: telas com porta, janela de cobrança pelos parâmetros, OFX sem duplicar, agenda fecha com as contas, proporcional cego, comissão vira uma conta só
exit=0
```
Blocos: (a) 4 telas com aba · (b) janela 5/3: só o de 3d-a-vencer e o de 5d-vencido entram; 10d e 1d ficam de fora; e-mail traz R$ 702,00 e a data · (c) OFX 2× → 2 e 0, crédito +/débito −, conta 403/7382527 · (d) saldo projetado do dia == recontado por SQL · (e) 15/30 no dia 16, cheio com base vazia, cheio com mês inteiro, 10/30 no encerramento; paralelo cego: `gerar_recebiveis` soma == Σ monthly_value SQL · (f) gerar conta 2× → 1 pagável, 2ª recusa.

**Prova HTTP (efêmero 8224, parado):** `GET /redesign/data/financeiro` 200 com as 4 telas nos grupos certos; `importar-ofx` 2 novas → 0 já existiam (conta Cora reconhecida pelo cabeçalho); `comissoes-gerar-conta` 1 pagável de R$ 321,99 → 2ª chamada HTTP 400 «já gerou». Fixtures `TESTE CP` apagadas do sandbox (0 restantes).

## §5 — O que NÃO foi feito e por quê

- **Cobrança automática por e-mail (beat)**: fica no clique. Disparo sem humano a cliente real é decisão do dono (§7). A régua/beat da casa já entrega texto pronto; esta tela só acrescenta o envio real, com gate.
- **Fluxo de caixa em calendário visual** (grade de mês do DGX): o front do redesign não tem tipo calendário; entreguei a mesma informação como tabela por dia. JSON de menu/tipo novo = decisão do front, não do agente.
- **Fatura avulsa impressa, NBS/CST/IBS (reforma tributária), centros hierárquicos, limite por condição, formas de pagamento como cadastro, juros/multa na baixa, relatórios com agrupamento/Excel, períodos semanal/…/anual da conta fixa, CNAB (remessa/retorno)**: baixo valor hoje ou o caminho da casa é outro (NFS-e+boleto por API em vez de fatura+CNAB). Detalhe na tabela de `docs/dgx/lacunas/faturamento_financeiro.md`.
- **Emissão de NFS-e, `ordem_pagamento_service`, adapter Inter, «retroceder status de nota»**: fora do mandato (não tocar). «Retroceder» não se aplica: o status da NFS-e vem da prefeitura.
- **Não tocado:** `_frente_*.py`, `alembic/`, `docker-compose*`, `.env*`, `frontend/`, `main_production.py`, `checar_regressao.py`, produção. JSON de menu: nenhum (tudo por aba em `_fin_grupos`).

## §6 — Como o Jordan testa amanhã

1. **Financeiro › Configurações › Parâmetros** (F4): defina «Cobrança: dias antes do vencimento» = 7 e «dias após vencido» = 1.
2. **Receber › Cobrança por e-mail**: a lista enche com quem está na janela (hoje ~7 vencidos). Cada linha com e-mail tem «Enviar e-mail» — confirma → o cliente recebe o lembrete e a tentativa fica registrada no recebível. Sem parâmetro, a tela não lista ninguém.
3. **Bancos › Importar OFX**: baixe um OFX do Asaas/Cora e suba (deixe a conta em «reconhecer pelo arquivo»). Suba o mesmo de novo → 0 novas.
4. **Visão Geral › Agenda de caixa (por dia)**: veja o saldo projetado descer/subir a cada vencimento; troque o mês no seletor.
5. **Custos › Fechamento de comissões** (F11) → feche um período → **Custos › Comissões → conta a pagar** → «Gerar conta» → aparece em Contas a Pagar; «Gerar» de novo é recusado.

## §7 — Decisões que só o dono pode tomar

1. **Cobrança automática por e-mail**: ligar o envio SEM clique (beat diário lendo os mesmos parâmetros)? Hoje é por clique de propósito — comunicação a cliente real é gate humano.
2. **INCIDENTE a saber**: ao testar a ação de e-mail por HTTP no container efêmero, ele herdou o SMTP **real** do `.env` e **enviou de fato** um lembrete de cobrança (fatura R$ 23.160,00 vencida 09/09) ao cliente real `presidencia@chacaramaiapolis.com.br`. Um e-mail só, do sandbox. A ação está correta (gate de clique); o erro foi meu, testar envio contra SMTP de produção. Recomendo: SMTP de sandbox (mailtrap/console) no `.env` do staging, ou uma trava «só e-mails @conectamais.pro no não-produção».
3. **Recebível proporcional**: quer ligar (`fiscal.nfse_valor_proporcional_dias` = 30)? Hoje vazio = valor cheio (0 contratos afetados agora). Ligar muda o valor de todo contrato que começar/encerrar no meio do mês.
4. **Fluxo de caixa em calendário** de verdade (grade visual como o DGX) vale um tipo de tela novo no front? Por ora é tabela por dia.
5. Os 3 fechamentos/parâmetros do trial DGX com `TESTE CP` que não têm endpoint de exclusão (CFOP, serviço, fatura, recibo) ficaram no trial — sem impacto, prefixo claro.
