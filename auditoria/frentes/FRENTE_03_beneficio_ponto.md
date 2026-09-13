# FRENTE 03 — Benefício ligado ao ponto + arquivo do operador + repasse ao contrato (12/09/2026)

Branch: `frente/03-beneficio-ponto` (criada a partir de `fase5-hermes-camada-cognitiva` @ 30be528a3 — a
worktree veio 3.442 commits atrás, em 9ca2cf4c9, sem `redesign_builders/`, `scripts/orq/` nem
`beneficios_importer.py`; foi movida para a ponta antes de qualquer linha).
Módulo: `folha` (people_management) + `_frente_03.py` no builder do DP. Testado SÓ no staging, em
**modo efêmero** (imagem `conecta-pro-backend:latest` com a worktree montada em `/app:ro`, banco
`conecta_pro_staging`) — o `/app` do `conecta-pro-backend-staging` é um bind somente-leitura da árvore
principal e não recebe `docker cp`.

> ⚠️ Registro honesto: antes da correção do contrato eu copiei 4 arquivos para
> `/opt/conecta-pro/backend/` (a árvore principal) para o staging enxergá-los. Desfiz na hora:
> `beneficios_importer.py` voltou byte a byte à versão commitada (md5 `74fdf0b1…`, 7.752 bytes, igual ao
> que estava lá) e os 3 arquivos novos foram apagados. A árvore principal ficou como estava.

---

## 1. Estado ANTES (medido 12/09/2026, staging)

- `beneficios_importer.py` só LIA os relatórios (Sólides VA+mobilidade, SINETRAM VT) e gravava
  `employees.vt_modalidade`. Total do Sólides lia **R$ 0** (o "#332373" ficava entre o rótulo e o R$).
- Motor da folha: `VT_DIA=10`, `VR_DIA=22` **chumbados**; dias fixos por escala (`DIAS_TRAB_ESCALA`).
- Não existia: cálculo pelo ponto, colunas "anterior", mapa de frequência, arquivo do operador,
  repasse, tabela de conferência. `cct_benefit_configs`: **0 linhas**.
- Relatórios reais em `uploads/referencia_kits/kit/`: Sólides pedido 332373, **Agosto/2026**, 12 pessoas,
  R$ 6.546,00; SINETRAM pedido 16235837, 1 pessoa (Celiane), R$ 270,00.

Oráculos rodados ANTES do motor (staging):

```
$ test_oraculo_beneficio_fecha.py
FALHOU: o motor de benefício ligado ao ponto não existe (cannot import name 'beneficio_ponto' ...)
1 desvio: motor ausente                                                   exit=1

$ test_oraculo_arquivo_operador.py
FALHOU: gerador/parser de texto não existe (No module named '...beneficio_ponto')
1 desvio: sem gerador                                                     exit=1
```

