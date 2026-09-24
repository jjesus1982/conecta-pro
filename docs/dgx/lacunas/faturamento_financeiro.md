# Lacunas DGX → Conecta PRO — Faturamento + Financeiro (T4, 24/09/2026)

Fonte: passagem por dentro do DGX (trial `conectamais.dgxbrasil.com.br`, empresa PATRIMONIAL) com o
`scripts/dgx/dgx_client.py` — botões, formulários, APIs capturadas por Playwright e POSTs de teste com
prefixo `TESTE CP`. Comparado com a casa por `grep` em `backend/modules`, as abas de `_fin_grupos.py`
(156 telas do Financeiro) e os relatórios `DGX_F11_financeiro.md` / `RELATORIO_NOITE_2026-09-24.md`.

## O que o trial do DGX deixou ver (Fase A, resumido)

O financeiro do trial está **vazio** (0 contas, 0 plano de contas, 0 centros, 0 bancos). Criei
`TESTE CP`: forma de pagamento, condição, centro de custo, plano de contas, tipo de serviço, CFOP,
recibo, fatura, fechamento de comissões. Quebrado no trial (HTTP 500): `Faturas/GerarConta`,
`Faturas/Imprimir`, `NotasServico/Salvar` (wizard), `PessoaRecibos/Imprimir`, `POST contasBancarias`,
`/TransferenciasBancarias`. Regras que o servidor impôs: datas em ISO, enums como inteiro
(`tipoPessoa` 0=Fornecedor/Cliente…, `segmento` 1=Portaria…), conta a receber recusa **valor acima
do limite da condição de pagamento**, conta fixa exige **favorecido e conta bancária**, fechamento de
comissões é **único por período** (`Já existe um fechamento nesse período`).

Layouts de exportação registrados: cobrança por **remessa/retorno CNAB** (`Cobranca/GerarArquivo`,
`ArquivosRemessa`, `arquivosRetornoCobranca/ImportarArquivo` → `ProcessarRetornoJson`), pagamentos por
**remessa/retorno** (`ContasPagar/ImportarArquivo`, `arquivosRetornoPagamento`), **OFX** na conciliação
(`POST /api/financeiro/conciliacoes/extrato` multipart → transações com `fitID`, `fitIDUUIDV5`,
`chaveComposta = banco|conta|fitid|data|valor|tipo`, `fitIDSugerido`), relatórios em **PDF/Excel/Word**
(`ListagemReport?Tipo=`), exportação de contas (`ContasReceber/ArquivoExportacao` — 500 no trial),
importação de folha para o contas a pagar (`contasPagar/rubricas/arquivo`, `pensionistas/arquivo`).

## Tabela

