# DGX — DP/RH: modelo de dados lido dos formulários

**Fonte:** `GET /<Entidade>/Incluir` devolve o formulário do modal, com `<form action="/<Entidade>/Salvar">`.
Lido em 24/09/2026. Campo `hidden` = chave/estado que o formulário carrega sem mostrar.
Opções de `select` estão COMPLETAS — são a parametrização do sistema.

Padrão arquitetural: MVC .NET, um controller por entidade com `Index` (grid), `Incluir`/`Editar` (modal), `Salvar` (POST), `Lista` (grid parcial), `ParametrosGrid`. Multi-empresa por `idEmpresa` em toda tela.


## Cargos  (`/Cargos` → `/Cargos/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| Cargo: | `Cargo` | text |  |
| Abreviação: | `Abreviacao` | text | maxlength=7 |
| Abreviação: | `SufixoInicial` | text | maxlength=10 |
| Abreviação: | `SalarioBase` | text |  |
| Tipo de Serviço: | `TipoServico` | select | Administrativo · Escolta · Limpeza · Outros · Patrimonial |
| Tipo de Serviço: | `CBO` | text | maxlength=20 |
| Tipo de Serviço: | `CBORAIS` | text | maxlength=20 |
| Porte de Arma: | `PorteArma` | checkbox |  |
| _(oculto)_ | `PorteArma` | hidden | valor inicial `false` |

## Funções  (`/Funcoes` → `/Funcoes/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| Cód. Interno: | `CodigoInterno` | text |  |
| Cód. Interno: | `Nome` | text |  |
| Exige CNH | `ExigeCNH` | checkbox |  |
| _(oculto)_ | `ExigeCNH` | hidden | valor inicial `false` |
| Exige CNH | `ExigeCNV` | checkbox |  |
| _(oculto)_ | `ExigeCNV` | hidden | valor inicial `false` |

## Férias  (`/Ferias` → `/Ferias/Salvar`)

Seções: Dados Gerais

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `idAfastamento` | hidden | valor inicial `0` |
| _(oculto)_ | `idSolicitacao` | hidden | valor inicial `` |
| _(oculto)_ | `idContaPagar` | hidden | valor inicial `` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| _(oculto)_ | `DiasLicencaRemunerada` | hidden | valor inicial `` |
| _(oculto)_ | `SalarioMes` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiaMes` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiasFeriasMes` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiasAbonoMes` | hidden | valor inicial `` |
| _(oculto)_ | `SalarioHora` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiaMesSeg` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiasFeriasMesSeg` | hidden | valor inicial `` |
| _(oculto)_ | `ValorDiasAbonoMesSeg` | hidden | valor inicial `` |
| _(oculto)_ | `Departamento` | hidden | valor inicial `` |
| Colaborador:    Listar colaboradores demitidos | `chkdemissaof` | checkbox |  |
| Colaborador:    Listar colaboradores demitidos | `idColaborador` | select |  |
| Colaborador:    Listar colaboradores demitidos | `FeriasPerdidas` | select | NÃO · SIM |
| Colaborador:    Listar colaboradores demitidos | `GozoMenor` | select | NÃO · SIM |
| Início: | `Inicio` | text |  |
| Início: | `Termino` | text |  |
| Início: | `dInicioAquisitivo` | text | disabled= |
| _(oculto)_ | `InicioAquisitivo` | hidden | valor inicial `` |
| Início: | `dTerminoAquisitivo` | text | disabled= |
| _(oculto)_ | `TerminoAquisitivo` | hidden | valor inicial `` |
| Dias Perdidos por Falta: | `sDiasPerdidosFalta` | text |  |
| _(oculto)_ | `DiasPerdidosFalta` | hidden | valor inicial `0` |
| Dias Perdidos por Falta: | `DiasAbono` | text |  |
| Dias Perdidos por Falta: | `DiasNoPeriodo` | text | disabled=disabled |

## Afastamentos  (`/AgenteAfastamentos` → `/AgenteAfastamentos/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| idEmpregado | `idEmpregado` | select |  |
| Tipo de Afastamento: | `Tipo` | select | Aborto não criminoso · Acidente de trabalho · Aposentadoria por Invalidez · Cárcere · Cessão de Trabalhador · Doença · Exercício de mandato eleitoral · Exercício de mandato sindical · Investigação Interna · Licença maternidade - 120 dias · Licença maternidade - a partir de 120 dias até 180 dias · Licença paternidade · Licença sem Vencimentos · Novo afastamento em decorrência da mesma doença, dentro de 60 dias contados da cessação do afastamento anterior · Novo afastamento em decorrência do mesmo acidente de trabalho · Outros Motivos de afastamento temporário · Participação de curso ou programa de qualificação – Art. 476A da CLT · Prestação de Serviço Militar |
| Retorno Previsto: | `Afastamento` | text |  |
| Retorno Previsto: | `Previsto` | text |  |
| Retorno Previsto: | `Retorno` | text |  |
| Retorno Previsto: | `Beneficio` | text |  |