## 2. O que foi feito, arquivo por arquivo

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_beneficio_fecha.py` (novo) | Por competência com relatório de portal e por pessoa×benefício: motor calculou (ausência = vermelho); portal guardado = PDF; total = qtd × unitário do BANCO; com anterior conhecido, \|calc − portal\| ≤ 0,01. `sem_anterior`: diferença impressa, não julgada (senão seria `coalesce(anterior,0)`). |
| `backend/scripts/orq/test_oraculo_arquivo_operador.py` (novo) | Ida e volta: `montar_arquivo_operador` → `parse_*_texto` reproduz CPF/valor/cartão linha a linha; 2 casos sintéticos (regra) + cada PDF real; SINETRAM sem cartão tem de ser recusado. |
| `backend/modules/people_management/folha/services/beneficio_ponto.py` (novo) | Motor: `calcular_competencia`, `mapa_frequencia`, `importar_portal`, `parametros`, `montar_arquivo_operador`, `gerar_arquivo_operador`, `simular_reajuste`, `abrir_pedido_reajuste`, DDL. CLI: `python3 -m modules.people_management.folha.services.beneficio_ponto 2026 8 [/pasta/pdfs]`. |
| `backend/modules/people_management/folha/services/beneficios_importer.py` | `parse_solides_texto` / `parse_sinetram_texto` (parser por texto — base da ida e volta), `Pedido.competencia` ("(Agosto/2026)"), `ler_pedidos_em` (classifica pelo conteúdo, não pelo nome), fix do total do Sólides. `ler_solides/ler_sinetram` mantêm assinatura. |
| `backend/scripts/qa/checar_repasse_sem_aditivo.py` (novo) | Caçador: contrato ativo com `last_adjustment_date` sem aditivo `adjustment` assinado desde então (A) + pedido de repasse aprovado cujo contrato mudou de `monthly_value` sem aditivo assinado (B). Linha canônica `TOTAL repasses sem aditivo: N`. |
| `backend/modules/operacional/controllers/redesign_builders/_frente_03.py` (novo) | Telas `beneficio-conferencia` (tbl), `beneficio-frequencia` (tbl), forms `beneficio-calcular`, `beneficio-arquivo`, `beneficio-reajuste`; `router` com `/action/beneficio-calcular`, `/action/beneficio-arquivo-operador`, `/action/beneficio-reajuste-pedido`. As telas entram como ABAS de `g-beneficios` (Benefícios & Reembolsos). |
| `backend/modules/operacional/controllers/redesign_builders/departamento_pessoal.py` | 4 linhas: `from ._frente_03 import router as _r03` + `router.include_router(_r03)` (nível do módulo) e `from ._frente_03 import telas as _telas_03` + `out.update(await _telas_03(db, out))` no fim do `build()`. `telas` recebe `out` para pendurar as abas no grupo. |

### As regras do motor (o que a linha da conferência significa)
- **Previsão** = datas DISTINTAS em `shifts` na competência com `status <> 'cancelled'` e não folga
  (`cancelled` duplica `scheduled`: Adeilson tem 45 linhas para 15 dias). Sem shifts: 44h = seg–sáb;
  12x36 = `dias_vt_vr` (sabe quantos, não quais → mapa `?`, `fonte_escala='escala_padrao_sem_dias'`).
  44h: VR só seg–sex (regra já escrita em `calculo_service.dias_vt_vr`).
- **Trabalhado** = dias com par de batidas (dia da ENTRADA), pareando com `MAX_TURNO_H`, `SQL_BATIDAS`,
  `params_batidas` importados de `horas_service` (régua única). Dia com menos que
  `beneficio_horas_minimas_dia` horas = `I` (insuficiente), não `T`. Pessoa sem batida no mês = `S`
  (sem ponto), nunca falta. `punch_timestamp` é hora LOCAL (created_at = punch + 4h, medido).
- **Férias** = `hr_vacation_requests` APPROVED; **afastado** = `sst_afastamentos` (em curso sem retorno =
  aberto, mesma régua da coorte do ponto); **fora do vínculo** = antes da admissão / depois da demissão.
- **Anterior**: planejado/trabalhado do mês anterior + recebido = `portal_valor` da conferência anterior
  (importado dos PDFs). `dias_recebidos = recebido / unitário_anterior`; +Ponto = trabalhou mais do que
  recebeu; −Ponto = recebeu mais do que trabalhou; quantidade = previsão + crédito/débito.
- **Estados** (nunca 0): `ok`, `sem_anterior`, `anterior_sem_ponto`, `anterior_nao_integral` (R$ pago
  não é múltiplo do unitário → humano), `sem_parametro`, `sem_modalidade` (VT sem `vt_modalidade`),
  `sem_escala`, `so_portal` (portal pagou, motor ainda não rodou).
- **Parâmetros do banco** (`cct_benefit_configs`, vigentes): `vale_refeicao` (R$/dia),
  `vale_transporte` por `operadora` (SOLIDES / SINETRAM), `beneficio_horas_minimas_dia`. VR sem config
  cai para `cct_beneficios.valor_minimo`. `concedido_folha` = o que a folha concede HOJE
  (`VT_DIA/VR_DIA × dias_vt_vr`, importados) — para a tela mostrar calculado × folha × portal.

## 3. Estado DEPOIS (medido, modo efêmero, banco do staging)

Motor rodado para Agosto (com os PDFs) e Setembro/2026:
```
portal: pedidos [sinetram 16235837 2026-08 (1 linha), solides 332373 2026-08 (12 linhas)] · gravados 23
motor 2026-08: 56 pessoas · 112 linhas · {sem_anterior: 65, sem_modalidade: 45, sem_escala: 2}
motor 2026-09: 54 pessoas · 108 linhas · {sem_anterior: 43, sem_modalidade: 44, ok: 21}
```

Oráculos VERDES:
```
$ test_oraculo_beneficio_fecha.py
competências com portal: 1 · pessoa×benefício no portal: 23 · casadas no motor: 23 · comparáveis (com anterior): 0 ·
divergentes: 0 · sem anterior: 23 (Δ motor−portal acumulada R$ -106.00)
AVISO: nenhuma linha tinha o anterior — a igualdade motor = portal ainda NÃO foi exercitada; vale a partir da 2ª competência com relatório.
OK benefício fecha: todo pago tem cálculo, o portal guardado é o do PDF, a aritmética bate e o unitário é o do banco   exit=0

