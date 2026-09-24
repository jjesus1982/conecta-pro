# DGX — os 127 parâmetros do sistema (`GET /api/Settings/Parametros`)

Lidos em 24/09/2026 com Bearer de `GET /Usuarios/token` (JWT `iss=Digiexpress.Autenticacao`, `roles=[adm]`, `emp=conectamaispatrimonial`, validade 15 min). Cada parâmetro é `{nome, valor, chaveEmpresa}` — **um valor por empresa**, é assim que o multi-CNPJ deles parametriza.

Valores em branco são o padrão de uma instância nova (a nossa, sem uso). Segredos (senhas de e-mail) foram omitidos.


## Benefícios

| Parâmetro | Valor na instância |
|---|---|
| `EmitenteFixoBeneficios` | — |
| `VRBeneficiosCentroCustoEmitente` | false |

## Crachá

| Parâmetro | Valor na instância |
|---|---|
| `ModeloCracha` | — |

## E-mail/SMTP

| Parâmetro | Valor na instância |
|---|---|
| `CRDiasAVencerEmailAuto` | 0 |
| `CRDiasVencidosEmailAuto` | 0 |
| `CRMsgAVencerEmailAuto` | — |
| `CRMsgVencidosEmailAuto` | — |
| `PoliticaDeSenha` | (omitido) |
| `SenhaComMaiusculas` | (omitido) |
| `SenhaComMinusculas` | (omitido) |
| `SenhaComNumeros` | (omitido) |
| `SenhaComSimbolos` | (omitido) |
| `SenhaDiasExpiracao` | (omitido) |
| `SenhaQtdDigitos` | (omitido) |

## Empresa

| Parâmetro | Valor na instância |
|---|---|
| `DominioPatrimonialOnline` | ConectaMaisPatrimonial.com.br |

## Escolta/Missão

| Parâmetro | Valor na instância |
|---|---|
| `CustoMedioKMEscolta` | — |
| `PercentualTaxaAdministrativaEscolta` | — |
| `TrazerClienteEscolta` | false |

## Fechamento

| Parâmetro | Valor na instância |
|---|---|
| `AppSupervisoes.ModeloAplicativo` | Supervisao |
| `BoletimModeloPadrao` | — |
| `DiasFechamento` | 0 |
| `DiasLimiteFaturamento` | 0 |
| `LinhasGridFechamento` | 50 |
| `ModeloContrato` | 01 |
| `ModeloFatura` | — |
| `ModeloRecibo` | 01 |
| `ModeloReciboCestaBasica` | — |
| `ModeloRelatorioCoberturas` | — |

## Fiscal

| Parâmetro | Valor na instância |
|---|---|
| `NotaServicoContratoValorProporcional` | false |
| `NotaServicoDiasContratoValorProporcional` | 30 |
| `NotasServicoEnvioAutomatico` | — |
| `PERMITIR_RETROCEDER_NOTA_STATUS_ENVIADO` | false |

## Folha/Apontamento

| Parâmetro | Valor na instância |
|---|---|
| `DiaApontamento` | 1 |
| `DiasAntesLancarAusencia` | 3 |
| `EventoAprovacaoSuspensao` | 0 |
| `EventosFaltaPorPeriodo` | — |
| `EventosRelatorioApontamento` | — |
| `ExibirEventoCartaoAssinatura` | true |
| `ModeloPadraoRelatorioApontamento` | — |

## Interface