## TiposAfastamento  (`/TiposAfastamento`)

_Formulário não é modal clássico (HTTP 500) — provavelmente tela `/frontend/`._


## Sindicatos  (`/Sindicatos` → `/Sindicatos/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| Nome: | `Nome` | text |  |
| Nome: | `NomeReduzido` | text |  |
| Endereço: | `Endereco` | text |  |
| Contato: | `Contato` | text |  |
| Contato: | `Telefone` | text |  |
| Contato: | `Tipo` | select | LABORAL · PATRONAL |

## Eventos (rubricas de ponto/folha)  (`/Eventos` → `/Eventos/Salvar`)

Seções: Evento · Horas · Dias · Somatória · Remoção de cálculo · Exportação para folha · Comercial

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| Código: | `Codigo` | text |  |
| Código: | `Descricao` | text |  |
| Período: | `Periodo` | select | DIAS · HORAS · MÊS |
| Período: | `NaoVizualizarPonto` | select | -- SELECIONE -- · NÃO · SIM |
| Período: | `Vale` | select | -- SELECIONE -- · NÃO · SIM |
| Justificado: | `HoraExtra` | select | -- SELECIONE -- · NÃO · SIM |
| Justificado: | `Ausencia` | select | -- SELECIONE -- · NÃO · SIM |
| Tipo do Dia: | `TipoFalta` | select | Atividade Externa · Crédito · Dia Normal · Falta Justificada · Falta Não Justificada · Folga |
| Tipo do Dia: | `DescontarBeneficio` | select | -- SELECIONE -- · NÃO · SIM |
| Tipo do Dia: | `ListarTipoBeneficioDescontado` | select | Assistência · Assistência Médica · Assistência Odontológica · Cartão de Crédito · Cesta Básica · Perfil Securitário · PLR · Prêmio · Seguro de Vida · SESMT - Segurança e Medicina do Trabalho · Vale Refeição · Vale Transporte |
| Somar ao Evento: | `Credito` | select | -- SELECIONE -- · SUBTRAIR · SOMAR |
| Somar ao Evento: | `SomarAoEvento` | select | NÃO · Hora Trabalhada · Hora Extra · Hora Extra 100% · Hora Noturna · Hora Noturna Reduzida · Atraso · Adicional no feriado · Intrajornada |
| Somar ao Evento: | `SomarAoPonto` | select | -- SELECIONE -- · NÃO · SIM |
| Considerar Descanso: | `ConsiderarDescanso` | select | -- SELECIONE -- · NÃO · SIM |
| Considerar Descanso: | `BancoHoras` | select | NÃO · SUBTRAIR · SOMAR |
| Considerar Descanso: | `ExportarEmFolga` | select | -- SELECIONE -- · NÃO · SIM |
| Ponto: | `RemoverPontoCalculado` | select | -- SELECIONE -- · NÃO · SIM |
| Ponto: | `RemoverDiaria` | select | -- SELECIONE -- · NÃO · SIM |
| Código Exportação: | `ExportarEvento` | select | -- SELECIONE -- · NÃO · SIM |
| Código Exportação: | `CodigoAuxiliar` | text |  |
| Comercial: | `Comercial` | select | -- SELECIONE -- · NÃO · SIM |
| Comercial: | `PorcentagemValor` | select | PORCENTAGEM · VALOR |
| Comercial: | `SalarioMinimo` | select | SALÁRIO BASE · SALÁRIO MÍNIMO |
| Comercial: | `Razao` | text |  |
| Comercial: | `RazaoNoturna` | text |  |

