# DGX — telas SPA (`/frontend`, `/view`) e o mapa real da API REST

Lido em 24/09/2026. As telas SPA carregam bundles JS próprios; **toda rota `/api/...` citada nos bundles** está listada abaixo — é o mapa real da API, não palpite. Campos das telas vêm do HTML inline (modais incluídos).


---

## `/frontend/DashboardAusencias/Index` — Dashboard Ausências  (HTTP 200)

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| idColaboradores | `idColaboradores` | select |  |  |
| idEventos | `idEventos` | select |  |  |
| idContratos | `idContratos` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/CalcularBancoHoras/Index` — Calcular Banco de Horas - Digiexpress  (HTTP 200)

Colunas do grid: RE · Nome · Saldo Banco de Horas

Botões: Limpar · Calcular

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idsCliente | `idsCliente` | select |  |  |
| idsContratos | `idsContratos` | select |  |  |
| idsFuncionario | `idsFuncionario` | select |  |  |
| idFuncao | `idFuncao` | select |  |  |
| Referencia | `Referencia` | text |  |  |
| modeloRelatorio | `modeloRelatorio` | select | Último Calculo · Cálculo Dia |  |
| Linhas por página: | `LinhasPorPagina` | text |  |  |
| calcularSaldoDiaAnterior | `calcularSaldoDiaAnterior` | checkbox |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/configuracoesponto` — Configurações de Ponto - Digiexpress  (HTTP 200)

Colunas do grid: Aplicação · Eventos · Diárias

Botões: Limpar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idPessoa | `idPessoa` | select |  |  |
| idContrato | `idContrato` | select |  |  |
| idVaga | `idVaga` | select |  |  |
| idColaborador | `idColaborador` | select |  |  |
| idFuncao | `idFuncao` | select |  |  |
| idModeloEscala | `idModeloEscala` | select |  |  |
| idEscala | `idEscala` | select |  |  |
| Aplicado | `aplicado` | checkbox |  |  |
| Linhas por página: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/view/feriados` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/integracaoBatimentos` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/View/controlePonto` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/regioes` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/acessosTemporarios` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/usuarioDepartamentos` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/DashboardAtivos/Index` — Dashboard Ativos  (HTTP 200)

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| idsCliente | `idsCliente` | select |  |  |
| idsFuncionario | `idsFuncionario` | select |  |  |
| idsContratos | `idsContratos` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/view/falhasImportacaoEmpregados` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/empregadofotos` — Fotos dos colaboradores - Digiexpress  (HTTP 200)

Colunas do grid: RE · Colaborador · Fotos

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| nome | `nome` | text |  |  |
| re | `re` | text |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/view/demissaolote/` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/EventosColetivos/Index` — Eventos Coletivos - Digiexpress  (HTTP 200)

Colunas do grid: Tipo · Evento Predecessor · Evento Sucessor · Apontamento · Início · Término · Referência · Quantidade Contratos · Quantidade Colaboradores

Botões: Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| Eventos: | `idEventos` | select |  |  |
| Contratos: | `idContratos` | select |  |  |
| Apontamento: | `idApontamentos` | select |  |  |
| Colaboradores: | `idColaboradores` | select |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| tipo | `tipo` | select | -- Selecione -- · Inclusão · Remoção · Substituição |  |
| Apontamento | `Apontamento` | select |  |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| idEventoPredecessor | `idEventoPredecessor` | select |  |  |
| idEventoSucessor | `idEventoSucessor` | select |  |  |
| hReferencia | `hReferencia` | text |  |  |
| idContratos | `idContratos` | select |  |  |
| idEscalas | `idEscalas` | select |  |  |
| idColaboradores | `idColaboradores` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/View/Sindicatos` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/vales` — Vales - Digiexpress  (HTTP 200)

Colunas do grid: Colaborador/Prestador · Evento · Data Ocorrência · Vencimento Colaborador · Vencimento Prestador · Valor · Valor Pago · Parcelas · Tipo · Motivo

Botões: Adicionar · Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| Tipo: | `trabalhista` | select | --Selecione-- · Colaborador · Prestador |  |
| Colaborador/Prestador: | `chkdemissaof` | checkbox |  |  |
| Colaborador/Prestador: | `comboColaboradorPrestadorFiltro` | select |  |  |
| Status | `status` | select | Aberto · Pago |  |
| Evento: | `idEvento` | select |  |  |
| Data pagamento inicio: | `inicio` | text |  |  |
| Data pagamento termino: | `termino` | text |  |  |
| Data Ocorrência inicio: | `ocorrenciaInicio` | text |  |  |
| Data Ocorrência termino: | `ocorrenciaTermino` | text |  |  |
| Colaborador: | `colaboradorStatus` | select | --Selecione-- · Ativos · Inativo · Afastado · Demitido · Falecido · Suspenso · Alocado · Ausente |  |
| Tipo: | `trabalhista` | select | Colaborador · Prestador |  |
| Colaborador/Prestador: | `chkdemissaoi` | checkbox |  |  |
| Colaborador/Prestador: | `comboColaboradorPrestadorVale` | select |  |  |
| Evento: | `idEvento` | select |  |  |
| Forma de Pagamento: | `FormaPagamento` | select | Conta · Apontamento · FT · Horas de Missão |  |
| Vencimento Colaborador: | `data` | text |  |  |
| Vencimento Prestador: | `vencimento` | text |  |  |
| Data da Ocorrência: | `dataocorrencia` | text |  |  |
| Valor: | `valor` | text |  |  |
| Parcelas: | `quantidadeParcelas` | text |  |  |
| Motivo: | `Motivo` | text |  |  |
| Empresa Emitente: | `idEmpresaEmitente` | select |  |  |
| Descrição: | `Descricao` | textarea |  |  |
| Selecionar Arquivo | `Arquivo` | file |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| Parcelas | `numeroParcelas` | number |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/Cobranca/index` — Cobrança - Digiexpress  (HTTP 200)