| Parâmetro | Valor na instância |
|---|---|
| `ContasReceberColunasVisiveisGrid` | ["chaveEmpresa","duplicata","observacoes","descricaoParcela","sacado","cnpjClien |
| `ExibicaoCompletaGridOperacional` | false |

## Ordens de Serviço

| Parâmetro | Valor na instância |
|---|---|
| `AppFrotas.LimitarFotos` | true |
| `AppFrotas.LimiteFotos` | 3 |
| `AppSupervisoes.Agendamentos` | true |
| `AppSupervisoes.FinalizarAbertos` | false |
| `AppSupervisoes.FotosAltaQualidade` | false |
| `AppSupervisoes.LimitarFotos` | true |
| `AppSupervisoes.LimiteFotos` | 3 |
| `AppSupervisoes.SetorChamados` | true |
| `AvisoContratosDataBase` | 1 |
| `BloquearAgenteCursos` | false |
| `BloqueioDefinicaoIntegracaoSolicitacoesPR` | False |
| `ContaPagarCamposAlteraveis` | — |
| `ContasReceberColunaObsPos` | -1 |
| `ContratoDiasApos` | 90 |
| `DEMANDAS_EXIBIR_TODOS_COLABORADORES` | false |
| `ExibirMotivosCartaoAssinatura` | true |
| `FaturamentoSistema` | false |
| `HorasOciosas` | — |
| `ModeloMovimentacaoRelatorioSegurancaTrabalho` | 01 |
| `ModeloRelatorioContratoSupervisor` | — |
| `MostrarIdSistema` | false |
| `PecasNovoSuprimentos` | false |
| `ProntaResposta` | false |
| `SuprimentosBaseUnica` | false |
| `ValidacaoProntaRespostaPrestador` | false |
| `Validar_Frequencia_Documentos_Admissionais` | true |

## Outros

| Parâmetro | Valor na instância |
|---|---|
| `AppSupervisoes.CameraTimeStamp` | false |
| `AppSupervisoes.EnviarLocalizacao` | false |
| `AppSupervisoes.EnvioPendencias` | EnvioLote |
| `AppSupervisoes.ExtrairRelatorio` | false |
| `AppSupervisoes.IntervaloAvisoAtividadesEmAberto` | 0 |
| `AppSupervisoes.OpcoesIniciarServico` | false |
| `AppSupervisoes.ValidarFotoChamado` | true |
| `AppSupervisoes.VersaoAplicativo` | 120 |
| `AprovacaoBaixarConta` | false |
| `BloquearExcedente` | false |
| `BoletimGrupoPadrao` | — |
| `BoletimOrdenacaoPadrao` | — |
| `CalcularVencimentoRecibo` | false |
| `ChaveFilial` | ConectaMaisPatrimonial |
| `CodigoBase` | 1 |
| `ContaPadraoContasPagar` | — |
| `ContaPadraoContasReceber` | — |
| `ContratoDiasAntes` | 30 |
| `ContratoFeriasDecimoTerceiro` | — |
| `DiasAgendamento` | 2 |
| `DiasInclusaoClientes` | 7 |
| `DiasPrevisaoRecrutamento` | 0 |
| `DiasTCE` | 5 |
| `ExibicaoPorJornada` | false |
| `ExibirFontePagadora` | false |
| `ExibirObservacoesCartaoAssinatura` | true |
| `ExibirOcorrenciaMapaRondas` | true |
| `FinanceiroContextoEmpresa` | False |
| `FinanceiroOrdenacaoPadrao` | — |
| `INICIO_OPERACAO_ANTECIPADO` | false |
| `IdPrestadorComoRE` | false |
| `Justificativa_Padrao` | — |
| `LinkProntoAtendimentoIntegracao` | https://ssdtecnologia.online/r3s/api/ocorrencia?token=75f2d1faafc317941e3d78e84d |
| `MFA` | false |
| `NivelPlanoContas` | — |
| `NomeFantasia` | false |
| `OrdenacaoImpressaoRps` | — |
| `PrestadorCelularObrigatorio` | false |
| `PrestadorFormaPagamentoObrigatoria` | false |
| `RePrestadorAutomatico` | false |
| `RecrutamentoCriarAlocacoes` | false |
| `RetornarPagamentoConta` | false |
| `TicketCodigoClienteTAE` | — |
| `TicketCodigoClienteTRE` | — |
| `TicketCodigoClienteTSF` | — |
| `TicketCodigoClienteVA` | — |
| `TicketCodigoClienteVR` | — |
| `TimeoutQuadroOperacional` | — |
| `UsarFichaComoMatricula` | false |
| `WhatsappEntregaExameDemissional` | — |

## Ponto

| Parâmetro | Valor na instância |
|---|---|
| `AlterarEscalaNoPonto` | false |
| `BloquearBatiemntoPontoOnline` | false |
| `CONTROLE_ACESSO_RAIO_MAXIMO` | 1000 |
| `CartaoPontoExibirLocalAlocacao` | false |
| `EsconderExtensoesPonto` | false |
| `PontoAutomatico` | false |
| `ToleranciaIntegracaoBatimentos` | 15 |

## Uniformes/EPI

| Parâmetro | Valor na instância |
|---|---|
| `ModeloEntregaUniformesDetalhes` | — |
| `ModeloEntregaUniformesListagem` | — |
| `ModeloFichaEntregaUniformes` | 01 |


_Total: 127 parâmetros._