$ test_oraculo_arquivo_operador.py
casos sintéticos: 2 · PDFs de portal relidos: 2 (de 9 pdf) · desvios: 0
OK arquivo do operador: o que geramos, relido pelo nosso parser, reproduz linha a linha                                  exit=0

$ checar_repasse_sem_aditivo.py
TOTAL repasses sem aditivo: 0
OK checar_repasse_sem_aditivo                                                                                          exit=0
```

Agosto/2026, calculado × folha × portal (o que a Pyetra vai ver — NÃO corrigido, é paralelo cego):

| Pessoa | Ben. | Prev. | Calc. | Folha | Portal | Δ | Leitura |
|---|---|---|---|---|---|---|---|
| Adeilson, Jonhata (AGP 12x36) | VR/VT | 15 | 330/150 | 330/150 | 330/150 | 0 | bate |
| Antonio, Jonilson, Livia, Maiara (12x36) | VR/VT | 16 | 352/160 | 330/150 | 352/160 | 0 | escala lançada (16) vence a constante da folha (15) |
| Edilene (ASG 44h) | VR | 21 | 462 | 462 | 484 | −22 | portal pagou 22 dias (constante da casa) onde a escala tem 21 seg–sex |
| Celiane, Geilson (ASG) | VR / VT | 21 / 26 | 462 / 260 | 462 / 260 | 506 / 270 | −44 / −10 | +1 dia em cada — ajuste de julho que não conhecemos ("sem anterior") |
| Daniel Vidal (ASG) | VR | 26 | 572 | 330 | 484 | +88 | **cadastro**: `escala_padrao='12x36'` com escala seg–sáb lançada |
| Daniel Souza (demitido 24/08) | VR/VT | 12 | 264/120 | 330/150 | 330/150 | −66/−30 | portal pagou o mês inteiro; 7 dias fora do vínculo |
| Kelly (12x36 sem escala lançada) | VR/VT | 15 | 330/150 | 330/150 | 308/140 | +22/+10 | 14 dias no portal; sem shifts, o motor não sabe quais dias |

Setembro/2026 tem 21 linhas em estado `ok` (Agosto como anterior, com recebido do portal e ponto):
as colunas Plan.ant / Trab.ant / Receb.ant / +Pt / −Pt aparecem preenchidas na tela.

Rotas e telas (servidor efêmero 127.0.0.1:8203):
```
$ docker exec teste-frente-03 python3 -c "from main_production import app; print(sorted(r.path for r in app.routes if 'redesign/action/beneficio' in r.path))"
['/api/v1/redesign/action/beneficio-arquivo-operador', '/api/v1/redesign/action/beneficio-calcular', '/api/v1/redesign/action/beneficio-reajuste-pedido']