Colunas do grid: Cliente · Duplicata · Conta Bancária · Nosso Número · Emissão · Vencimento · Total · Fonte Pagadora · Boleto Aceito

Botões: Processar · Concluir

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| empresaIdCliente | `empresaIdCliente` | select |  |  |
| idContasBancarias | `idContasBancarias` | select |  |  |
| status | `status` | select | Aberta · Paga · Vencida · Cancelada · Processo · Protestado |  |
| tipoFiltroData | `tipoFiltroData` | select | Emissão · Pagamento · Vencimento |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| duplicata | `duplicata` | text |  |  |
| nossoNumero | `nossoNumero` | text |  |  |
| idFormasPagamento | `idFormasPagamento` | select |  |  |
| valorDe | `valorDe` | text |  |  |
| valorAte | `valorAte` | text |  |  |
| Geração Pendente | `selecionarSemNossoNumero` | checkbox |  |  |
| selecionado | `selecionado` | checkbox |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| idContaBancaria | `idContaBancaria` | select |  |  |
| Selecionar Arquivo | `file` | file |  |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/ComissoesFechamento/index` — Fechamento de comissões - Digiexpress  (HTTP 200)

Colunas do grid: Início · Término · Origem

Botões: Incluir · Aprovar Fechamento

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| periodoInicioDe | `periodoInicioDe` | text |  |  |
| periodoInicioAte | `periodoInicioAte` | text |  |  |
| periodoTerminoDe | `periodoTerminoDe` | text |  |  |
| periodoTerminoAte | `periodoTerminoAte` | text |  |  |
| status | `status` | select | Aberto · Aprovado · Conta Gerada |  |
| origem | `origem` | select | Avulsa · Nota de Serviço |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| periodoInicio | `periodoInicio` | text |  |  |
| periodoTermino | `periodoTermino` | text |  |  |
| competencia | `competencia` | text |  |  |
| idNotaServico | `idNotaServico` | select |  |  |
| idEmitente | `idEmitente` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/View/AnaliseOrcamentaria` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/conciliacaoBancaria` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/Frontend/ContasFixas` — Contas Fixas - Digiexpress  (HTTP 200)

Colunas do grid: Tipo de Conta · Período · Valor · Pagador · Favorecido · Vencimento · Gerado Até · Empresa