## Advertências  (`/AgenteAdvertencias` → `/AgenteAdvertencias/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| idEmpregado | `idEmpregado` | select |  |
| Motivo: | `TipoFatoRelevante` | select | -- Selecione -- · Advertência · Outros |
| Motivo: | `Discriminacao` | text | maxlength=500 |
| Motivo: | `Data` | text |  |
| Descrição: | `Descricao` | textarea | maxlength=5000 |

## Suspensões  (`/EmpregadosSuspensoes` → `/EmpregadosSuspensoes/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| Ocorrencia | `idEmpregado` | select |  |
| Ocorrencia | `TipoFatoRelevante` | select | Suspensão |
| Motivo: | `Discriminacao` | text | maxlength=500 |
| Motivo: | `Data` | text |  |
| Motivo: | `DataRetorno` | text |  |
| Detalhes: | `Descricao` | textarea | maxlength=5000 |

## Cursos do colaborador  (`/AgenteCursos` → `/AgenteCursos/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `reciclavel` | hidden | valor inicial `False` |
| idEmpregado | `idEmpregado` | select | -- Selecione -- |
| idCursosCertificados | `idCursosCertificados` | select | -- Selecione -- |
| Curso: | `Curso` | text | readonly= |
| Curso: | `Local` | text |  |
| Conclusão: | `Conclusao` | text |  |
| Conclusão: | `Validade` | text |  |

## Tipos de Curso/Certificado  (`/CursosCertificados` → `/CursosCertificados/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| Curso | `Curso` | text | maxlength=200 |
| Reciclável: | `Reciclavel` | select | Não · Sim |
| Reciclável: | `DiasValidade` | select | 1 Ano · 2 Anos · 3 Anos · 4 Anos · 5 Anos · 6 Meses · Não Expira |
| Reciclável: | `Atuacao` | select | Sim · Não |

## Tipos de Benefício  (`/TiposBeneficios` → `/TiposBeneficios/Salvar`)

Seções: Tipo de Benefício · Desconto · Diário · Mensal · Desconto Meio Período (Mensal) · Descontos por Falta (Mensal)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| Mensal: | `Nome` | text | maxlength=100 |
| Mensal: | `Mensal` | select | NÃO · SIM |
| Prevalecer Individual: | `PrevalecerIndividual` | select | NÃO · SIM |
| Prevalecer Individual: | `TipoPrimitivo` | select | -- Selecione -- · Assistência · Assistência Médica · Assistência Odontológica · Cartão de Crédito · Cesta Básica · Perfil Securitário · PLR · Prêmio · Seguro de Vida · SESMT - Segurança e Medicina do Trabalho · Vale Refeição · Vale Transporte |
| Tipo: | `TipoDesconto` | select | Fixo · Nenhum · Percentual do Valor Sobre Falta · Percentual Sobre Salário · Percentual Sobre Valor · Unidade · Valor Por Dia |
| Tipo: | `CoeficienteDesconto` | text | maxlength=18 |
| Evento: | `idEventoDebito` | select | -- Selecione -- · 9005 - ADICIONAL NOTURNO · 9000 - DIAS SALARIO · 9001 - DSR FALTA · 9007 - DSR SOBRE ADICIONAL NOTURNO · 9008 - DSR SOBRE HORA EXTRA · 9006 - HORA NOTURNA REDUZIDA |
| Evento: | `DescontoDiretoDinheiro` | select | NÃO · SIM |
| Integração com Ponto: | `ListaTiposCalculoPonto` | select | Café da Manhã · Descanso · Diária · Horas em Missão · Mínimo de Horas · Missão Rodoviária · Reembolso Jornada · Reembolso Por Dia |
| Integração com Ponto: | `DescontoPorSaldo` | select | NÃO · SIM |
| Faltas: | `Faltas` | text |  |
| Faltas: | `FaltasJustificadas` | text |  |
| Faltas: | `DiasTrabalhadosMes` | text |  |
| Meses Afastastados: | `MesesAfastamentoPermitido` | text |  |
| Meses Afastastados: | `RemoverFeriasDiasMes` | select | NÃO · SIM |
| Meses Afastastados: | `RemoverAfastados` | select | NÃO · SIM |
| Meses Afastastados: | `RemoverAtrasados` | select | NÃO · SIM |
| Tipo: | `TipoDescontoMeioPeriodo` | select | Nenhum · Valor · Percentual |
| Tipo: | `hHorasMeioPeriodo` | text |  |
| Tipo: | `DescontoMeioPeriodo` | text |  |