GET /api/v1/redesign/data/departamento-pessoal  → 200
abas g-beneficios: [('beneficios', table, 159), ('nova-beneficio', form), ('beneficios-cct', table, 8), ('novo-beneficio-cct', form),
 ('registrar-reembolso', form), ('beneficio-conferencia', table, 220), ('beneficio-frequencia', table, 110),
 ('beneficio-calcular', form), ('beneficio-arquivo', form), ('beneficio-reajuste', form)]
1ª linha conferência: ADAILSON SERRA ALVES · 09/2026 · VR SOL · sem anterior · prev 15 · qtd 15 · R$ 22,00 · calc R$ 330,00 · folha R$ 330,00 · portal —
1ª linha frequência:  ADAILSON SERRA ALVES · 09/2026 · 12x36 · shifts · T3 E3 F10 I4 · TETEIITEIIFOFOFOFOFOFOFOFOFOFO

POST /api/v1/redesign/action/beneficio-calcular {"competencia":"2026-09"} → 200
{'ok': True, 'message': '54 pessoa(s), 108 linha(s) calculadas em 2026-09', 'estados': {'sem_anterior': 43, 'sem_modalidade': 44, 'ok': 21},
 'portal_pedidos_lidos': 2, 'portal_valores_gravados': 23, 'sem_parametro': 0}

POST /api/v1/redesign/action/beneficio-arquivo-operador {"competencia":"2026-09","operadora":"solides"} → 200
SOLIDES_202609130334_53_ConectaMais.txt: 53 linha(s), R$ 21.270,00 · 0 aviso
  NOME DO COLABORADOR                     CPF          EMPRESA / UNIDADE          ALIMENTAÇÃO   MOBILIDADE
  ADAILSON SERRA ALVES                    03527554238  CONECTA MAIS PATRIMONIAL        330.00         0.00
  ADEILSON DINIZ DEODATO                  81429045272  CONECTA MAIS PATRIMONIAL        484.00       220.00
POST … {"operadora":"sinetram"} → 200 · SINETRAM_202609130334_1_ConectaMais.txt: 1 linha, R$ 240,00
       1 846.184.772-53 CELIANE GARCIA DE SOUSA   58.04.06504388-1   R$   240,00  VALE TRANSPORTE

POST /api/v1/redesign/action/beneficio-reajuste-pedido {"beneficio":"VR","novo_unitario":"24.00","competencia":"2026-09"} → 200
{'ok': True, 'message': 'Pedido aberto — rascunho 73881dc3', 'beneficiarios': 50, 'contratos': 8, 'repasse_total_mes_valor': 1684.0, 'avisos': 0,
 'por_contrato_e_funcao': {
   'CTR-2026-00013 · Ideal Flores · AGENTE DE PORTARIA (SOLIDES)': '7 × 105 dias · R$ 22,00 → R$ 24,00 · contrato R$ 65.842,42 · repasse R$ 210,00/mês',
   'CTR-2026-00011 · Laranjeiras Village · AGENTE DE PORTARIA (SOLIDES)': '8 × 120 dias · … · contrato R$ 42.544,50 · repasse R$ 240,00/mês',
   'AMBÍGUO: CTR-2026-00009 / CTR-2026-00018 · AGENTE DE PORTARIA (SOLIDES)': '4 × 60 dias · … · contrato sem dado · repasse R$ 120,00/mês', …}}
