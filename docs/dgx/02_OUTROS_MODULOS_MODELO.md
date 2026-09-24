# DGX — demais módulos: modelo de dados dos formulários

**Fonte:** `GET /<Entidade>/Incluir` (modal). Lido em 24/09/2026. Entidades com HTTP 500 usam telas `/frontend/` (SPA) — mapeadas à parte.


---

# Apontamentos (Ponto)


## Escalas  (`/Escalas`)


**Form** `-` → `/Escalas/Salvar` (6 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `hCargaMensal` | hidden | `` |
| _(oculto)_ | `hDescansoJornada` | hidden | `` |
| idModelo | `idModelo` | select | -- Selecione -- |
| Codigo | `Codigo` | text | maxlength=9 |
| Nome | `Nome` | text | maxlength=200 |

## ModelosEscalas  (`/ModelosEscalas`)


**Form** `-` → `/ModelosEscalas/Salvar` (7 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Nome | `Nome` | text | maxlength=200 |
| Descricao | `Descricao` | text | maxlength=200 |
| DiasTrabalho | `DiasTrabalho` | text | maxlength=2 |
| DiasFolga | `DiasFolga` | text | maxlength=2 |
| hHorasDia | `hHorasDia` | text |  |
| DiasMes | `DiasMes` | text |  |

## Jornadas  (`/Jornadas`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## RelogioPonto  (`/RelogioPonto`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Ausencias  (`/Ausencias`)


**Form** `-` → `/Ausencias/Salvar` (12 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| idColaborador | `idColaborador` | select |  |
| idEvento | `idEvento` | select | -- Selecione -- |
| Dias: | `Inicio` | text |  |
| Dias: | `DiasTotal` | text | maxlength=6 |
| Dias: | `Termino` | text |  |
| Dias: | `Tratativa` | select | Não · Sim |
| Data: | `Data` | text |  |
| Data: | `Referencia` | text |  |
| Data: | `Tratativa` | select | Não · Sim |
| CID | `CID` | text | maxlength=20 |
| Observações: | `Observacoes` | textarea | maxlength=100000 |

## Apontamentos  (`/Apontamentos`)


**Form** `-` → `/Apontamentos/Salvar` (4 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Referencia | `Referencia` | text |  |
| Inicio | `Inicio` | text |  |
| Termino | `Termino` | text |  |

## CartaoPonto  (`/CartaoPonto`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## ControlePonto  (`/ControlePonto`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## CargaDispositivos  (`/CargaDispositivos`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

---

# Operacional


## Postos  (`/Postos`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Movimentacoes  (`/Movimentacoes`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## GridPlanejamento  (`/GridPlanejamento`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Avisos  (`/Avisos`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## ContratoSetores  (`/ContratoSetores`)


**Form** `-` → `/ContratoSetores/Salvar` (4 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Contrato: | `idContrato` | select |  |
| Código: | `Codigo` | text |  |
| Código: | `Nome` | text |  |

## SetorChamados  (`/SetorChamados`)


**Form** `-` → `/SetorChamados/Salvar` (9 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `idUsuarioAutor` | hidden | `` |
| _(oculto)_ | `Status` | hidden | `0` |
| _(oculto)_ | `Excluido` | hidden | `False` |
| Título: | `Titulo` | text |  |
| Título: | `Solicitante` | text |  |
| Contrato: | `combo-contratos` | select | -- Selecione -- |
| Contrato: | `combo-setores` | select | -- Selecione -- |
| Descrição: | `Descricao` | textarea |  |

## RondaLojas  (`/RondaLojas`)


**Form** `-` → `/RondaLojas/Salvar` (23 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Nº VD: | `Codigo` | text |  |
| Nº VD: | `Nome` | text |  |
| Status | `status` | select | Ativo · Inativo |
| Status | `idCliente` | select | -- Selecione -- |
| CNPJ da loja: | `CNPJ` | text |  |
| CNPJ da loja: | `InscricaoEstadual` | text |  |
| CNPJ da loja: | `InscricaoMunicipal` | text |  |
| Id Sistema do Cliente | `idSistemaCliente` | text |  |
| Id Sistema do Cliente | `idSistemaCliente2` | text |  |
| Telefone 01: | `Telefone` | text |  |
| Telefone 01: | `Telefone2` | text |  |
| Telefone 01: | `Radio` | text |  |
| Região: | `LojaRegiao` | select | -- Selecione -- |
| Região: | `idSetor` | select | -- Selecione -- |
| CEP: | `CEP` | text |  |
| CEP: | `Endereco` | text |  |
| Número: | `Numero` | text |  |
| Número: | `Bairro` | text |  |
| Cidade: | `Cidade` | text |  |
| Cidade: | `Estado` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |
| Complemento: | `Complemento` | text |  |
| Complemento: | `CodigoIBGEMunicipio` | text |  |

## ModelosRondas  (`/ModelosRondas`)


**Form** `-` → `/ModelosRondas/Salvar` (3 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `` |
| Nome: | `Nome` | text | maxlength=200 |
| Nome: | `idCliente` | select |  |

## RondaAlertas  (`/RondaAlertas`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

---

# Comercial


## Clientes  (`/Clientes`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Contratos  (`/Contratos`)


**Form** `-` → `/Contratos/Salvar` (14 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `Intermitente` | hidden | `false` |
| Apenas Ativos: | `apenasAtivos` | select | Sim · Não |
| Apenas Ativos: | `autocompleteCliente` | text |  |
| _(oculto)_ | `idCliente` | hidden | `` |
| Descrição do Contrato: | `Nome` | text |  |
| Data: | `Data` | text |  |
| Data: | `Inicio` | text |  |
| Data: | `Termino` | text |  |
| _(oculto)_ | `NumeroContrato` | hidden | `1` |
| Nº Contrato: | `Segmento` | select | -- SELECIONE -- · ESCOLTA ARMADA · LIMPEZA · MONITORAMENTO · OUTROS SERVIÇOS · PORTARIA · TECNOLOGIA · VIGILÂNCIA |
| Nº Contrato: | `TipoCalculo` | select | --SELECIONE-- · POR MONTANTE · POR HORA |
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `4` |
| _(oculto)_ | `PercentualEncargos` | hidden | `77,74` |

## PessoaPostos  (`/PessoaPostos`)


**Form** `-` → `/PessoaPostos/Salvar` (14 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `idPessoa` | hidden | `0` |
| Código / Remota: | `codigo` | text | maxlength=20 |
| Código / Remota: | `Nome` | text | maxlength=200 |
| CEP: | `Cep` | text |  |
| CEP: | `Endereco` | text | maxlength=200 |
| Número: | `Numero` | text | maxlength=20 |
| Número: | `Bairro` | text | maxlength=100 |
| Latitude: | `Latitude` | text |  |
| Latitude: | `Longitude` | text |  |
| Latitude: | `Raio` | text |  |
| Cidade: | `Cidade` | text | maxlength=100 |
| Cidade: | `Estado` | select | AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |
| Complemento: | `Complemento` | text | maxlength=100 |

## FontesPagadoras  (`/FontesPagadoras`)


**Form** `-` → `/FontesPagadoras/Salvar` (7 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `FontePagadora` | hidden | `True` |
| Razão Social: | `RazaoSocial` | text | maxlength=200 |
| Nome Fantasia: | `Nome` | text | maxlength=300 |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `PessoaJuridica` | radio |  |
| Tipo: | `InscricaoNacional` | text |  |

---

# SESMT


## SaudeOcupacional  (`/SaudeOcupacional`)


**Form** `-` → `/SaudeOcupacional/Salvar` (10 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `Inclusao` | hidden | `23/09/2026 23:54:06` |
| _(oculto)_ | `Status` | hidden | `0` |
| _(oculto)_ | `id` | hidden | `0` |
| Data | `Data` | text |  |
| VencimentoASO | `VencimentoASO` | text |  |
| Entregue: | `Tipo` | select | -- Selecione -- · Admissional · Demissional · Monitoração pontual, Nenhuma Anterior · Mudança de função · Periódico - conforme PCMSO · Retorno ao trabalho |
| Entregue: | `Entregue` | select | NÃO · SIM |
| Resultado | `Resultado` | select | -- Selecione -- · Apto · Apto com restrições · Inapto |
| idMedico | `idMedico` | select |  |
| Funcionários - Somente Demitidos: | `selecionaAgente` | select |  |

## Medicos  (`/Medicos`)


**Form** `-` → `/Medicos/Salvar` (6 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `0` |
| Nome: | `Nome` | text |  |
| Nome: | `CRM` | text | maxlength=8 |
| Telefone: | `Telefone` | text |  |
| Telefone: | `Estado` | select | -- Selecione -- · AC · AL · AM · AP · BA · CE · DF · ES · GO · MA · MG · MS · MT · PA · PB · PE · PI · PR · RJ · RN · RO · RR · RS · SC · SE · SP · TO |

## Exames  (`/Exames`)


**Form** `-` → `/Exames/Salvar` (4 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `validadeEdit` | hidden | `` |
| VALIDADE: | `Validade` | select | -- Selecione -- · 3 Meses · 6 Meses · 1 Ano |
| VALIDADE: | `Descricao` | text |  |

---

# Suprimentos


## Uniformes  (`/Uniformes`)


**Form** `-` → `/Uniformes/Salvar` (5 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `0` |
| Codigo: | `Codigo` | text |  |
| Codigo: | `idGrupo` | select | -- Selecione -- |
| Descrição: | `Descricao` | text |  |

## UniformesEntregas  (`/UniformesEntregas`)


**Form** `-` → `/UniformesEntregas/Salvar` (9 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `idColaborador` | hidden | `` |
| Colaborador: | `Solicitacao` | text |  |
| Admissão: | `Admissao` | text | disabled=disabled |
| Admissão: | `Cargo` | text | disabled=disabled |
| Contrato: | `Contrato` | text | disabled=disabled |
| _(oculto)_ | `idContrato` | hidden | `` |
| Contrato: | `Devolucao` | checkbox |  |
| _(oculto)_ | `Devolucao` | hidden | `false` |

## KitUniformes  (`/KitUniformes`)


**Form** `-` → `/KitUniformes/Salvar` (3 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Codigo` | hidden | `7` |
| Codigo: | `Nome` | text |  |

## UniformeEstoque  (`/UniformeEstoque`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Armamentos  (`/Armamentos`)


**Form** `-` → `/Armamentos/Salvar` (11 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `0` |
| Nº do Registro: | `Exclusividade` | select | GERAL · ESCOLTA · PATRIMONIAL |
| Nº do Registro: | `Registro` | text | maxlength=20 |
| Nº do Registro: | `Numero` | text | maxlength=20 |
| Nº do Registro: | `Sinarm` | text | maxlength=20 |
| Marca: | `Marca` | text | maxlength=30 |
| Marca: | `Especie` | text | maxlength=20 |
| Marca: | `Calibre` | text | maxlength=20 |
| Marca: | `Validade` | text |  |
| Identificação: | `Prefixo` | text | maxlength=50 |

## Coletes  (`/Coletes`)


**Form** `-` → `/Coletes/Salvar` (16 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Exclusividade: | `Exclusividade` | select | GERAL · ESCOLTA · PATRIMONIAL |
| Exclusividade: | `Marca` | text | maxlength=200 |
| Exclusividade: | `Protecao` | text | maxlength=10 |
| Exclusividade: | `Patrimonio` | text | maxlength=50 |
| Lote: | `Lote` | text | maxlength=50 |
| Lote: | `Modelo` | text | maxlength=100 |
| Lote: | `DataFabricacao` | text |  |
| Lote: | `CA` | text | maxlength=30 |
| Numeração: | `Numeracao` | text | maxlength=50 |
| Numeração: | `Tamanho` | select | P · M · G · GG · XG |
| Numeração: | `Validade` | text |  |
| Numeração: | `Status` | select | DISPONÍVEL · EM MISSÃO · INDISPONÍVEL · DESTRUÍDO |
| Numeração: | `Velada` | select | Não · Sim |
| Identificação: | `Prefixo` | text | maxlength=50 |
| Observações: | `Observacoes` | text | maxlength=500 |

## Materiais  (`/Materiais`)


**Form** `-` → `/Materiais/Salvar` (8 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Codigo: | `Codigo` | text |  |
| Codigo: | `Descricao` | text |  |
| Minimo: | `Minimo` | text |  |
| Minimo: | `Maximo` | text |  |
| Unidade: | `Unidade` | select | % · CT · CX · KG · M · m2 · m3 · ML · PC · T · UN |
| Unidade: | `Origem` | select | Importado · Nacional |
| Unidade: | `idGrupo` | select | -- Selecione -- |

## Estoque  (`/Estoque`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Fornecedores  (`/Fornecedores`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

---

# Faturamento


## Faturas  (`/Faturas`)


**Form** `-` → `/Faturas/Salvar` (16 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Nota Fiscal: | `limitNota` | text |  |
| Nota Fiscal: | `idNotaFiscal` | select | -- Selecione -- |
| Clientes: | `comboClientes` | text |  |
| _(oculto)_ | `idCliente` | hidden | `` |
| Emitente: | `idEmissor` | select | CONECTAMAIS PATRIMONIAL |
| _(oculto)_ | `idContaBancaria` | hidden | `` |
| Início Período: | `InicioPeriodo` | text |  |
| Início Período: | `TerminoPeriodo` | text |  |
| Início Período: | `Vencimento` | text |  |
| Nº Pedido: | `NumeroPedido` | text |  |
| Nº Pedido: | `Observacoes` | text |  |
| Descrição Avulsa: | `DiscriminacaoPadraoAvulso` | text |  |
| Descrição Avulsa: | `ValorUnitarioAvulso` | text |  |
| Descrição Padrão: | `idFaturaDiscriminacaoPadrao` | select | -- Selecione -- |
| Valor: | `ValorUnitario` | text |  |

## NotasServico  (`/NotasServico`)


**Form** `-` → `/NotasServico/Salvar` (10 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Inclusao` | hidden | `23/09/2026 23:54:24` |
| _(oculto)_ | `Competencia` | hidden | `` |
| _(oculto)_ | `idNotaServicoSubstituida` | hidden | `` |
| Código Motivo Substituição: | `CodigoMotivoSubstituicao` | select |  |
| Motivo Substituição: | `MotivoSubstituicao` | textarea |  |
| Tipo: | `TipoNotaServico` | select | -- SELECIONE -- · AVULSA · ESCOLTA / PRONTA RESPOSTA · SERVIÇOS |
| Tipo: | `idCliente` | select |  |
| Emissor: | `idEmitente` | select | -- SELECIONE -- · CONECTAMAIS PATRIMONIAL |
| Emissor: | `Emissao` | text |  |

## Servicos  (`/Servicos`)


**Form** `-` → `/Servicos/Salvar` (14 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Nome: | `Descricao` | text | maxlength=200 |
| Tributação do Municipio: | `CodigoTributacaoMunicipio` | text | maxlength=10 |
| Tributação do Municipio: | `ItemListaServico` | text | maxlength=10 |
| Tributação do Municipio: | `CNAE` | text | maxlength=9 |
| Abater Desc. Val.: | `AbaterDescontoValorServico` | select | Não · Sim |
| Abater Desc. Val.: | `AdicionarAdicionalValorServico` | select | Não · Sim |
| NBS: | `NBS` | text | maxlength=9 |
| NBS: | `CST` | text | maxlength=3 |
| Cod. Classificação Tributaria: | `CodigoClassificacaoTributaria` | text | maxlength=6 |
| Cod. Classificação Tributaria: | `CodigoIndicadorOperacao` | text | maxlength=6 |
| CST PIS: | `CSTPIS` | text | maxlength=2 |
| CST PIS: | `CSTCOFINS` | text | maxlength=2 |
| Incidência do IBS: | `IncidenciaIBS` | select | -- SELECIONE -- · Município do prestador · Município de prestação do serviço · Município do tomador |

## CFOP  (`/CFOP`)


**Form** `-` → `/CFOP/Salvar` (3 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| Código: | `Codigo` | text |  |
| Código: | `Operacao` | text |  |

## PessoaRecibos  (`/PessoaRecibos`)


**Form** `-` → `/PessoaRecibos/Salvar` (8 campos)

| Campo | Interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | `0` |
| _(oculto)_ | `Status` | hidden | `0` |
| _(oculto)_ | `DataEmissao` | hidden | `23/09/2026 23:54:31` |
| Cliente: | `idPessoa` | select |  |
| Cliente: | `idCFOP` | select | -- Selecione -- |
| Empresa Emitentes: | `idEmitente` | select | --Selecione-- · CONECTAMAIS PATRIMONIAL |
| Emissao: | `Data` | text | disabled=disabled |
| Emissao: | `DataPagamento` | text |  |

---

# Financeiro


## ContasPagar  (`/ContasPagar`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## ContasReceber  (`/ContasReceber`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## ContasBancarias  (`/ContasBancarias`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## PlanoContas  (`/PlanoContas`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## CentrosCusto  (`/CentrosCusto`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## FormasPagamento  (`/FormasPagamento`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## CondicoesPagamento  (`/CondicoesPagamento`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## TransferenciasBancarias  (`/TransferenciasBancarias`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

---

# Configurações


## Usuarios  (`/Usuarios`)


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

## Empresas  (`/Empresas`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._

## Configuracoes  (`/Configuracoes`)

_Sem modal `Incluir` (HTTP 500) — tela `/frontend/` ou cadastro por outra rota._