| Recurso DGX | tela/fluxo | o que faz | Conecta PRO | classificação | vale para a Conecta Mais? | esforço |
|---|---|---|---|---|---|---|
| **Cobrança automática por e-mail** a vencer/vencidos | Configurações `CRDiasAVencerEmailAuto`, `CRDiasVencidosEmailAuto`, `CRMsg*`; `contasReceber/enviarEmail`; `boletosemailjob` | N dias antes/depois do vencimento manda e-mail com boleto ao cliente | Régua (`regua_cobranca_service`) entrega **texto pronto para o humano**; beat `propor_cobranca_vencidos` cria rascunho na Central; `send_email` existe (`core/mailer.py`); parâmetros `financeiro.cobranca_dias_a_vencer_email`/`_vencidos_email` semeados pela F4 e **nada lê**; 26/29 clientes com e-mail | NÃO TEMOS | **alto** — 7 recebíveis vencidos (R$ 43.880) hoje; o lembrete a vencer é o que evita o atraso | M |
| **Conciliação por OFX** | `/view/conciliacaoBancaria` → botão OFX (arquivo + conta + período) | Lê o OFX, casa por `fitID`/chave composta, sugere, confirma/sobrescreve/remove | Inter e Cora por API (`inter_reconciliacao_diaria`), `conciliar_todas` casa extrato × contas; **`_parse_ofx` existe em `bank_transaction_controller.py` sem rota nem tela** — o card «Upload manual OFX: backend pronto (via API)» não é verdade (controller de 90 linhas, 0 rotas); Asaas IP (Patrimonial) tem **0 transações** | TEMOS PARCIAL | **alto** — Asaas e qualquer banco sem API só entram por OFX; e a tela promete o que não existe | M |
| **Fluxo de caixa em calendário** | `/View/FluxoCaixa/Calendario` (mês/semana/dia; `contasBancarias/filtro` com `CalcularSaldos`, `Atrasadas`) | Vencimentos a pagar/receber por dia com saldo | `fluxo-caixa` = extrato passado (`bank_transactions`); `projecao`/`cockpit` = agregado; não há visão por **dia** dos vencimentos futuros com saldo projetado; front sem tipo calendário | TEMOS PARCIAL | **médio** — 2 recebíveis e 8 pagáveis nos próximos 60 dias; a pergunta «cabe no caixa no dia 7?» não tem tela | P (tabela por dia) |
| **Fatura/nota proporcional por dias** | `/Parametros/NotasServico`: Contrato Proporcional (Sim/Não), Dias (30) | Contrato iniciado/encerrado no meio do mês fatura pró-rata | `gerar_recebiveis` (contrato/competência) cobra **`monthly_value` cheio** mesmo com `start_date` no meio do mês; parâmetro `fiscal.nfse_valor_proporcional_dias` semeado pela F4 e **nada lê**; hoje 0/14 contratos ativos começam fora do dia 1 (não muda nada agora; muda no próximo contrato) | NÃO TEMOS | **médio** — paralelo cego: parâmetro vazio = comportamento idêntico | P |
| **Fechamento de comissões → «Conta Gerada»** | `/frontend/ComissoesFechamento` Incluir → Aprovar → Conta Gerada (pagável com rateio) | O fechamento aprovado vira conta a pagar | F11: fechar cria `commission_payments` não confirmado + `approved`; **não gera o pagável** (F11 §5 deixou de fora) | TEMOS PARCIAL | **médio** — registrar a obrigação ≠ pagar (mesmo princípio de `registrar_obrigacoes`); sem o pagável a comissão não entra no fluxo de caixa nem na fila de aprovação | P |
| Fatura manual (período, vencimento, itens, descrição padrão, GerarConta, copiar em lote, imprimir lote) | `/Faturas` | Documento «fatura» com itens → conta a receber | `registrar-conta-receber`, `gerar-recebiveis`, `billing-contrato-ativado`; aqui o documento ao cliente é a **NFS-e** (DANFSe) + boleto; «fatura» avulsa impressa não existe | TEMOS PARCIAL | baixo — condomínio recebe NFS-e + boleto; fatura à parte é papel a mais | M |
| Nota de serviço (tipos, RPS em lote, substituição com motivo, envio automático, retroceder status `PERMITIR_RETROCEDER_NOTA_STATUS_ENVIADO`) | `/NotasServico`, `/NotasServicoEletronica` | Emissão por RPS à prefeitura | Emissor NFS-e nacional + Manaus (114 notas), cancelamento/substituição no emissor; «retroceder status» não se aplica: o status vem da prefeitura, e `nfses.status` (27 autorizada) não tem escritor | TEMOS / NÃO SE APLICA (retroceder) | — (fora do mandato: não tocar emissão) | — |
| Cobrança por boleto CNAB (remessa/retorno, nosso número, imprimir boleto) | `/frontend/Cobranca` Processar/Concluir | Gera remessa, importa retorno, baixa | Boleto/PIX **por API** (Inter/Cora) com baixa automática (`auto_baixa_pagaveis`, `conciliar_todas`) | TEMOS (melhor) | — CNAB é o caminho antigo | — |
| Recibo de venda (modelo 01/02/03, lote, calcular vencimento, listagem PDF/Excel/Word) | `/PessoaRecibos` | Recibo numerado por cliente | F11 `recibos`/`recibo-novo` (numerado, timbrado, extenso) | TEMOS | baixo (modelos/lote) | — |
| Tipos de serviço com NBS, CST, CST PIS/COFINS, classificação tributária, **incidência IBS** | `/Servicos` | Cadastro fiscal do serviço já com campos da reforma tributária | F11 `codigos-servico` (LC 116 + cTribNac); sem NBS/CST/IBS | TEMOS PARCIAL | baixo até 2027 (IBS/CBS) — quando a prefeitura exigir | P |
| CFOP / natureza | `/CFOP` | código + operação | F11 `cfop-natureza` | TEMOS | — | — |
| Dashboard evolução de faturamento (acumulado, top 10 clientes) | `/DashboardEvolucaoFaturamento` | gráfico por empresa | `faturamento`, `rentabilidade`, `resultado-cnpj`, `tendencias` | TEMOS | — | — |
| Centros de custo hierárquicos (pai/filho, descendentes) | `/CentrosCusto` | árvore + relatório por período | Centro = categoria do extrato (F11 §7.5); `fin_cost_centers` vazia; `payable_accounts.cost_center` NULL | TEMOS PARCIAL | baixo até o dono decidir classificar por centro formal | M |
| Condições de pagamento com **limite de valor** | `/CondicoesPagamento` | recusa conta acima do limite da condição | F11 `condicoes-pagamento` sem limite | TEMOS PARCIAL | baixo | P |
| Formas de pagamento (`boleto` bool, forma de lançamento) | `/FormasPagamento` | cadastro | `payment_method_id` em pagáveis; sem tela própria | TEMOS PARCIAL | baixo | P |
| Análise orçamentária (orçado × realizado por centro, período, atrasadas) | `/View/AnaliseOrcamentaria` (usa `fluxoCaixa/filtro`) | comparação por centro | F11 `orcamento-vs-realizado` + `orcado-realizado` | TEMOS | — | — |
| Contas a pagar: rateio por centro, compensação, parcelar, aprovar, importar rubricas/pensionistas da folha, opção de tributo (parcela única c/ desconto) | `/frontend/contaspagar/editar` | lançamento completo | `registrar-conta-pagar` + condição (F11), `fila-aprovacao`, `registrar_obrigacoes` (folha/guias/NFS-e → pagável), pensionistas (F11); rateio por centro não | TEMOS (rateio: parcial) | baixo | — |
| Contas a receber: tipos de pessoa, duplicata/nosso número, parcelar, rateio, histórico, baixa com juros/multa, cancelamento com motivo, exportação | `/frontend/contasReceber/editar` | lançamento completo | `registrar-conta-receber` + condição, `baixar-recebivel`, `nfse-a-receber`; juros/multa: colunas existem (`interest_rate`, `penalty_rate`), baixa não calcula | TEMOS (juros na baixa: parcial) | baixo | P |
| Contas bancárias + extrato + fluxo por conta | `/ContasBancarias` | cadastro, extrato | `contas-bancarias`, `banking`, `saldos` | TEMOS | — | — |
| Contas fixas (pagar/receber, favorecido, período semanal…anual, gerar N, cancelar, listagem) | `/Frontend/ContasFixas` | recorrência gera título | F11 `contas-fixas` (mensal, só pagar) | TEMOS | baixo (períodos) | — |
| Plano de contas hierárquico + relatório listagem/detalhado com valor | `/PlanoContas` | árvore, valor por conta | `plano-contas`, `balancete`, `lancamentos` | TEMOS | — | — |
| Transferências bancárias | `/TransferenciasBancarias` (500 no trial) | entre contas próprias | `transferir-ted`, `enviar-pix` (Inter, OTP) | TEMOS | — | — |
| Dashboard financeiro (despesas/receitas por centro, a pagar/receber/atraso) | `/frontend/DashboardFinanceiro` | painel | `dashboard`, `cockpit`, `dre-inline`, `fluxo-categorias` | TEMOS | — | — |
| Relatórios: contas a pagar (6 agrupamentos), a receber (3), fluxo de caixa (4 modelos, PDF/Excel/Word), centro de custo, plano de contas, contas fixas | menu Relatórios Financeiros | PDF/Excel/Word por filtro | `relatorios` (DRE, balancete, fluxo de caixa em PDF), `relatorio-pago-pdf`; sem agrupamentos nem Excel | TEMOS PARCIAL | baixo — as telas do redesign já filtram; Excel quando alguém pedir | M |
| Remessa/retorno de **pagamentos** (CNAB) | `/ContasPagar` Remessa/Retorno | lote ao banco por arquivo | Ordens de pagamento via API Inter + OTP | NÃO SE APLICA | — | — |

## Ordem da Fase D (alto/médio × P/M)

1. Cobrança por e-mail (a vencer/vencidos pelos parâmetros F4) — M
2. Importar OFX na conciliação — M
3. Fluxo de caixa por dia (agenda de vencimentos com saldo projetado) — P
4. Recebível proporcional por dias (parâmetro `fiscal.nfse_valor_proporcional_dias`) — P
5. Comissões: fechamento aprovado → conta a pagar («Conta gerada») — P

Fora (§5 do relatório): fatura avulsa impressa, NBS/CST/IBS, centros hierárquicos, limite por condição,
formas de pagamento, juros na baixa, relatórios com agrupamento/Excel, períodos de conta fixa, CNAB.