Botões: Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| chaveEmpresa | `chaveEmpresa` | select |  |  |
| nome | `nome` | text |  |  |
| tipoConta | `tipoConta` | select | Contas à Pagar · Contas à Receber |  |
| valorDe | `valorDe` | text |  |  |
| valorAte | `valorAte` | text |  |  |
| DiaMesInicio | `DiaMesInicio` | text |  |  |
| DiaMesTermino | `DiaMesTermino` | text |  |  |
| tipoPessoa | `tipoPessoa` | select | Fornecedor · Cliente · Colaborador · Prestador · Pensionista |  |
| idFornecedor | `idFornecedor` | select |  |  |
| idCliente | `idCliente` | select |  |  |
| idColaborador | `idColaborador` | select |  |  |
| idPensionista | `idPensionista` | select |  |  |
| idColaborador | `idColaborador` | select |  |  |
| idCentroCusto | `idCentroCusto` | select |  |  |
| idEmitente | `idEmitente` | select |  |  |
| periodo | `periodo` | select | Semanal · Quinzenal · Mensal · Bimestral · Trimestral · Semestral · Anual |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| empresaModal | `empresaModal` | select |  |  |
| nome | `nome` | text |  |  |
| contaTipo | `contaTipo` | select | Contas à Pagar · Contas à Receber |  |
| tipoPessoaModal | `tipoPessoaModal` | select | Fornecedor · Cliente · Colaborador · Prestador · Pensionista | tipoPessoaModal |
| idFornecedor | `idFornecedor` | select |  | ModeloComboFornecedoresModal |
| idCliente | `idCliente` | select |  | ModeloComboClientesModal |
| idPrestador | `idPrestador` | select |  | ModeloComboPrestadoresModal |
| idPensionista | `idPensionista` | select |  | ModeloComboPensionistasModal |
| idColaborador | `idColaborador` | select |  | ModeloComboColaboradoresModal |
| idEmpresa | `idEmpresa` | select |  |  |
| idContaBancaria | `idContaBancaria` | select |  |  |
| idCusto | `idCusto` | select |  |  |
| idPlanoConta | `idPlanoConta` | select |  |  |
| idPlanoContaContabil | `idPlanoContaContabil` | select |  |  |
| valor | `valor` | text |  |  |
| periodo | `periodo` | select | Semanal · Quinzenal · Mensal · Bimestral · Trimestral · Semestral · Anual |  |
| diaSemana | `diaSemana` | select | DOMINGO · SEGUNDA · TERÇA · QUARTA · QUINTA · SEXTA · SABADO |  |
| diaMes | `diaMes` | text |  |  |
| tipoDia | `tipoDia` | select | Útil · Corrido · Dia Fixo (Mês Corrente) |  |
| Observacao | `Observacao` | textarea |  |  |

Bundles: `/Frontend/js/popper.min.js` · `/Frontend/js/select-data.js?v11` · `/Frontend/js/text-format.js?v1` · `/Frontend/js/validation.js?v2` · `/Frontend/js/user.js?v1` · `/Frontend/js/menu.js?v3` · `/Frontend/js/form.js?v14` · `/Frontend/js/login.js?v1`

---

## `/View/FluxoCaixa/Calendario` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/DashboardFinanceiro/Index` — Dashboard Financeiro  (HTTP 200)

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| fluxoCaixa | `fluxoCaixa` | checkbox |  |  |
| idCentrosCusto | `idCentrosCusto` | select |  |  |
| status | `status` | select | Aberta · Paga · Vencida · Processo |  |
| tipoFiltroData | `tipoFiltroData` | select | Emissão · Pagamento · Vencimento |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/contasPagar/relatorioContasPagar` — Relatório de Contas a Pagar - Digiexpress  (HTTP 200)

Botões: Todos

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| ChaveEmpresa | `ChaveEmpresa` | select |  |  |
| TipoPesquisa | `TipoPesquisa` | select | Emissão · Pagamento · Vencimento |  |
| DataInicial | `DataInicial` | text |  |  |
| DataFinal | `DataFinal` | text |  |  |
| EmpresaIdFornecedor | `EmpresaIdFornecedor` | select |  |  |
| idContaBancaria | `idContaBancaria` | select |  |  |
| Status | `Status` | select | Aberta · Paga · Vencida · Cancelada |  |
| Agrupamento | `Agrupamento` | select | -- SELECIONE -- · Fornecedor · Conta Bancaria · Entre Datas · Entre Datas Detalhado · Centro de Custo · Plano de Contas |  |
| idCentroCusto | `idCentroCusto` | select |  |  |
| idPlanoContas | `idPlanoContas` | select |  |  |
| Segmento | `Segmento` | select | Vigilância · Portaria · Limpeza · Monitoramento · Escolta Armada · Outros Serviços |  |
| CNPJEmitente | `CNPJEmitente` | select |  |  |
| idPlanoContas | `idPlanoContas` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/coberturas/index` — Coberturas - Digiexpress  (HTTP 200)