```
O pedido ficou em `agent_drafts` (🔴, `reajuste_beneficio_repasse`, status `rascunho`) e o caçador continua em 0 —
nenhum preço mudou, que é o desenho.

## 4. Fiação pendente para o integrador

**DDL de produção** (idêntico ao que o motor cria com IF NOT EXISTS — pode deixar o motor criar ou rodar antes):
```sql
CREATE TABLE IF NOT EXISTS folha_beneficio_conferencia (
  id bigserial PRIMARY KEY,
  employee_id uuid NOT NULL,
  competencia date NOT NULL,
  beneficio varchar(4) NOT NULL,
  operadora varchar(20),
  estado varchar(24) NOT NULL,
  planejado_anterior integer, trabalhado_anterior integer, recebido_anterior numeric(12,2),
  direito_anterior integer, saldo_anterior integer,
  previsao integer, mais_ponto integer, menos_ponto integer, credito_debito integer, quantidade integer,
  unitario numeric(12,2), total numeric(12,2),
  concedido_folha numeric(12,2),
  portal_valor numeric(12,2), portal_pedido varchar(40), portal_cartao varchar(40),
  mapa jsonb,
  fonte_escala varchar(30),
  calculado_em timestamptz DEFAULT now(),
  UNIQUE (employee_id, competencia, beneficio)
);
```

**Parâmetros (DML) — DECISÃO DO JORDAN antes de rodar em produção.** Valores MEDIDOS nos relatórios de
Agosto/2026 (VR 22 = 330/15; VT Sólides 10 = 150/15; VT SINETRAM 10 = 270/27); horas mínimas = 4h é chute
meu, conservador, marcado como pendente:
```sql
INSERT INTO cct_benefit_configs (id, empresa_id, tipo_beneficio, valor_empresa, desconto_empregado, operadora, vigencia_inicio, ativo, observacoes) VALUES
 (gen_random_uuid(), NULL, 'vale_refeicao', 22.00, 0, 'SOLIDES', '2026-01-01', true, 'frente 03: R$/dia — pedido Sólides Agosto/2026 (330 = 15 × 22) e piso CCT'),
 (gen_random_uuid(), NULL, 'vale_transporte', 10.00, 0, 'SOLIDES', '2026-01-01', true, 'frente 03: R$/dia — mobilidade Sólides Agosto/2026 (150 = 15 × 10)'),
 (gen_random_uuid(), NULL, 'vale_transporte', 10.00, 0, 'SINETRAM', '2026-01-01', true, 'frente 03: R$/dia — SINETRAM (270 = 27 × 10) — confirmar com a Pyetra'),
 (gen_random_uuid(), NULL, 'beneficio_horas_minimas_dia', 4.00, 0, NULL, '2026-01-01', true, 'frente 03: horas mínimas no dia para contar como trabalhado — DECISÃO PENDENTE');
```
(no staging as 4 linhas já estão.)

**`backend/scripts/qa/checar_regressao.py`** — dicionário `CACADORES` (roda no container):
```python
    "checar_repasse_sem_aditivo.py": lambda s: _n(r"^TOTAL repasses sem aditivo:\s*(\d+)", s),
```

**Conflito com a frente 08** (já mergeada): ela anexou `from ._frente_08 …` / `out.update(await _telas_08(db))`
logo antes do `return out`. As minhas (`# frente 03`) ficam logo após `montar_grupos(out)` e passam `out`
(`_telas_03(db, out)`) para pendurar as abas no grupo. As quatro linhas convivem — manter as duas.

**`celery_app.py` / `main_production.py`**: nada. O router entra pelo registry dos builders
(`departamento_pessoal.router.include_router(_r03)`), o motor não tem task.

**`frontend/src/app/redesign/_modules/departamento-pessoal.json`**: nada — as 5 telas são abas do grupo
`g-beneficios` já existente no menu.

**Relatórios dos portais**: o form "Calcular" e os oráculos procuram PDFs em `/app/uploads/referencia_kits`
e `/app/uploads/kits` (produção monta `uploads/` em `/app/uploads`; o oráculo aceita `BENEFICIO_PDF_DIR`).
Colocar o Sólides e o SINETRAM do mês lá é o que liga o "portal" da conferência.

**Deploy**: bake normal (`deploy_backend_bluegreen.sh`) — `docker cp` não publica.

## 5. O que NÃO foi feito e por quê

- **Nenhuma escrita em folha/holerite/pagamento/pedido de portal** — paralelo cego (pré-mortem).
- **Nenhum repasse automático**: o pedido nasce 🔴 em `agent_drafts` sem executor; aprovar não muda
  preço. Preço muda por `contract_addendums` (tipo `adjustment`, assinado) — ato humano.
- **Layout oficial de importação do Sólides e do SINETRAM**: não existe documentação em casa. O arquivo
  gerado espelha as colunas dos relatórios deles e é provado pelo NOSSO parser. Antes de subir a um
  portal, confirmar o layout com eles (a tela avisa).
