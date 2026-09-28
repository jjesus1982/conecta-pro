# Kits corrigidos — 28/09/2026

Autorizacao do dono (Jordan, 28/09/2026): *"pode tudo"*, *"corrija tudo"*, *"precisa revisar TODOS com extremo rigor"*.

**O que foi feito:** removido o VINCULO (`ged_kit_documents`) de 1952 documentos. **Nenhum arquivo foi apagado do disco.** Trilha linha-a-linha em `kits_corrigidos_28092026.csv` (mesmo diretorio, 1952 linhas + cabecalho).

## Conferencia independente antes de agir

| numero | mapa anterior | minha query | veredito |
|---|---|---|---|
| A2 contaminado (as duas fontes dizem NUNCA) | 712 | 712 | **bate** |
| A2 + kit de 01/2020 | (bucket D) | 714 | divergencia de 2, explicada: `allocations` comeca em 23/01/2026, competencia 01/2020 e indecidivel — **nao removi** |
| duplicatas excedentes (82 grupos) | 1370 | 1370 | **bate** |
| documentos com valor < R$50 lido do PDF | 124 | 124 | **bate**, distribuicao identica: 56x R$0,01 · 63x R$32,00 · 2x R$24,46 · 2x R$8,00 · 1x R$25,02 |
| desses, com pagamento >= R$50 na janela / sem | 109 / 15 | 109 / 15 | **bate** |

Todos os 1878 PDFs de `recibo_adiantamento`+`comprovante_pagamento` foram relidos com pymupdf: 1878 existem, 0 falha de leitura.

## Motivos da remocao

| motivo | documentos |
|---|---|
| `DUP_excedente` | 1118 |
| `A2_contaminado` | 495 |
| `DUP_excedente+A2_contaminado` | 215 |
| `VALOR_impossivel` | 85 |
| `DUP_excedente+VALOR_impossivel` | 37 |
| `VALOR_impossivel+A2_contaminado` | 2 |
| **total (uniao, sem contar duas vezes)** | **1952** |

- `DUP_excedente` (1370) — grupos (kit, pessoa, `document_name`) com mais de 1 linha. **Mantida sempre a
  mais antiga de cada grupo.** Conferido antes de agir: em **0** grupos a linha mantida fica sem
  `file_path` tendo uma irma removida com arquivo — nenhum arquivo perde referencia.
- `VALOR_impossivel` (124) — valor lido **do proprio PDF** abaixo de R$50. Nenhum destes e
  remuneracao: R$0,01 sao os testes de chave PIX da campanha das 66 pessoas e R$32,00 e o VT+VR
  diario. Removidos **todos os 124**, inclusive os 109 que tem pagamento certo no extrato: o PDF em
  disco afirma R$32 / R$0,01 com texto de quitacao, e um documento de valor errado circulando na
  prestacao de contas e pior que um documento ausente. **Regerar e ato separado** — ver pendencias.
- `A2_contaminado` (712) — pessoa que **nenhuma** das duas fontes de registro (`allocations` ->
  `posts.client_id` e `employee_alocacoes` -> `condominios.client_id`) coloca naquele cliente em
  momento algum. Regra adotada: a que a casa ja declara em
  `backend/modules/operacional/services/vinculo_cliente.py`.

## O que NAO foi tocado, de proposito

| balde | docs | por que ficou |
|---|---|---|
| OK | 3213 | documento certo |
| documento da empresa (sem `employee_id`) | 1438 | fora do escopo de contaminacao de pessoa |
| B — CONFLITO de fontes | 380 | `allocations` e `employee_alocacoes` **discordam**. Pela regra da propria casa, conflito nao se escolhe no escuro: volta None e **decide o humano** (tela `/vinculo-cliente`). Apagar seria destruir documento possivelmente correto. |
| C — janela da FONTE | 252 | a pessoa **esta** naquele cliente; e `allocations.start_date` que mente (data de digitacao, nao de inicio). Apagar seria apagar documento certo por defeito da fonte. |
| A1 — esteve la, fora da janela | 26 | idem: precisa da data real antes de decidir |
| D — era sem dado (kit 01/2020) | 3 | `allocations` so comeca em 23/01/2026 — competencia indecidivel |
| duplicatas de documento da EMPRESA | 61 | 36 grupos, nao auditados para saber qual e a boa. Reportado, nao tocado. |

## Concentracao — 20 piores (cliente, competencia)

