# DGX — Configurações do sistema e modais descobertos pelo Index

Lido em 24/09/2026. Para as entidades cujo `/Incluir` dava 500, o link real do modal foi extraído do HTML do `/Index` (`href`, `onclick`, `data-url`). Inclui a página **Configurações** inteira — 108 parâmetros do sistema — e os filtros dos grids financeiros (que revelam as dimensões do modelo).


---

## Colaboradores  (`/Colaboradores/Index` · HTTP 200)

Botões da tela: Salvar · Fechar · Concluir · Continuar · Confirmar

Filtros do grid:

- `idsEmitentes` (select): -- Selecione -- · - CONECTAMAIS PATRIMONIAL


### Modal `/Colaboradores/Incluir?SubInclusao=False`

**Form** `-` → `/Colaboradores/Salvar` (14 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Inclusao` | hidden | `23/09/2026 00:00:00` |
| _(oculto)_ | `Colaborador` | hidden | `true` |
| RE | `RE` | text | maxlength=20 |
| CPF | `CPF` | text |  |
| Nome | `Nome` | text | maxlength=200 |
| Ficha: | `NomeGuerra` | text | maxlength=200 |
| Ficha: | `Admissao` | text | maxlength=20 |
| Ficha: | `Ficha` | text | maxlength=20 |
| Jovem Aprendiz: | `Salario` | text | maxlength=18 |
| Jovem Aprendiz: | `JovemAprendiz` | select | NÃO · SIM |
| Nível: | `CodigoCargo` | select |  |
| Nível: | `idNivel` | select |  |
| Nível: | `PCD` | select | NÃO · SIM |

---

## Postos  (`/Postos/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## Movimentacoes  (`/Movimentacoes/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### Modal `/Movimentacoes/IncluirMovimentacao`

**Form** `-` → `/Movimentacoes/Salvar` (23 campos)
Seções: Origem · Destino:

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `0` |
| _(oculto)_ | `Inclusao` | hidden | `23/09/2026 23:56:50` |
| _(oculto)_ | `idOrigem` | hidden | `` |
| _(oculto)_ | `Importacao` | hidden | `False` |
| _(oculto)_ | `Visualizado` | hidden | `False` |
| **[Origem]** | | | |
| Início: | `Data` | text |  |
| Início: | `UltimoDia` | text | disabled=disabled |
| Colaborador | `idcolaboradorAutoComplete` | text |  |
| _(oculto)_ | `idColaborador` | hidden | `0` |
| Admissão: | `Admissao` | text | disabled=disabled |
| Admissão: | `Cargo` | text | disabled=disabled |
| _(oculto)_ | `idCargo` | hidden | `` |
| Cliente: | `ClienteAlocado` | text | disabled=disabled |
| Vaga: | `ModeloVaga` | text | disabled=disabled |
| _(oculto)_ | `idModelo` | hidden | `` |
| Vaga: | `Turno` | text | disabled=disabled |
| **[Destino:]** | | | |
| Tipo de Movimentação: | `TipoMovimentacao` | select | -- Selecione -- · ALOCAR COLABORADOR EM NOVA VAGA · REMOVER O COLABORADOR DA VAGA ATUAL |
| Tipo de Movimentação: | `Motivo` | select | -- SELECIONE -- · A PEDIDO DO CLIENTE · A PEDIDO DO SUPERVISOR · ALOCAÇÃO DE VAGA · COBERTURA DE AFASTAMENTO · COBERTURA DE FALTA · COBERTURA DE FERIAS · TREINAMENTO |
| Contrato: | `idContrato` | select | -- SELECIONE -- |
| Vaga: | `idModeloVaga` | select |  |
| Vaga: | `idSequencia` | select | -- SELECIONE -- |
| Observações: | `Observacoes` | textarea |  |

---

## GridPlanejamento  (`/GridPlanejamento/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## Avisos  (`/Avisos/Index` · HTTP 500)


---

## Clientes  (`/Clientes/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### Modal `/Clientes/Incluir?SubInclusao=False`

**Form** `-` → `/Clientes/Salvar` (25 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Cliente` | hidden | `True` |
| _(oculto)_ | `IBGEMunicipioPrincipal` | hidden | `` |
| _(oculto)_ | `IBGEUFPrincipal` | hidden | `` |
| _(oculto)_ | `PercentualReducaoINSS` | hidden | `0` |
| _(oculto)_ | `Escolta` | hidden | `True` |
| Razão Social: | `RazaoSocial` | text | maxlength=200 |
| Razão Social: | `Nome` | text |  |
| Natureza Juridica: | `idNaturezaJuridica` | select | -- Selecione -- · ASSOCIAÇÕES SEM FINS LUCRATIVOS - · EMPRESA INDIVIDUAL - EI · EMPRESA INDIVIDUAL DE RESPONSABILIDADE LIMITADA - EIRELI · SOCIEDADE ANÔNIMA - SA · SOCIEDADE EMPRESARIAL LIMITADA - LTDA · SOCIEDADE LIMITADA UNIPESSOAL - SLU |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `InscricaoNacional` | text |  |
| Estrangeiro: | `Estrangeiro` | select | NÃO · SIM |
| Estrangeiro: | `DocumentoEstrangeiro` | text | maxlength=20, disabled=disabled |
| CEP: | `CEPPrincipal` | text |  |
| CEP: | `EnderecoPrincipal` | text | maxlength=300 |
| Número: | `NumeroPrincipal` | text | maxlength=20 |
| Número: | `BairroPrincipal` | text | maxlength=100 |
| Cidade: | `CidadePrincipal` | text | maxlength=100 |
| Cidade: | `EstadoPrincipal` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO · EX |
| Complemento: | `ComplementoPrincipal` | text | maxlength=100 |
| Complemento: | `RotaPropria` | select | NÃO · SIM |
| Complemento: | `EmitirNotaFiscal` | select | NÃO · SIM |
| Representante: | `idModeloBoletim` | select | -- Selecione -- · Modelo - 1 (Datas baseadas no intervalo de cobrança) · Modelo - 2 - GR-BSA · Modelo - 3 · Modelo - 4 · Modelo - 5 · Modelo - 6 · Modelo - 7 · Modelo - 8 · Modelo - 9 · Modelo - 10 · Modelo - 11 - Previsão de início, Nº Nota Veículo Escoltado (Datas baseadas no intervalo de cobrança) · Modelo - 12 · Modelo - 13 · Modelo - 14 · Modelo - 15 · Modelo - 16 · Modelo - 17 · Modelo - 18 · Modelo - 19 · Modelo - 20 (Datas baseadas no intervalo de cobrança) · Modelo - 21 - GR-BSA com deslocamento · Modelo - 21 - GR-BSA com deslocamento, paradas e transportadora · Modelo - 2 - GR-BSA paradas e transportadora · Modelo - 11 (Datas baseadas no intervalo de cobrança) · Modelo - 18 - Número EO, Deslocamento · Modelo - 2 - Agrupar por Data · Modelo Gerenciadora · Modelo - 1 - Desconto / Acréscimo (Datas baseadas no intervalo de cobrança) · Modelo - 22 (Datas baseadas no intervalo de cobrança) · Modelo - 23 - Paradas · Modelo - 2 - Viatura · AdmFilial - Modelo 02 · AdmFilial - Modelo 04 (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 05 · AdmFilial - Modelo 07 (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 09 · AdmFilial - Modelo 02 - Sem Motorista, Hora Parada e Preservação · AdmFilial - Modelo 04 - Com Solicitante e Chegada da Operação (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 04 - Com Solicitante, Chegada da Operação e Nº EO (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 09 - Com Valor · AdmFilial - Modelo  04 - Com Solicitante, Chegada da Operação, Nº EO e Número de Viagem (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 04 - Com Solicitante, Chegada da Operação, Nº EO e Previsão de Inicio (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 09 - Com Tipo de Viagem · Modelo - 24 - Rateio OS · Modelo - 21 - GR-BSA com Km inicial e final, paradas e transportadora · AdmFilial - Modelo 10 (Datas baseadas no intervalo de cobrança) · AdmFilial - Modelo 11 · AdmFilial - Modelo 01 · Modelo - 24 - Tabelas por Período (Datas baseadas no intervalo de cobrança) · Modelo - 11 - Número EO, Deslocamento · Modelo - 2 - GR-BSA - Fontes Pagadoras · Modelo - 2 - GR-BSA - Lojas · AdmFilial - Modelo 12 · Modelo - 4 - Agentes e CPF · Modelo - 11 - Solicitante (Datas baseadas no intervalo de cobrança) · Modelo - 2 - GR-BSA - Nome Agentes · AdmFilial - Modelo 10 - Previsão de Início · Modelo com EO e OBS · Modelo - 7 - Número EO |
| Representante: | `idRepresentante` | select | -- Selecione -- |

---

## ContasPagar  (`/ContasPagar/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Calcular · Baixar · Aprovar · Enviar · Atualizar · Pensionistas · Rúbricas · Remessa de Pagamentos · Retorno de Pagamentos · Cancelar · Gerar · Processar · Confirmar · Continuar

Filtros do grid:

- `chaveEmpresa` (select)
- `cnpjEmitente` (select)
- `empresaIdFornecedores` (select)
- `CheckConsultaDemitidos` (checkbox)
- `empresaIdColaborador` (select)
- `idPensionistas` (select)
- `idAdvogados` (select)
- `tipoPessoa` (select): Todos · Fornecedor · Colaborador · Prestador · Pensionista · Advogado
- `idFormasPagamento` (select)
- `idContasBancarias` (select)
- `centrosCustoDescendentes` (checkbox)
- `idCentrosCusto` (select)
- `idPlanoContas` (select)
- `status` (select): Aberta · Paga · Vencida · Cancelada · Processo
- `segmentos` (select): Vigilância · Portaria · Limpeza · Monitoramento · Escolta · Outros · Tecnologia
- `exportado` (select): Não · Sim
- `aprovacao` (select): Não · Sim
- `documento` (text)
- `descricao` (text)
- `ChequeEmitido` (select): Não · Sim
- `NumeroCheque` (text)
- `tipoFiltroData` (select): Emissão · Pagamento · Vencimento
- `inicio` (text)
- `termino` (text)
- `competencia` (text)


---

## ContasReceber  (`/ContasReceber/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Calcular · Baixar · Salvar · Atualizar · Cancelar · Processar · Confirmar · Enviar · Continuar

Filtros do grid:

- `chaveEmpresa` (select)
- `idClienteCompostos` (select)
- `idFontesPagadoras` (select)
- `cnpjEmitente` (select)
- `empresaIdColaborador` (select)
- `idFormasPagamento` (select)
- `idContasBancarias` (select)
- `centrosCustoDescendentes` (checkbox)
- `idCentrosCusto` (select)
- `idPlanoContas` (select)
- `status` (select): Aberta · Paga · Vencida · Cancelada · Processo · Protestado
- `segmentos` (select): Vigilância · Portaria · Limpeza · Monitoramento · Escolta · Outros · Tecnologia
- `exportado` (select): Não · Sim
- `duplicata` (text)
- `descricao` (text)
- `competencia` (text)
- `tipoFiltroData` (select): Emissão · Pagamento · Vencimento
- `inicio` (text)
- `termino` (text)
- `modelo` (select): Listagem · Rateios (Todos) · Rateios (Específicos) · Listagem Grid · Ordenado
- `transferencia` (select): -- Selecione -- · Não · Sim
- `nossoNumero` (text)
- `numeroNota` (text)
- `boletoEmitido` (select): SIM · NÃO
- `protestado` (select): SIM · NÃO


---

## ContasBancarias  (`/ContasBancarias/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Salvar · Gerar · Enviar · Continuar · Confirmar

Filtros do grid:

- `chaveEmpresa` (select)
- `descricao` (text)
- `idContaBancariaFiltro` (hidden)
- `Inicio` (text)
- `termino` (text)
- `intervaloContas` (select): Emissão · Pagamento · Vencimento · Pagamento ou Vencimento


---

## PlanoContas  (`/PlanoContas/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Atualizar · Salvar · Enviar · Continuar · Confirmar

Filtros do grid:

- `nome` (text)
- `idsPlanoContaPai` (select)
- `ordenacao` (select): Nome · Código


---

## CentrosCusto  (`/CentrosCusto/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Salvar · Gerar · Enviar · Continuar · Confirmar

Filtros do grid:

- `idCustoPai` (select)
- `idCusto` (select)
- `modelo` (select): Detalhado · Listagem


---

## FormasPagamento  (`/FormasPagamento/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Salvar · Enviar · Continuar · Confirmar

Filtros do grid:

- `nome` (text)


---

## CondicoesPagamento  (`/CondicoesPagamento/Index` · HTTP 200)

Botões da tela: Aplicar · Fechar · Salvar · Enviar · Continuar · Confirmar

Filtros do grid:

- `descricao` (text)


---

## TransferenciasBancarias  (`/TransferenciasBancarias/Index` · HTTP 500)


---

## Empresas  (`/Empresas/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## Configuracoes  (`/Configuracoes/Index` · HTTP 200)

Botões da tela: Inserir Imagem · Remover Imagem · Visualizar Imagem · Concluir · Fechar · Continuar · Confirmar


### Modal `/Configuracoes/EditarBeneficios`

**Form** `-` → `/Configuracoes/EditarBeneficios` (8 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Tipo Benefício: | `idBeneficio` | select | -- Selecione -- |
| Quantidade: | `Quantidade` | text |  |
| Quantidade: | `Valor` | text |  |
| Quantidade: | `Inclusao` | text |  |
| Quantidade: | `Cancelamento` | text |  |
| Limite Faltas: | `LimiteFaltas` | text |  |
| Limite Faltas: | `LimiteFaltasJustificadas` | text |  |

### `/Configuracoes/IncluirImagemFundoCracha` → HTTP 500

### Página inteira (parâmetros do sistema)

**Form** `-` → `/Configuracoes/Salvar` (108 campos)
Seções: Quantidade de Linhas Padrão · Ordens de Serviço · Nota de Serviço · Fechamento · Equipes · Salário Mínimo · Benefícios · Folha de Pagamento · Raio (Controle de Acesso) · Fundo Crachá · Usuário do Cronos · Configurações do Cronos · Ponto Online

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `1` |
| _(oculto)_ | `ValidadePadraoUniformes` | hidden | `` |
| _(oculto)_ | `TipoRateioUniforme` | hidden | `0` |
| _(oculto)_ | `EmailEnvio` | hidden | `` |
| _(oculto)_ | `EmailSenha` | hidden | `` |
| _(oculto)_ | `EmailSMTP` | hidden | `` |
| _(oculto)_ | `EmailPorta` | hidden | `587` |
| _(oculto)_ | `EmailSSL` | hidden | `True` |
| _(oculto)_ | `EmailEnvioBoleto` | hidden | `` |
| _(oculto)_ | `EmailSenhaBoleto` | hidden | `` |
| _(oculto)_ | `EmailSMTPBoleto` | hidden | `` |
| _(oculto)_ | `EmailPortaBoleto` | hidden | `` |
| _(oculto)_ | `EmailSSLBoleto` | hidden | `False` |
| _(oculto)_ | `AlertaSupervisoesEmail` | hidden | `` |
| _(oculto)_ | `AlertaSupervisoesSenha` | hidden | `` |
| _(oculto)_ | `AlertaSupervisoesSMTP` | hidden | `` |
| _(oculto)_ | `AlertaSupervisoesPorta` | hidden | `` |
| _(oculto)_ | `AlertaSupervisoesSSL` | hidden | `False` |
| _(oculto)_ | `DemandasEmail` | hidden | `` |
| _(oculto)_ | `DemandasEmailSenha` | hidden | `` |
| _(oculto)_ | `DemandasEmailSMTP` | hidden | `` |
| _(oculto)_ | `DemandasEmailPorta` | hidden | `` |
| _(oculto)_ | `DemandasEmailSSL` | hidden | `False` |
| _(oculto)_ | `ContratoEmail` | hidden | `` |
| _(oculto)_ | `ContratoEmailSenha` | hidden | `` |
| _(oculto)_ | `ContratoEmailSMTP` | hidden | `` |
| _(oculto)_ | `ContratoEmailPorta` | hidden | `` |
| _(oculto)_ | `ContratoEmailSSL` | hidden | `False` |
| _(oculto)_ | `PernoiteEmail` | hidden | `` |
| _(oculto)_ | `PernoiteEmailSenha` | hidden | `` |
| _(oculto)_ | `PernoiteEmailSMTP` | hidden | `` |
| _(oculto)_ | `PernoiteEmailPorta` | hidden | `` |
| _(oculto)_ | `PernoiteEmailSSL` | hidden | `False` |
| _(oculto)_ | `PontoEmail` | hidden | `` |
| _(oculto)_ | `PontoEmailSenha` | hidden | `` |
| _(oculto)_ | `PontoEmailSMTP` | hidden | `` |
| _(oculto)_ | `PontoEmailPorta` | hidden | `` |
| _(oculto)_ | `PontoEmailSSL` | hidden | `False` |
| **[Quantidade de Linhas Padrão]** | | | |
| Linhas Grid: | `LinhasGrid` | text |  |
| **[Ordens de Serviço]** | | | |
| Exibir OS: | `GridOperacionalOS` | checkbox |  |
| _(oculto)_ | `GridOperacionalOS` | hidden | `false` |
| Exibir OS: | `GridOperacionalMCT` | checkbox |  |
| _(oculto)_ | `GridOperacionalMCT` | hidden | `false` |
| Exibir OS: | `ExibirReIdentificacaoEquipe` | checkbox |  |
| _(oculto)_ | `ExibirReIdentificacaoEquipe` | hidden | `false` |
| Exibir OS: | `TratativaSolicitacao` | checkbox |  |
| _(oculto)_ | `TratativaSolicitacao` | hidden | `false` |
| Tabela de Preço na Rota: | `TabelaPrecoNaRota` | checkbox |  |
| _(oculto)_ | `TabelaPrecoNaRota` | hidden | `false` |
| Tempo Minimo de Missão: | `hTempoMinimoMissao` | text |  |
| Tempo Minimo de Missão: | `DistanciaMinimaMissao` | text |  |
| Tempo Minimo de Missão: | `DistanciaMaximaMissao` | text |  |
| Tempo Minimo de Missão: | `KMMaximoUltimaOperacao` | text |  |
| EmailsCopiaEscoltaOnline | `EmailsCopiaEscoltaOnline` | text |  |
| **[Nota de Serviço]** | | | |
| Exibir Observações do Cliente: | `exibirObservacao` | checkbox |  |
| **[Fechamento]** | | | |
| Linhas Grid: | `LinhasGridFechamento` | text |  |
| Linhas Grid: | `VeiculoEscoltadoDetalhado` | select | ABREVIADO · DETALHADO |
| Linhas Grid: | `FaturamentoSistema` | select | MANUAL · SISTEMA |
| Linhas Grid: | `Modelo` | select | --SELECIONE-- · Modelo - 1 · Modelo - 2 · Modelo - 3 · Modelo - 4 · Modelo - 5 · Modelo - 6 · Modelo - 7 · Modelo - 8 · Modelo - 9 · Modelo - 10 · Modelo - 11 · Modelo - 12 · Modelo - 13 · Modelo - 14 · Modelo - 15 · Modelo - 16 · Modelo - 17 · Modelo - 18 · Modelo - 19 · Modelo - 20 |
| Arredondar Vel. Média: | `ArredondarVelocidadeMedia` | select | SIM · NÃO |
| Arredondar Vel. Média: | `ArredondarHorarioTabela` | select | SIM · NÃO |
| **[Equipes]** | | | |
| Prestar Contas Obrigatório: | `PrestarContasObrigatorio` | checkbox |  |
| _(oculto)_ | `PrestarContasObrigatorio` | hidden | `false` |
| Prestar Contas Obrigatório: | `ContaOperacionalEquipeCreditos` | select |  |
| Prestar Contas Obrigatório: | `ContaOperacionalEquipeFechamento` | select |  |
| Plano de Conta Créditos: | `PlanoOperacionalEquipeCreditos` | select |  |
| Plano de Conta Créditos: | `PlanoOperacionalEquipeFechamento` | select |  |
| Inicio Hora Noturna: | `hInicioNoturnoAgente` | text |  |
| Inicio Hora Noturna: | `hTerminoNoturnoAgente` | text |  |
| Inicio Hora Noturna: | `VelocidadeMediaApontamento` | text |  |
| Inicio Hora Noturna: | `KmParadasApontamento` | text |  |
| Exibir Nome de Guerra: | `PreAlertaNomeGuerra` | checkbox |  |
| _(oculto)_ | `PreAlertaNomeGuerra` | hidden | `false` |
| EmailsCopiaPreAlerta | `EmailsCopiaPreAlerta` | text |  |
| CopiaEmailDelesp | `CopiaEmailDelesp` | text |  |
| **[Salário Mínimo]** | | | |
| Novo Salário Mínimo | `ValorSalarioMinimo` | text |  |
| **[Benefícios]** | | | |
| Usuário SPTRANS: | `UsuarioSPTRANS` | text |  |
| Usuário SPTRANS: | `ApontamentosCombo` | text |  |
| **[Folha de Pagamento]** | | | |
| Dia de Apontamento: | `DiaApontamento` | text |  |
| Dia de Apontamento: | `DiasAusencia` | text |  |
| Dia de Apontamento: | `idEventoAusencia` | select | 9000 - DIAS SALARIO · 9001 - DSR FALTA · 9005 - ADICIONAL NOTURNO · 9006 - HORA NOTURNA REDUZIDA · 9007 - DSR SOBRE ADICIONAL NOTURNO · 9008 - DSR SOBRE HORA EXTRA |
| **[Raio (Controle de Acesso)]** | | | |
| Valor Raio: | `ValorRaioRelogioPonto` | text |  |
| **[Fundo Crachá]** | | | |
| _(oculto)_ | `ImagemFundoCracha` | hidden | `` |
| _(oculto)_ | `uploadImagem` | hidden | `/Configuracoes/IncluirImagemFu` |
| SelecionarArquivo | `SelecionarArquivo` | file |  |
| **[Usuário do Cronos]** | | | |
| _(oculto)_ | `UsuarioControleAcesso.id` | hidden | `1` |
| _(oculto)_ | `UsuarioControleAcesso.Excluido` | hidden | `False` |
| Login: | `UsuarioControleAcesso.Login` | text | maxlength=20 |
| Login: | `ControleAcessoSenha` | password | maxlength=20 |
| **[Configurações do Cronos]** | | | |
| _(oculto)_ | `ConfiguracaoControleAcesso.id` | hidden | `1` |
| _(oculto)_ | `ConfiguracaoControleAcesso.Excluido` | hidden | `False` |
| _(oculto)_ | `ConfiguracaoControleAcesso.PrecisaoReconhecimentoFacial` | hidden | `0` |
| Prefixo do RE: | `ConfiguracaoControleAcesso.PrefixoRE` | text | maxlength=4 |
| Prefixo do RE: | `ConfiguracaoControleAcesso.ToleranciaValidacaoHoras` | text |  |
| Prefixo do RE: | `ConfiguracaoControleAcesso.Precisao` | text |  |
| Prefixo do RE: | `ConfiguracaoControleAcesso_RemoverBancoHoras` | select | Não · Sim |
| ConfiguracaoControleAcesso_ValidarToleranciaBatimentos | `ConfiguracaoControleAcesso_ValidarToleranciaBatimentos` | select | Não · Sim |
| ConfiguracaoControleAcesso.ToleranciaBatimentos | `ConfiguracaoControleAcesso.ToleranciaBatimentos` | text |  |
| ConfiguracaoControleAcesso_TestarVivacidade | `ConfiguracaoControleAcesso_TestarVivacidade` | select | Não · Sim |
| ConfiguracaoControleAcesso_RepetirTeste | `ConfiguracaoControleAcesso_RepetirTeste` | select | Não · Sim |
| ConfiguracaoControleAcesso.TotalTestesVivacidade | `ConfiguracaoControleAcesso.TotalTestesVivacidade` | text |  |
| Remover Registrar Ponto | `ConfiguracaoControleAcesso_RemoverBotaoRegistrar` | select | Não · Sim |
| Remover Registrar Ponto | `ConfiguracaoControleAcesso_RemoverBotaoPontos` | select | Não · Sim |
| Remover Registrar Ponto | `ConfiguracaoControleAcesso_RemoverBotaoJustificativa` | select | Não · Sim |
| Remover Reconhecimento Facial | `ConfiguracaoControleAcesso_RemoverBotaoReconhecimento` | select | Não · Sim |
| Remover Reconhecimento Facial | `ConfiguracaoControleAcesso_RemoverBotaoAssinatura` | select | Não · Sim |
| Remover Reconhecimento Facial | `ConfiguracaoControleAcesso_RemoverBotaoMensagens` | select | Não · Sim |
| **[Ponto Online]** | | | |
| Exibir Jornadas | `ExibirJornadaPontoOnline` | select | DEFINIDO POR COLABORADOR · ESCONDER PARA TODOS OS COLABORADORES · EXIBIR PARA TODOS OS COLABORADORES |

---

## Jornadas  (`/Jornadas/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## RelogioPonto  (`/RelogioPonto/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## CartaoPonto  (`/CartaoPonto/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Pesquisar · Exportar · Continuar · Confirmar

Filtros do grid:

- `ModeloImpressaoCartaoPonto` (select): Horas Agentes/Periodo · Cartão Ponto Lote
- `vigencia` (text)
- `idSupervisores` (select)
- `idContrato` (select)
- `idEmpresas` (select)
- `idModelo` (select)
- `ApenasComPonto` (select): NÃO · SIM
- `idColaboradores` (select)
- `TrazerDemitidos` (select): NÃO · SIM
- `idColaboradores` (select): Carregando ...
- `Inicio` (text)
- `Termino` (text)
- `Referencia` (text)
- `ExibirDetalhes` (select): SIM · NÃO
- `ExibirEventosCalculados` (select): SIM · NÃO
- `ExibirBancoHoras` (select): SIM · NÃO
- `ExibirEventos` (select): SIM · NÃO
- `ExibirMotivos` (select): SIM · NÃO
- `visualizacaoEscolta` (select): Patrimonial · Escolta
- `TipoFiltro` (select): Esteve no contrato · Terminou no contrato · Iniciou no contrato
- `CampoOrdenacao` (select): -- Selecione -- · Colaborador - Crescente · Colaborador - Decrescente
- `FragmentarPeriodo` (select): SIM · NÃO
- `ExibirLocal` (select): SIM · NÃO
- `Inicio` (text)
- `Termino` (text)


---

## ControlePonto  (`/ControlePonto/Index` · HTTP 200)

Botões da tela: Imprimir · Fechar · Buscar · Concluir · Continuar · Confirmar

Filtros do grid:

- `Dia` (text)
- `idContratos` (select)
- `idColaboradores` (select)
- `Status` (select)
- `Empresas` (select)


---

## CargaDispositivos  (`/CargaDispositivos/Index` · HTTP 200)

Botões da tela: Recarregar lista · Adicionar colaborador · Adicionar contrato · Remover Demitidos · Remover selecionados · Concluir · Fechar · Continuar · Confirmar


---

## TiposAfastamento  (`/TiposAfastamento/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## BeneficiosReajuste  (`/BeneficiosReajuste/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### Modal `/BeneficiosReajuste/Editar`

**Form** `fFiltro` → `/Contratos/Filtro` (2 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| Contrato: | `idContrato` | select |  |
| Contrato: | `idBeneficio` | select | -- Selecione -- |

---

## ColaboradorCracha  (`/ColaboradorCracha/Index` · HTTP 200)

Botões da tela: Salvar · Fechar · Concluir · Continuar · Confirmar


---

## RondaAlertas  (`/RondaAlertas/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


---

## UniformeEstoque  (`/UniformeEstoque/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### `/UniformeEstoque/Index` → HTTP None

### Modal `/UniformeEstoque/Filtro`

**Form** `fFiltro` → `/Uniformes/Filtro` (3 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| Descrição: | `Descricao` | text |  |
| Grupo: | `idGrupo` | select | -- Selecione -- |
| Grupo: | `Status` | select | -- Selecione -- · Abaixo do Minimo · Acima do Maximo · Minimo não Informado · Proximo do Minimo · Regular · Zerado |

### `/UniformeEstoque` → HTTP None

---

## Estoque  (`/Estoque/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### `/UniformeEstoque/Index` → HTTP None

---

## Fornecedores  (`/Fornecedores/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### Modal `/Fornecedores/Incluir?SubInclusao=False`

**Form** `-` → `/Fornecedores/Salvar` (14 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Razão Social: | `RazaoSocial` | text | maxlength=200 |
| Razão Social: | `Nome` | text | maxlength=200 |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `InscricaoNacional` | text |  |
| CEP: | `CEPPrincipal` | text |  |
| CEP: | `EnderecoPrincipal` | text |  |
| Número: | `NumeroPrincipal` | text |  |
| Número: | `BairroPrincipal` | text | maxlength=100 |
| Cidade: | `CidadePrincipal` | text | maxlength=100 |
| Cidade: | `EstadoPrincipal` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |
| Complemento: | `ComplementoPrincipal` | text | maxlength=100 |
| Complemento: | `Posto` | select | NÃO · SIM |

---

## Usuarios  (`/Usuarios/Index` · HTTP 200)

Botões da tela: Concluir · Fechar · Continuar · Confirmar


### Modal `/Usuarios/Incluir`

**Form** `-` → `/Usuarios/Salvar` (7 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Alterar` | hidden | `true` |
| Nome: | `Nome` | text | maxlength=100 |
| Login: | `Login` | text |  |
| Login: | `idGrupos` | select |  |
| Confirmar Senha: | `Password` | password |  |
| Confirmar Senha: | `Confirme` | password |  |

### Modal `/Usuarios/AlterarSenha`

**Form** `-` → `/Usuarios/AlterarSenha` (6 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `3` |
| _(oculto)_ | `Login` | hidden | `master` |
| _(oculto)_ | `Retorno` | hidden | `https://conectamais.dgxbrasil.` |
| Usuario: | `SenhaAtual` | password |  |
| Confirme Senha: | `Password` | password |  |
| Confirme Senha: | `CNovaSenha` | password |  |

---

## `/api/Settings/Parametros`

- `/api/Settings/Parametros` → HTTP 401: ``
- `/api/Settings/Parametros?nome=ModeloCracha` → HTTP 401: ``
- `/api/Settings/Parametros?nome=Ponto` → HTTP 401: ``
- `/api/Settings/Parametros?nome=Folha` → HTTP 401: ``
- `/api/Settings/Parametros?nome=Ferias` → HTTP 401: ``
- `/api/Settings/Parametros?nome=Beneficios` → HTTP 401: ``
- `/api/Settings/Parametros/Lista` → HTTP 405: ``
- `/api/Settings/Parametros/Todos` → HTTP 405: ``
