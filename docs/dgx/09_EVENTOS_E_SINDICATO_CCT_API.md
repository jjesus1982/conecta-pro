# DGX — Eventos (modelo completo) e a estrutura Sindicato/CCT na API

Lido em 24/09/2026 com Bearer.

## Os 6 eventos semeados — modelo completo (`POST /api/RH/eventos/filtro`)

| id | excluido | evento | descricao | finalidade | suspensao | tipoDesconto | codigoAuxiliar | status | observacoes | digiexpress | codigo | credito | periodo | porcentagemValor | fgts | inss | irrf | rendimentoBruto | decimoTerceiro | periculosidade | holerith | razao | razaoNoturna | dsr | horaExtra | mediaDecimoTerceiro | salarioMinimo | comercial | descontarBeneficio | tipoFalta | exportarEvento | somarAoPonto | removerPontoCalculado | somarAoEvento | naoVizualizarPonto | removerDiaria | vale | ausencia | bancoHoras |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 | False | 0 | DSR SOBRE HORA EXTRA |  | False |  |  | 0 |  | False | 9008 | True | 1 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |
| 5 | False | 0 | DSR SOBRE ADICIONAL NOTURNO |  | False |  |  | 0 |  | False | 9007 | False | 1 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |
| 4 | False | 0 | HORA NOTURNA REDUZIDA |  | False |  |  | 0 |  | False | 9006 | False | 1 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |
| 3 | False | 0 | ADICIONAL NOTURNO |  | False |  |  | 0 |  | False | 9005 | True | 1 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |
| 2 | False | 0 | DSR FALTA |  | False |  |  | 0 |  | False | 9001 | False | 0 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |
| 1 | False | 0 | DIAS SALARIO |  | False |  |  | 0 |  | False | 9000 | False | 0 | False | False | False | False | False | False | False | False | 0 | 0 | False | False | False | False | False | False | 0 | False | False | False |  | False | False | False | False | False |

## Rotas de sindicato/CCT, cargos, funções, benefícios, férias, afastamentos, demissões

Padrão: `combo` (GET), `filtro` (POST), `{id}` (GET). 405 = existe mas não com esse método; 404 = não existe nesse nome.

- `GET /api/rh/sindicatos` → **200**
- `GET /api/rh/sindicatos/combo` → **200**
- `GET /api/RH/Sindicatos/combo` → **200**
- `GET /api/rh/sindicatoFuncoes` → **405**
- `GET /api/rh/sindicatoEventos` → **405**
- `GET /api/rh/sindicatoBeneficios` → **405**
- `GET /api/rh/sindicatoMunicipios` → **405**
- `GET /api/RH/SindicatoFuncaoBeneficios` → **405**
- `GET /api/RH/SindicatoFuncaoEventos` → **405**
- `GET /api/rh/sindicatoFuncoes/1` → **204**
- `GET /api/rh/sindicatoEventos/1` → **204**
- `GET /api/rh/sindicatoBeneficios/1` → **204**
- `GET /api/rh/sindicatoMunicipios/1` → **204**
- `GET /api/RH/SindicatoFuncaoBeneficios/1` → **204**
- `GET /api/RH/SindicatoFuncaoEventos/1` → **204**
- `GET /api/rh/funcoes/combo` → **200**
- `GET /api/rh/cargos/combo` → **200**
- `GET /api/RH/Cargos/combo` → **200**
- `GET /api/RH/Funcoes/combo` → **200**
- `GET /api/rh/beneficios/combo` → **404**
- `GET /api/RH/TiposBeneficios/combo` → **404**
- `GET /api/rh/tiposBeneficios/combo` → **404**
- `POST /api/rh/sindicatos/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/sindicatoFuncoes/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/sindicatoEventos/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/sindicatoBeneficios/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/sindicatoMunicipios/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/RH/SindicatoFuncaoBeneficios/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/RH/SindicatoFuncaoEventos/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/funcoes/filtro` → **404**
- `POST /api/rh/cargos/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/tiposBeneficios/filtro` → **200**
- `POST /api/rh/demissoes/filtro` → **404**
- `POST /api/rh/empregadoHistoricoContatos/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/ferias/filtro` → **200** — `{lista, total, legendas}`
- `POST /api/rh/afastamentos/filtro` → **404**
- `POST /api/RH/Ferias/filtro` → **200** — `{lista, total, legendas}`
- `400 /api/controlePonto/planejamentos/filtro` → **400** — campos exigidos: `{"inicio": ["The Inicio field is required."], "termino": ["The Termino field is required."]}`
- `400 /api/financeiro/schemas/contasPagar` → **400** — campos exigidos: `{"id": ["The value 'contasPagar' is not valid."]}`
- `400 /api/RH/Colaboradores/schema` → **400** — campos exigidos: `{"id": ["The value 'schema' is not valid."]}`
- `GET /api/rh/sindicatoFuncoes/0` → **204**
- `GET /api/rh/sindicatos/0` → **204**
- `GET /api/rh/sindicatos/1` → **204**