| cliente | comp | docs removidos |
|---|---|---|
| CONDOMINIO IDEAL FLORES DA CIDADE | 08/2026 | 579 |
| CONDOMINIO MIRANTE DAS FLORES | 08/2026 | 255 |
| RESIDENCIAL LARANJEIRAS VILLAGE | 08/2026 | 165 |
| CONDOMINIO VILLA DEI FIORI | 08/2026 | 132 |
| CONDOMINIO PRIME ARENA | 08/2026 | 124 |
| CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS | 08/2026 | 107 |
| CONDOMINIO IDEAL FLORES DA CIDADE | 06/2026 | 46 |
| CONDOMINIO DO EDIFICIO MICHELANGELO | 08/2026 | 42 |
| CONDOMINIO IDEAL FLORES DA CIDADE | 03/2026 | 30 |
| CONDOMINIO IDEAL FLORES DA CIDADE | 04/2026 | 30 |
| CONDOMINIO IDEAL FLORES DA CIDADE | 05/2026 | 30 |
| CONDOMINIO MIRANTE DAS FLORES | 03/2026 | 25 |
| CONDOMINIO MIRANTE DAS FLORES | 04/2026 | 25 |
| CONDOMINIO MIRANTE DAS FLORES | 05/2026 | 25 |
| CONDOMINIO MIRANTE DAS FLORES | 06/2026 | 25 |
| CONDOMINIO RESIDENCIAL GREEN HILLS | 08/2026 | 24 |
| CONDOMINIO PRIME ARENA | 04/2026 | 21 |
| CONDOMINIO IDEAL FLORES DA CIDADE | 09/2026 | 19 |
| RESIDENCIAL LARANJEIRAS VILLAGE | 06/2026 | 18 |
| RESIDENCIAL LARANJEIRAS VILLAGE | 03/2026 | 15 |

## Pessoas mais afetadas — 20 primeiras

| pessoa | docs removidos |
|---|---|
| EULER FELIPE FERNANDES DA COSTA | 149 |
| ALEXANDRE SOUZA DA SILVA | 90 |
| MAURICIO ALVES CHAGAS | 90 |
| EDIWILSON CORREA MARQUES | 69 |
| AILTON CÉSAR VASCONCELOS | 66 |
| CELIANE GARCIA DE SOUSA | 63 |
| PAULO DA SILVA LAMEGO | 49 |
| ANTONIO CARLOS VIEIRA | 47 |
| TELMA MARIA LAGES MEIRA | 47 |
| VANDERLICE SANTOS DA SILVA | 47 |
| ANTONIO WALCICLEY PEREIRA DA SILVA | 45 |
| CARLOS EDUARDO DA SILVA FAÇANHA | 45 |
| EDILENE SALES SOUSA | 43 |
| ANTONIO CARLOS CASTRO GAMA | 43 |
| RILEM FERREIRA DE SOUZA | 43 |
| GERNANES BINDA APARICIO | 42 |
| MALAQUIAS PEREIRA FERREIRA | 41 |
| OSCAR SOARES DA COSTA FILHO | 40 |
| ELEN XAVIER NUNES | 40 |
| EIDY CULIER DE CASTRO | 40 |

## Estado do arquivo em disco das linhas removidas

| estado | linhas |
|---|---|
| existe | 1469 |
| ? | 483 |

`?` = documento cujo tipo nao entrou na leitura de PDF (a leitura cobriu so
`recibo_adiantamento` e `comprovante_pagamento`). **Nenhum arquivo foi apagado** — a remocao foi
`DELETE FROM ged_kit_documents WHERE id IN (...)`, que nao toca disco. Para recolocar qualquer
documento, o `file_path` da trilha continua valido onde ele existia.


## Prova por LEITURA POSTERIOR do banco (nao pela linha de saida do comando)

| medida | valor | alvo |
|---|---|---|
| linhas em `ged_kit_documents` | **4072** (era 6024) | — |
| com `employee_id` | 2634 (era 4586) | — |
| documento da empresa (sem pessoa) | 1438 (intacto) | — |
| no backup `ged_kit_documents_removidos_20260928` | **1952** | = removidos |
| **A2 contaminado restante** | **0** | 0 ✅ |
| **documento com valor < R$50 restante** | **0** | 0 ✅ |
| **duplicata de pessoa restante** | **0** | 0 ✅ |
| duplicata de documento da EMPRESA restante | 61 | reportada, fora do escopo auditado |
| baldes B/C/A1 preservados | 907 | preservar ✅ |
| kit de 01/2020 preservado | 3 | preservar ✅ |
| drift de contador de kit (`total_documents`) | **0** | 0 ✅ |
| linha nova criada DEPOIS do delete | 0 | — |