Colunas do grid: Motivo · Início · Termino · RE · Colaborador · RE Coberto · Coberto · Cliente · Número Contrato · Contrato · Vaga · Função · Escala

Botões: Limpar · ×

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idModelosVagas | `idModelosVagas` | select |  |  |
| idColaboradoresCobertura | `idColaboradoresCobertura` | select |  |  |
| idColaboradoresCobertos | `idColaboradoresCobertos` | select |  |  |
| motivo | `motivo` | select | Volante · Férias · Falta · Afastamento · Atestado · Folga · Atividade Externa |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| Tratativa | `tratativa` | checkbox |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/view/dashboardChamados` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/view/departamentos` — Digiexpress - View  (HTTP 200)


Bundles: `/view/assets/index-sXS-qoqY.js`

---

## `/frontend/livroocorrencias` — Livro de Ocorrências - Digiexpress  (HTTP 200)

Colunas do grid: Usuário · Cliente · Contrato · Data · Origem · Descricao

Botões: Finalizar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| Origem | `Origem` | select | -- Selecione -- · Q-Watcher · Vigilância |  |
| idContrato | `idContrato` | select |  |  |
| idCliente | `idCliente` | select |  |  |
| idUsuario | `idUsuario` | select |  |  |
| idUsuario | `idUsuario` | select |  |  |
| Visualizado | `Visualizado` | select | Não · Sim |  |
| Status | `Status` | select | Pendente · Finalizado |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| Data | `Data` | text |  |  |
| Descricao | `Descricao` | textarea |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/DashboardChecklist/Index` — Dashboard Checklist  (HTTP 200)

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idCliente | `idCliente` | select |  |  |
| ids | `ids` | select |  |  |
| idUsuarios | `idUsuarios` | select |  |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| Execucao | `Execucao` | select | Supervisão · Atividade |  |
| idSetor | `idSetor` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/Frontend/periodicidade` — Mapa de Supervisão  (HTTP 200)

Abas: Diário · Semanal · Quinzenal · Mensal · Bimestral · Trimestral · Semestral · Anual

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idContrato | `idContrato` | select |  |  |
| modeloRelatorio | `modeloRelatorio` | select | Listagem · Mapa |  |
| mes | `mes` | select | JANEIRO · FEVEREIRO · MARÇO · ABRIL · MAIO · JUNHO · JULHO · AGOSTO · SETEMBRO · OUTUBRO · NOVEMBRO · DEZEMBRO |  |
| ano | `ano` | text |  |  |
| Tipo | `Tipo` | select | Supervisão · Atividade |  |
| referencia | `referencia` | text |  |  |
| Periodo | `Periodo` | select | Diário · Semanal · Quinzenal · Mensal · Bimestral · Trimestral · Semestral · Anual |  |
| dia | `dia` | number |  |  |
| Trazer Excluídos: | `filtrotrazerExcluidos` | select | Não · Sim |  |
| idSetor | `idSetor` | select |  |  |
| idUsuarios | `idUsuarios` | select |  |  |

Bundles: `/Frontend/js/popper.min.js` · `/Frontend/js/select-data.js?v11` · `/Frontend/js/text-format.js?v1` · `/Frontend/js/validation.js?v2` · `/Frontend/js/user.js?v1` · `/Frontend/js/menu.js?v3` · `/Frontend/js/form.js?v14` · `/Frontend/js/login.js?v1`

---

## `/frontend/MapaSupervisores/Index` — Mapa de Supervisores  (HTTP 200)

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| idContrato | `idContrato` | select |  |  |
| inicio | `inicio` | text |  |  |
| ultimosRegistros | `ultimosRegistros` | select | Não · Sim |  |
| Tipo | `Tipo` | select | Supervisão · Atividade |  |
| idSetor | `idSetor` | select |  |  |
| idUsuarios | `idUsuarios` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/auditorias` — Auditorias - Digiexpress  (HTTP 200)

Colunas do grid: Placa · Condutor · Km · Data

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| empresas | `empresas` | select |  |  |
| placa | `placa` | text |  |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/vistorias` — Vistorias - Digiexpress  (HTTP 200)

