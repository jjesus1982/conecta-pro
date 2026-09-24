# DGX — API REST real: combos, filtros e o que cada resposta carrega

Lido em 24/09/2026 com Bearer. Padrão: `GET .../combo` (opções de dropdown), `POST .../filtro` (busca paginada — devolve o MODELO da entidade), `GET/PUT .../{id}`. A instância está vazia (0 colaboradores), então as listas vêm `[]`; o que importa é o **formato** e as **opções**.


## `GET /api/RH/eventos/combo` → HTTP 200

Forma: lista n=6 keys=['id', 'nome', 'complemento', 'cpf', 'chaveEmpresa']

```json
[{"id":1,"nome":"9000 - DIAS SALARIO","complemento":null,"cpf":null,"chaveEmpresa":null},{"id":2,"nome":"9001 - DSR FALTA","complemento":null,"cpf":null,"chaveEmpresa":null},{"id":3,"nome":"9005 - ADICIONAL NOTURNO","complemento":null,"cpf":null,"chaveEmpresa":null},{"id":4,"nome":"9006 - HORA NOTURNA REDUZIDA","complemento":null,"cpf":null,"chaveEmpresa":null},{"id":5,"nome":"9007 - DSR SOBRE ADICIONAL NOTURNO","complemento":null,"cpf":null,"chaveEmpresa":null},{"id":6,"nome":"9008 - DSR SOBRE HORA EXTRA","complemento":null,"cpf":null,"chaveEmpresa":null}]
```

## `GET /api/ControlePonto/Escalas/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/comercial/contratos/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Comercial/Clientes/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Comercial/Fornecedores/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/RH/Colaboradores/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/RH/Prestadores/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/RH/Pensionistas/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Financeiro/PlanoContas/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Financeiro/CentrosCusto/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/financeiro/contasBancarias/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Comercial/EmpresaEmitentes/combo` → HTTP 200

Forma: lista n=1 keys=['id', 'nome', 'razaoSocial', 'cnpj', 'nomeDiretor', 'emailDiretor', 'inscricaoEstadual', 'inscricaoMunicipal', 'cep', 'endereco', 'numero', 'bairro', 'cidade', 'estado', 'complemento', 'logo', 'fone', 'email', 'rps', 'percentualTributacaoNota']

```json
[{"id":1,"nome":"CONECTAMAIS PATRIMONIAL","razaoSocial":"CONECTAMAIS PATRIMONIAL LTDA","cnpj":"66.014.833/0001-10","nomeDiretor":null,"emailDiretor":null,"inscricaoEstadual":"","inscricaoMunicipal":null,"cep":"69055-630","endereco":"RUA VICTOR HUGHES","numero":"19","bairro":"PARQUE 10 DE NOVEMBRO","cidade":"MANAUS","estado":"AM","complemento":"CONJUNTO CASTELO BRA","logo":"66014833000110.jpg","fone":"","email":null,"rps":0,"percentualTributacaoNota":0,"observacao":null,"status":0,"optanteSimplesNacional":false,"fonteTributaria":null,"informacoesNotaServico":null,"retencaoISS":false,"vencimentoISS":false,"gerarCredito":false,"municipioTributacao":false,"idInformacaoFiscal":null,"serie":null,"
```

## `GET /api/comercial/pessoaPostos/combo` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Comercial/Representantes` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/Comercial/Pessoas/combo?chaveComposta=true&tipoPessoas=Departamento&listarGrupo=true` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/prontoAtendimento/eventosProntaResposta` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/escoltas/rotas` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/mapas/Localizacoes` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/rh/demissoes` → HTTP 405


## `GET /api/rh/empregadoHistoricoContatos` → HTTP 405


## `GET /api/rh/colaboradores` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `GET /api/RH/eventos` → HTTP 404


## `GET /api/rh/eventos/1` → HTTP 200

Forma: obj keys=['id', 'excluido', 'evento', 'descricao', 'finalidade', 'suspensao', 'tipoDesconto', 'codigoAuxiliar', 'status', 'observacoes', 'digiexpress', 'codigo', 'credito', 'periodo', 'porcentagemValor']