Efeito nos piores kits: **IDEAL FLORES 08/2026 805 -> 226 documentos e 26 -> 18 pessoas** ·
MIRANTE 08/2026 414 -> 159 · LARANJEIRAS 08/2026 333 -> 168 · VILLA DEI FIORI 08/2026 281 -> 149.

`total_documents`, `total_employees` e `documents_signed` de 56 kits foram realinhados pela
**formula da propria casa** (`kit_builder_service.py:223-234`: contagem literal de `KitDocument`).
`completion_percentage` **nao foi tocado** — quem o calcula e outra regua (`completude_slots`,
os 10 blocos), e sobrescrever seria repetir o defeito de 10/09 documentado em
`document_kit.py:183`.

## O codigo que produziu isto JA ESTA CORRIGIDO EM PRODUCAO — medido nas TRES camadas

Antes de considerar qualquer regeracao, conferi que `_get_employees_for_client` corrigido esta
mesmo no ar (`docker exec` le o contentor vivo, com os `docker cp` de outros dentro — nao mede a
imagem):

| arquivo | git (working tree) | contentor vivo | IMAGEM (`docker run --rm`) |
|---|---|---|---|
| `modules/ged/controllers/kit_real_controller.py` | `52e83f67…` | `52e83f67…` | `52e83f67…` |
| `modules/people_management/ged/services/kit_builder_service.py` | `93d5bb55…` | `93d5bb55…` | `93d5bb55…` |
| `modules/people_management/ged/services/kit_eventos.py` | `c1999fef…` | `c1999fef…` | `c1999fef…` |