## Benefício individual  (`/EmpregadoBeneficios` → `/EmpregadoBeneficios/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Manual` | hidden | valor inicial `True` |
| idColaborador | `idColaborador` | select |  |
| idBeneficio | `idBeneficio` | select | -- Selecione -- |
| Linha: | `idLinha` | select | -- Selecione -- |
| Anular Outras Fontes: | `Quantidade` | text |  |
| Anular Outras Fontes: | `ValorUnitario` | text | maxlength=18 |
| Anular Outras Fontes: | `Inclusao` | text |  |
| Anular Outras Fontes: | `AnularOutrasFontes` | select | NÃO · SIM |

## Dependentes  (`/AgenteDependentes` → `/AgenteDependentes/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| idEmpregado | `idEmpregado` | select |  |
| Nome | `Nome` | text | maxlength=200 |
| DataNascimento | `DataNascimento` | text |  |
| Deficiente: | `Sexo` | select | -- Selecione -- · Feminino · Masculino |
| Deficiente: | `Deficiente` | select | Não · Sim |
| Deficiente: | `TipoDeficiencia` | text | maxlength=50 |
| Deficiente: | `GrauDependente` | select | -- Selecione -- · Bisneto/a · Cônjuge · Filho/a · Genro/Nora · Irmã(o) · Neto/a · Pai/Mae · Sogro/a |
| RG: | `RG` | text | maxlength=20 |
| RG: | `CPF` | text | maxlength=20 |
| RG: | `GrauInstrucao` | select | -- Selecione -- · 5º ano completo do Ensino Fundamental · Analfabeto · Até o 5º ano incompleto do Ensino Fundamental · Do 6º ao 9º ano do Ensino Fundamental incompleto · Doutorado completo · Educação Superior completa · Educação Superior incompleta · Ensino Fundamental Completo · Ensino Médio completo · Ensino Médio incompleto · Mestrado completo |

## Linhas de VT (itinerários)  (`/OperadoraItinerarios` → `/OperadoraItinerarios/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| Codigo | `Codigo` | text |  |
| Nome | `Nome` | text | maxlength=200 |
| Operadora: | `idOperadora` | select | Carregando... |
| Tipo: | `Valor` | text | maxlength=18 |
| Tipo: | `TipoPasse` | select | -- Selecione-- · Cartao · Papel |
| Tipo: | `CodigoAuxiliar` | text |  |
| Tipo: | `CodigoSPVale` | text |  |
| Linha Mensal: | `idOperadoraMensal` | select | Carregando... |
| Mensal: | `Mensal` | checkbox |  |

## BeneficiosReajuste  (`/BeneficiosReajuste`)

_Formulário não é modal clássico (HTTP 500) — provavelmente tela `/frontend/`._


## ColaboradorCracha  (`/ColaboradorCracha`)

_Formulário não é modal clássico (HTTP 500) — provavelmente tela `/frontend/`._


## Entregas de Benefícios (lote)  (`/EntregasBeneficios` → `/EntregasBeneficios/Salvar`)

| Campo | Nome interno | Tipo | Opções / regras |
|---|---|---|---|
| _(oculto)_ | `id` | hidden | valor inicial `0` |
| _(oculto)_ | `Status` | hidden | valor inicial `0` |
| idBeneficio | `idBeneficio` | select | -- Selecione -- |
| Referencia | `Referencia` | text |  |
| Início Período: | `PrevisaoInicio` | text |  |
| Início Período: | `PrevisaoFim` | text |  |
| Entrega anterior 1: | `idEntregaAnterior` | select |  |
| Entrega anterior 2: | `idEntregaAnterior2` | select |  |
| Apuração: | `idApontamento` | select | Manual |
| Apuração: | `ApuracaoInicio` | text |  |
| Apuração: | `ApuracaoFim` | text |  |