- **Cartão do SINETRAM**: o nº do cartão é da PESSOA, não da competência — o gerador cai para o último
  `portal_cartao` conhecido dela em qualquer mês (foi o que fez o arquivo de Setembro sair com a Celiane em vez
  de vazio). Quem nunca apareceu num relatório do SINETRAM fica fora do arquivo, com aviso.
- **Download do arquivo**: o resultado do form devolve o conteúdo em texto (painel de resultado). Botão
  de download fica para quando o layout for confirmado — não vale entregar arquivo bonito de layout
  incerto.
- **Colunas fora do alembic** (`vt_modalidade`, `plano_odonto_*`): continuam fora — zona proibida;
  dívida do Jordan (§6 da análise de 09/09).
- **Cadastro**: Daniel Vidal (ASG) com `escala_padrao='12x36'`; 45 pessoas ativas sem `vt_modalidade`
  (VT em `sem_modalidade`); Kelly sem escala lançada. Não corrigi cadastro — aparece na tela.
- **SINETRAM: 27 dias × R$ 10 ou 30 × R$ 9?** Só um pedido, não dá para distinguir. Ficou R$ 10/dia como
  parâmetro; a Pyetra confirma.
- **Igualdade motor = portal ainda não exercitada** (todas as linhas de Agosto são a 1ª competência). O
  oráculo diz isso em voz alta e passa a valer na 2ª competência com relatório.
- **Hermes/LLM**: nada aqui depende do LLM (Parte 0.2 não afeta esta frente).

## 6. Como o Jordan testa amanhã

1. DP → **Benefícios & Reembolsos** → abas novas: *Benefício × ponto × portal*, *Mapa de frequência*,
   *Calcular competência*, *Arquivo do operador*, *Reajuste com repasse (pedido)*.
   (deep-link: `/redesign/departamento-pessoal?t=beneficio-conferencia`).
2. Na conferência, filtrar Agosto e comparar com a tabela da seção 3 — cada Δ tem uma leitura.
3. *Calcular competência* com `2026-09`: recalcula e reimporta os PDFs que estiverem em `uploads/`.
4. *Arquivo do operador*: `2026-09` + Sólides → o texto aparece no resultado com as colunas do relatório
   deles; SINETRAM só lista quem tem nº de cartão conhecido (o resto vira aviso).
5. *Reajuste*: VR, `24.00`, `2026-09` → resultado mostra R$ Contrato / R$ Unitário / R$ Repasse por
   contrato × função e o pedido aparece na **Central de Aprovações** (🔴, tipo
   `reajuste_beneficio_repasse`). Aprovar NÃO muda nada — é o desenho.
6. Linha de comando (staging): `docker exec -e PYTHONPATH=/app <container> python3 /app/scripts/orq/test_oraculo_beneficio_fecha.py`
   e `..._arquivo_operador.py`, `python3 /app/scripts/qa/checar_repasse_sem_aditivo.py`.

## 7. Riscos residuais (pré-mortem, frente 3)

1. *Folha que já erra* (DESC.ADIANT.SALARIAL): o motor não lê a folha, lê escala + ponto + portal; o
   `concedido_folha` só mostra a régua atual. Não propaga, mas também não corrige a folha.
2. *Arquivo do operador errado sem ninguém perceber*: a ida e volta é pelo NOSSO parser; o aceite do
   portal continua não sendo prova. Layout oficial pendente.
3. *Repasse sem autorização*: caçador em 0; depende de `last_adjustment_date`/pedido porque `contracts`
   não tem trilha de preço (0 linhas em `audit_logs`). Pista, não prova.
4. *Anterior que não temos*: tratado como estado; Setembro já tem 21 linhas `ok`. O primeiro mês real
   de comparação será Outubro (com o pedido de Setembro do portal).
5. *Colunas fora do alembic*: risco intacto até a migration.
6. *Ponto próprio desde 14/08*: Agosto tem `S`/`I` em quem ainda batia no Sólides — o "trabalhado
   anterior" de Setembro herda isso (`anterior_sem_ponto` quando não há batida nenhuma).