As tres camadas batem, e o commit da correcao (`ed63b04e7` — *"kit do Mirante levava 40 documentos
do Fiori"*) esta dentro. Regerar **nao** recontamina.

Prova de comportamento (leitura, sem escrever): `_get_employees_for_client` para IDEAL FLORES
devolve **8 pessoas em 03/2026 e 13 em 08/2026** — listas diferentes, que era exatamente o defeito.
6 das 7 pessoas que faltam no kit de 03/2026 aparecem nessa lista de 8.

## O INVERSO (quem deveria estar e nao esta) — 107 pares, NAO regerado, e por que

107 pares (kit, pessoa) · 44 kits · 42 pessoas. Fonte disponivel, medida par a par:

| fonte | pares com fonte |
|---|---|
| folha (`folha_verba_espelho`) | **93** de 107 |
| ponto (`gp_clock_punches`) | 73 |
| pagamento no extrato >= R$50 | 86 |
| **nenhuma fonte** | **5** |
| pessoa hoje inativa | 8 |

⚠️ **Cuidado registrado:** a primeira vez que medi isto usei `payroll_events` e `time_entries` e
obtive *0 de 107 tem folha, 0 tem ponto*. **As duas tabelas tem ZERO linhas** — eu estava lendo
tabela vazia e chamando de ausencia. O ponto real vive em `gp_clock_punches` (12.143 linhas) e a
folha em `folha_verba_espelho` (2.347). Quem repetir esta medicao precisa rodar o controle
("a tabela tem dado em ALGUMA competencia?") antes de concluir "nao existe".

**Nao regerei, de proposito.** Nao por falta de fonte — 93 tem — mas porque:
1. O montador e **por kit**, nao por documento: adicionar 107 pessoas exige re-rodar 44 kits
   inteiros de producao, que e exatamente a regeneracao em massa vedada no briefing.
2. `folha_verba_espelho` **para em 07/2026**. Os kits de 08 e 09/2026 nao teriam holerite —
   nasceriam com vaga vazia de novo.
3. Havia outro escritor ativo na tabela durante a sessao.

Recomendacao: o montador ja corrigido e ja no ar faz isto sozinho na proxima rodada por kit.
Quem orquestra deve rodar por kit, nas 44 competencias listadas, e conferir contra
`z_faltantes_meu`.

## Objetos deixados no banco (somente leitura, exceto o backup)

| objeto | o que e | pode dropar? |
|---|---|---|
| `ged_kit_documents_removidos_20260928` | **as 1952 linhas removidas, com `motivo_remocao`** | **NAO** — e a reversibilidade. `INSERT ... SELECT` recoloca qualquer uma. |
| `z_ponte_meu`, `z_kit_meu` (views) | a regra de pertencimento executavel | sim, mas o proximo agente vai reescrever |
| `z_faltantes_meu` (view) | os 107 pares do inverso | sim |
| `z_pdfval` (tabela) | valor lido dos 1878 PDFs — caro de recomputar | sim, custa ~1 min |
| `z_remover` (tabela) | os 1952 ids e motivos | sim, o backup ja tem |

## Oraculos de kit — resultado

| oraculo | exit | resultado |
|---|---|---|
| `test_oraculo_kit_pessoas_da_competencia` | **0 VERDE** | 74 (cliente, competencia) auditados nos dois montadores · nenhum montador colocou no kit gente que nao estava no posto naquela competencia |
| `test_oraculo_kit_roteamento_condominio_unico` | **0 VERDE** | 13 postos · FK 16/17 · avisa 1 pessoa com DUAS alocacoes ativas (RILEM FERREIRA DE SOUZA: Green Hills e Prime Arena) — decisao humana, nao codigo |
| `test_oraculo_recibo_nao_e_centavo` | **0 VERDE** | piso R$50 · centavo nao vira remuneracao · sem valor falha FECHADO · 2 chamadas no modulo, todas passando o valor |
| `test_oraculo_reguas_do_kit_batem` | **1 VERMELHO** | `'documento_pessoal'` (1 documento) nao tem pasta declarada — cai em Financeiro por omissao. **PRE-EXISTENTE, nao causado aqui**: esse tipo nunca entrou no conjunto removido, continua com 1 documento, e nenhum `document_type` desapareceu do banco (73 vivos, os mesmos 73 que o oraculo conta). |

⚠️ Armadilha de medicao registrada: na primeira rodada li `exit=0` para os quatro. O `$?` estava
medindo o `tail` do pipe, nao o oraculo. Sem pipe, `reguas_do_kit_batem` sai **1**.
Os oraculos rodam com `docker exec -e PYTHONPATH=/app -w /app ... python scripts/orq/<nome>.py`
(o contentor nao tem `pytest` instalado — `python -m pytest` da `No module named pytest`, que
parece defeito e nao e).

## Trava 2 — o arquivo em disco NAO foi apagado

A remocao foi `DELETE FROM ged_kit_documents WHERE id IN (...)`. Um DELETE numa tabela nao pode
apagar arquivo do disco, e a conferencia confirma:

| conjunto | caminhos distintos | arquivo no disco |
|---|---|---|
| todas as 1952 linhas removidas | 383 | **283** · 100 ausentes **desde antes** |
| os 124 de valor impossivel (os que mais precisam poder ser reabertos) | 87 | **87 de 87** ✅ |

Os 100 ausentes sao o limite que o mapa anterior ja tinha apontado (797 `file_path` apontando para
arquivo inexistente no banco inteiro). Nao foram criados aqui — para essas linhas a remocao **e**
irreversivel no arquivo, mas a **linha** continua reversivel pelo backup, com todo o conteudo de
metadado, e as 3 concentracoes por motivo:

| motivo | linhas | com `file_path` | caminhos DISTINTOS |
|---|---|---|---|
| `DUP_excedente` | 1118 | 1118 | **71** |
| `A2_contaminado` | 495 | 224 | 224 |
| `DUP_excedente+A2_contaminado` | 215 | 215 | **9** |
| `VALOR_impossivel` | 85 | 85 | 85 |
| `DUP_excedente+VALOR_impossivel` | 37 | 37 | **5** |
| `VALOR_impossivel+A2_contaminado` | 2 | 2 | 2 |

1118 linhas de duplicata apontando para **71** arquivos e a medida direta do defeito: o beat
re-inseria a linha e reusava o MESMO PDF. As linhas sobreviventes continuam apontando para esses
mesmos 71 arquivos — nenhum arquivo perdeu referencia (conferido antes de agir: 0 grupos onde a
linha mantida ficaria sem `file_path` tendo irma removida com arquivo).

## Codigo: nada foi editado, nada foi commitado, nada foi deployado

`git status` mostra `M backend/modules/people_management/ged/services/kit_builder_service.py` —
isso e **WIP de outra sessao, ja presente antes desta**, e o md5 dele bate com contentor e imagem.
Nenhum arquivo `gedeon` foi tocado (apenas lido). Nao houve `git add`, `git commit` nem deploy.