Colunas do grid: Status do Checklist · Status de Chegada · Placa · Condutor · Km · Data · Manutenção Pendente · Condutor · Km · Data · Manutenção Pendente

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| empresas | `empresas` | select |  |  |
| placaVeiculo | `placaVeiculo` | text |  |  |
| statusRetorno | `statusRetorno` | select | Todos · Tiveram diferenças · Não retornado · Retornado igual |  |
| intervaloData | `intervaloData` | select | Saída · Retorno |  |
| dataInicial | `dataInicial` | text |  |  |
| dataFinal | `dataFinal` | text |  |  |
| Estado: | `estados` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/grupofrotas` — Grupo de Frotas - Digiexpress  (HTTP 200)

Colunas do grid: Nome

Botões: Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| Nome | `Nome` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/localidades` — Localidades - Digiexpress  (HTTP 200)

Colunas do grid: Nome · CEP · Endereço · Número · Bairro · Cidade · Estado · Complemento · Contato · Telefone

Botões: Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| nome | `nome` | text |  |  |
| contato | `contato` | text |  |  |
| endereco | `endereco` | text |  |  |
| Nome | `Nome` | text |  |  |
| CEP | `CEP` | text |  |  |
| Endereco | `Endereco` | text |  |  |
| Numero | `Numero` | text |  |  |
| Bairro | `Bairro` | text |  |  |
| Cidade | `Cidade` | text |  |  |
| Estado | `Estado` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |  |
| Complemento | `Complemento` | text |  |  |
| Contato | `Contato` | text |  |  |
| Telefone | `Telefone` | text |  |  |
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/usuariosfrotas` — Usuários do Frotas - Digiexpress  (HTTP 200)

Colunas do grid: Nome · Login

Botões: Salvar

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| Localizar: | `Localizar` | text |  |  |
| Localizar: | `LinhasPorPagina` | text |  |  |
| Nome | `Nome` | text |  |  |
| Login | `Login` | text |  |  |
| listaPermissoes | `listaPermissoes` | select | Todas · Abastecimentos · Vistorias · Nenhuma · Requisição de Abastecimento · Pernoites · Auditorias · Incluir Veículos · Solicitação Manutenção · Últimos Abast. |  |
| listaGrupoFrotas | `listaGrupoFrotas` | select |  |  |
| idGrupoChecklist | `idGrupoChecklist` | select |  |  |
| idEmpregado | `idEmpregado` | select |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

## `/frontend/Ferias/Editar` — Férias - Digiexpress  (HTTP 200)

Colunas do grid: Colaborador · Férias Perdidas · Gozo Menor · Início · Término · Início Aquisitivo · Término Aquisitivo · Dias Perdidos por Falta · Dias de Abono · Dias de Período Aquisitivo

Botões: Calcular · Salvar Todos

| Campo | Interno | Tipo | Opções | Modal |
|---|---|---|---|---|
| colaboradoresDemitidos | `colaboradoresDemitidos` | checkbox |  |  |
| idColaboradores | `idColaboradores` | select |  |  |
| inicio | `inicio` | text |  |  |
| termino | `termino` | text |  |  |
| GozoMenor | `GozoMenor` | select | Não · Sim |  |
| diasAbono | `diasAbono` | text |  |  |
| credito | `credito` | text |  |  |
| desconto | `desconto` | text |  |  |

Bundles: `/frontend/js/popper.min.js` · `/frontend/js/select-data.js?v11` · `/frontend/js/text-format.js?v1` · `/frontend/js/validation.js?v2` · `/frontend/js/user.js?v1` · `/frontend/js/menu.js?v3` · `/frontend/js/form.js?v14` · `/frontend/js/login.js?v1`

---

# Mapa real da API REST — 0 rotas citadas nos bundles


---

## Métodos (OPTIONS)

- `/api/RH/Ferias` → {'status': 404, 'allow': ''}
- `/api/RH/ColaboradorBases` → {'status': 404, 'allow': ''}
- `/api/Faturamento/Comissoes` → {'status': 404, 'allow': ''}
- `/api/RH/Colaboradores` → {'status': 404, 'allow': ''}
- `/api/Financeiro/ContasPagar` → {'status': 404, 'allow': ''}
- `/api/Comercial/Contratos` → {'status': 404, 'allow': ''}