```json
{"id":1,"excluido":false,"evento":0,"descricao":"DIAS SALARIO","finalidade":null,"suspensao":false,"tipoDesconto":null,"codigoAuxiliar":null,"status":0,"observacoes":null,"digiexpress":false,"codigo":9000,"credito":false,"periodo":0,"porcentagemValor":false,"fgts":false,"inss":false,"irrf":false,"rendimentoBruto":false,"decimoTerceiro":false,"periculosidade":false,"holerith":false,"razao":0,"razaoNoturna":0,"dsr":false,"horaExtra":false,"mediaDecimoTerceiro":false,"salarioMinimo":false,"comercial":false,"descontarBeneficio":false,"tipoFalta":0,"exportarEvento":false,"somarAoPonto":false,"removerPontoCalculado":false,"somarAoEvento":null,"naoVizualizarPonto":false,"removerDiaria":false,"vale"
```

## `GET /api/financeiro/schemas/contasPagar` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `GET /api/financeiro/schemas/contasReceber` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `GET /api/financeiro/schemas/ContasPagar` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `GET /api/financeiro/schemas/lancamentos` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `GET /api/financeiro/schemas` → HTTP 405


## `GET /api/financeiro/conciliacoes` → HTTP 405


## `GET /api/storage/files` → HTTP 405


## `GET /api/rh/schemas/colaboradores` → HTTP 404


## `GET /api/RH/Colaboradores/schema` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `GET /api/controlePonto/planejamentos/filtro` → HTTP 405


## `POST /api/rh/colaboradores/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'total']

```json
{"lista":[],"total":0}
```

## `POST /api/rh/alteracoesSalario/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":null,"total":0}
```

## `POST /api/rh/SomatoriaContatos/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":null,"total":0}
```

## `POST /api/financeiro/contasPagar/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":[{"key":0,"value":0},{"key":1,"value":0},{"key":2,"value":0},{"key":3,"value":0},{"key":4,"value":0}],"total":0}
```

## `POST /api/financeiro/contasReceber/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":[{"key":0,"value":0},{"key":1,"value":0},{"key":2,"value":0},{"key":3,"value":0},{"key":4,"value":0},{"key":5,"value":0}],"total":0}
```

## `POST /api/financeiro/contasPagar/rateio/filtro {}` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `POST /api/controlePonto/planejamentos/filtro {}` → HTTP 400

Forma: obj keys=['errors', 'type', 'title', 'status', 'traceId']


## `POST /api/prontoAtendimento/prontaRespostas/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":[],"total":0}
```

## `POST /api/prontoAtendimento/tabelaProntaRespostaTolerancias/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":null,"total":0}
```

## `POST /api/comercial/pessoaPostos/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'total', 'legendas']

```json
{"lista":[],"total":0,"legendas":[]}
```

## `POST /api/RH/eventos/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[{"id":6,"excluido":false,"evento":0,"descricao":"DSR SOBRE HORA EXTRA","finalidade":null,"suspensao":false,"tipoDesconto":null,"codigoAuxiliar":null,"status":0,"observacoes":null,"digiexpress":false,"codigo":9008,"credito":true,"periodo":1,"porcentagemValor":false,"fgts":false,"inss":false,"irrf":false,"rendimentoBruto":false,"decimoTerceiro":false,"periculosidade":false,"holerith":false,"razao":0,"razaoNoturna":0,"dsr":false,"horaExtra":false,"mediaDecimoTerceiro":false,"salarioMinimo":false,"comercial":false,"descontarBeneficio":false,"tipoFalta":0,"exportarEvento":false,"somarAoPonto":false,"removerPontoCalculado":false,"somarAoEvento":null,"naoVizualizarPonto":false,"removerDia
```

## `POST /api/comercial/contratos/filtro {}` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":[],"total":0}
```

## `POST /api/Comercial/Clientes/filtro {}` → HTTP 200

Forma: lista n=0 keys=[]

```json
[]
```

## `POST /api/rh/colaboradores/filtro pag` → HTTP 200

Forma: obj keys=['lista', 'total']

```json
{"lista":[],"total":0}
```

## `POST /api/financeiro/contasPagar/filtro pag` → HTTP 200

Forma: obj keys=['lista', 'legendas', 'total']

```json
{"lista":[],"legendas":[{"key":0,"value":0},{"key":1,"value":0},{"key":2,"value":0},{"key":3,"value":0},{"key":4,"value":0}],"total":0}
```
