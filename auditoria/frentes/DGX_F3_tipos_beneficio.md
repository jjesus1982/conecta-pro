# DGX F3 — Tipos de Benefício com regra de desconto (24/09/2026)

Branch: `dgx/f3-tipos-beneficio` (a worktree veio em 9ca2cf4c9, 3.400+ commits atrás; movida para a
ponta de `fase5-hermes-camada-cognitiva` @ c7077dbb6 antes de qualquer linha).
Módulo: `folha` (people_management) + builder do DP. Testado SÓ no sandbox staging, em modo efêmero
(imagem `conecta-pro-backend:latest`, worktree montada em `/app:ro`, banco `conecta_pro_staging`,
container `teste-dgx-f3` na porta 8203 — parado ao fim). **Produção não foi tocada** (só leitura).

---

## 1. Estado ANTES (medido 24/09/2026, staging = cópia de produção)

- A regra de VT/VR vivia em três lugares, nenhum deles dado: `calculo_service` (`DESC_VT_PCT=0.04`,
  `DESC_VR_PCT=0.01`, `DESC_ODONTO=8.50`, `DESC_SEGURO=2.00`, rubricas 1010/1011/1020/1021), o motor
  `beneficio_ponto` (férias e afastados SEMPRE removidos da previsão, sem limite de faltas, saldo do mês
  anterior sempre aplicado) e `cct_benefit_configs` (R$/dia por operadora).
- `cct_beneficios`: 8 linhas (valor/desconto %), sem tipo de desconto, sem integração com ponto.
- `employee_benefits`: 159 linhas, `type` livre (`VT`, `Plano Odontológico`, `Seguro Vida`,
  `vale_refeicao`…), sem tipo com regra, sem linha, sem quantidade/unitário.
- `employees.vt_modalidade`: 40 ativos NULL · 9 solides · 1 sinetram (produção: 40/9/1 também).
- `folha_beneficio_conferencia`: só 08/2026 (108 linhas). Gravei a **baseline** com o motor ANTERIOR
  (antes de qualquer edição) para 08 e 09/2026:
  ```
  2026-08: VR sem_anterior 54 (R$ 18.832,00) · VT sem_anterior 11 (R$ 2.090,00) · VT sem_modalidade 43
  2026-09: VR ok 11 (R$ 5.082,00) · VR sem_anterior 40 (R$ 15.026,00) · VT ok 10 (R$ 2.120,00) · VT sem_modalidade 41
  ```
- Oráculo ANTES do código (vermelho):
  ```
  $ test_oraculo_beneficio_regra_e_dado.py
  FALHOU: tabela beneficio_tipos não existe — a regra ainda mora no código
  TOTAL desvios: 1                                                        exit=1
  ```

## 2. O que o DGX tem (docs/dgx/01, "Tipos de Benefício" / "Benefício individual" / "Linhas de VT")

Tipo de Benefício com: tipo primitivo (12), mensal, prevalecer individual, **tipo de desconto (7)** +
coeficiente, evento de débito, desconto direto em dinheiro, **integração com ponto (8 modos)**, desconto
por saldo, faltas / faltas justificadas / dias trabalhados no mês, meses de afastamento permitido, remover
férias / afastados / atrasados, meio período (tipo/horas/valor). Benefício individual com linha
(itinerário), quantidade, unitário, "anular outras fontes", `Manual`. Linhas de VT por operadora com
valor, tipo de passe (cartão/papel), linha mensal.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/beneficio_tipos.py` (novo, 347 l.) | DDL idempotente (`_ensure`), seed, `regras(db)` (a regra ativa por primitivo), `salvar_tipo` / `inativar_tipo` / `salvar_linha` / `salvar_individual` com validação (origem obrigatória; coeficiente obrigatório se desconto ≠ nenhum; rubrica tem de existir; tarifa sem origem recusada). `__main__` = auto-checagem das réguas de entrada. |
| `backend/modules/people_management/folha/services/beneficio_ponto.py` (+49/−11) | `Parametros.regras` lido de `beneficio_tipos`; `mapa_frequencia` devolve `removidos` (dias planejados que férias/afastamento tiraram); `calcular_competencia(..., gravar=True)` lê `remover_ferias` / `remover_afastados` / `limite_faltas` da regra; estados novos `sem_regra` (sem tipo ativo — nunca constante escondida) e `cortado_faltas`; `gravar=False` devolve `linhas_calc` sem escrever (é como o oráculo compara). |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f3_tipos_beneficio.py` (novo, 293 l.) | Telas + ações (abaixo). |
| `departamento_pessoal.py` (+6) | plug `# dgx f3`: `router` no topo, `telas(db, out)` após a frente 03. |
| `_frente_03.py` (+2) | tons dos dois estados novos na conferência. |
| `backend/scripts/orq/test_oraculo_beneficio_regra_e_dado.py` (novo) | §4. |

**DDL que `_ensure` aplica em produção no 1º acesso** (telas, ações e motor chamam):
```sql
CREATE TABLE IF NOT EXISTS beneficio_tipos (id bigserial PK, nome varchar(100) UNIQUE, tipo_primitivo CHECK (11 valores),
  mensal, prevalecer_individual, tipo_desconto CHECK (7 valores) DEFAULT 'nenhum', coeficiente_desconto numeric(12,4),
  rubrica_debito varchar(10), desconto_direto_dinheiro, integracao_ponto CHECK (8 valores | NULL), desconto_por_saldo,
  limite_faltas int, limite_faltas_justificadas int, dias_trabalhados_mes int, meses_afastamento_permitido int,
  remover_ferias, remover_afastados, remover_atrasados, meio_periodo_tipo CHECK (nenhum|valor|percentual),
  meio_periodo_horas numeric(6,2), meio_periodo_valor numeric(12,2), cct_beneficio_id uuid, ativo, origem_regra text, created_at, updated_at);
CREATE TABLE IF NOT EXISTS beneficio_linhas (id bigserial PK, operadora varchar(40), codigo, nome varchar(200), valor numeric(12,2),
  tipo_passe CHECK (cartao|papel), mensal, ativo, origem_regra text, created_at, updated_at, UNIQUE (operadora, nome));
ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS beneficio_tipo_id bigint, linha_id bigint, quantidade numeric(10,2),
  valor_unitario numeric(12,2), anular_outras_fontes boolean NOT NULL DEFAULT false, manual boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_employee_benefits_beneficio_tipo ON employee_benefits (beneficio_tipo_id);
```
**Seed** (`INSERT … ON CONFLICT DO NOTHING`, números lidos de `calculo_service` na hora, nunca copiados):

| Tipo | Prim. | Desconto | Rubrica | Ponto | Remover | Origem |
|---|---|---|---|---|---|---|
| Vale Transporte | VT | % sobre salário · 4 | 1010 | diária · saldo | férias, afastados | `DESC_VT_PCT`; R$/dia em `cct_benefit_configs`; regra do motor da frente 03 |
| Vale Refeição | VR | % sobre salário · 1 | 1011 | diária · saldo | férias, afastados | `DESC_VR_PCT`; 44h sem VR no sábado; idem |
| Plano Odontológico | odonto | fixo · 8,50 | 1020 | — | — | `DESC_ODONTO` (17,00 com dependente — Pyetra 09/09) |
| Seguro de Vida | seguro_vida | fixo · 2,00 | 1021 | — | — | `DESC_SEGURO` |
| Cesta Básica / Ajuda Medicamento / Auxílio Funeral / Empréstimo Consignado | cesta/outro | nenhum | — | — | — | `cct_beneficios.<tipo>` — sem desconto em código |

Linhas de VT: uma por operadora em `cct_benefit_configs.vale_transporte` (SINETRAM R$ 10/dia, SOLIDES
R$ 10/dia), `origem_regra` = a observação daquela linha ("confirmar com a Pyetra" no SINETRAM). Nenhuma
tarifa inventada; linha nova pode nascer sem valor e a aba avisa quantas estão assim.
Backfill (só colunas MINHAS, só onde NULL): `employee_benefits.beneficio_tipo_id` por `type`
(VT/vale_transporte → VT; vale_refeicao → VR; …odont… → odonto; …seguro… → seguro_vida) e `linha_id`
pela `vt_modalidade` do colaborador quando a operadora tem uma linha só. Medido no staging: 51 VT ativos
apontam para o tipo VT; 3 ganharam linha (os que têm `vt_modalidade` E benefício VT).

**Telas** (abas do grupo `g-beneficios` do DP; deep-link `/redesign/departamento-pessoal?t=<id>`):

| id | tipo | o que mostra / faz |
|---|---|---|
| `beneficio-tipos` | table (8 linhas) | Tipo · Primitivo · Período · Desconto (regra resumida, ex. "% sobre salário · 4% · rubrica 1010") · Ponto · Faltas/just./dias · Remover · Meio período · CCT · Origem · Estado. Ações por linha: **Editar** (form completo pré-preenchido) e **Inativar** (com motivo). CTA "Novo tipo". Filtro ativos/inativos. |
| `beneficio-tipo-novo` | form | os 21 campos do `/TiposBeneficios` do DGX → `POST /api/v1/redesign/action/beneficio-tipo-salvar` |
| `beneficio-linhas` | table (2) | Operadora · Código · Linha · Valor (ou "sem tarifa — sem fonte") · Passe · Período · Em uso · Origem · Estado; Editar / Inativar. CTA "Nova linha". |
| `beneficio-linha-nova` | form | → `beneficio-linha-salvar` |
| `nova-beneficio` (existente) | form | ganhou **Tipo com regra**, **Linha (VT)**, **Quantidade**, **Valor unitário**, **Anular outras fontes**; passa a gravar por `beneficio-individual-salvar` (`manual = true`, colunas antigas preenchidas igual). |

**Ações**: `beneficio-tipo-salvar[?tipo_id=]`, `beneficio-tipo-inativar?tipo_id=`,
`beneficio-linha-salvar[?linha_id=][&ativo=nao]`, `beneficio-individual-salvar`. Medido (8203):
```
tipo sem origem → 422 "Origem da regra: obrigatória … regra sem fonte é regra inventada"
tipo desconto sem coef → 422 · rubrica 9999 → 422 "não existe em rubricas_folha"
tipo ok → 200 #97 · editar → 200 · inativar → 200 · inativar 999999 → 422
linha valor sem origem → 422 · linha sem valor → 200 #31 · editar com valor+origem → 200 · inativar → 200
individual sem colaborador → 422 · individual ok → 200 (manual, tipo VT, linha SINETRAM, 22 × R$ 10,00)
beneficio-calcular 2026-09 (motor lendo a regra) → 200 · estados {sem_anterior: 40, sem_modalidade: 41, ok: 21} (= baseline)
GET data/departamento-pessoal → 200 · abas g-beneficios: 15 (… beneficio-tipos, beneficio-tipo-novo, beneficio-linhas, beneficio-linha-nova)
checar_tela_sem_porta (QA_API=8203): TOTAL: 17 sem porta — nenhum de benefício (os 17 são anteriores: mapa-ferias, rep-p-instrumento…)
```
Fixtures (`FIXTURE DGX F3`) apagadas ao fim: tipo #97, linha #31, 1 `employee_benefits`.

## 4. Oráculo — `backend/scripts/orq/test_oraculo_beneficio_regra_e_dado.py`

Afirma: (a) todo tipo ativo tem `tipo_desconto` nos 7 e `origem_regra`; seed VT/VR == `DESC_VT_PCT×100` /
`DESC_VR_PCT×100` com rubrica 1010/1011 existente; exatamente 1 tipo ativo por VT e por VR. (b) todo
`employee_benefits` ativo de VT/VR aponta para tipo ativo do mesmo primitivo. (c) motor com
`gravar=False` reproduz, linha a linha, estado/previsão/quantidade/unitário/total guardados em toda
competência calculada → Σ|Δ total| = 0. (d) nenhuma linha com valor sem origem.

```
ANTES  → FALHOU: tabela beneficio_tipos não existe — a regra ainda mora no código · TOTAL desvios: 1 · exit=1
DEPOIS → tipos ativos: 8 · por primitivo: {VR: 1, VT: 1, cesta: 1, odonto: 1, outro: 3, seguro_vida: 1}
         competências comparadas: 2 · linhas comparadas: 208 · guardadas sem par (fora da coorte): 2 · Σ|Δ total|: R$ 0.00
         TOTAL desvios: 0 · OK benefício regra e dado … · exit=0
CONTRA-PROVA (o motor LÊ a tabela): UPDATE beneficio_tipos SET limite_faltas = 0 WHERE tipo_primitivo='VR'
       → FALHOU: (c) 09/2026 VR 66c823e6: difere em ['estado','qtd','total'] — motor cortado_faltas/15/0/0.00 × guardado sem_anterior/15/15/330.00
         … TOTAL desvios: 76 · exit=1   (revertido; verde de novo: 0)
```
As 2 "guardadas sem par" são linhas de 08/2026 de uma pessoa que saiu da coorte desde o cálculo de 12/09
(dado, não regra) — impressas, não julgadas.

Comando: `run.sh` do contrato com `python3 /app/scripts/orq/test_oraculo_beneficio_regra_e_dado.py`
(a worktree precisa de `backend/logs/` para o servidor HTTP subir com `/app:ro` — dir gitignored).

## 5. O que NÃO foi feito e por quê

- **A folha continua lendo `calculo_service`** (zona de leitura): o desconto do empregado (4%/1%/8,50/2,00)
  na tabela é ESPELHO provado pelo oráculo, não fonte. Trocar a fonte é decisão do dono depois de dois
  meses de paralelo cego verde.
- **Só VT/VR passam pelo motor**. Os outros tipos existem, carregam a regra e a origem, mas nenhum
  motor os lê (cesta/odonto/seguro não entram em `folha_beneficio_conferencia`) — a F1/F2 (evento e CCT
  como dado) é quem os liga.
- **`limite_faltas` usa as faltas do mês ANTERIOR (fechado)**, não do corrente — coerente com o motor
  ("previsão corrigida pelo anterior"). `limite_faltas_justificadas`, `dias_trabalhados_mes`,
  `meses_afastamento_permitido`, `remover_atrasados`, meio período, `desconto_direto_dinheiro`,
  `prevalecer_individual` e os 7 modos de ponto ≠ diária estão **gravados, não aplicados** (o motor não
  distingue justificada/injustificada nem atraso hoje). Aplicar cada um exige regra que não existe em
  código — inventar seria pior que não aplicar.
- **`beneficio_linhas.valor` é R$/dia** (a fonte que existe), não tarifa por passagem como no DGX.
  SINETRAM 27 × R$ 10 ou 30 × R$ 9 continua sem resposta (§7).
- **A tabela `beneficios`** (159 linhas) não mostra as colunas novas (tipo/linha/qtd/unitário) — é
  `tbl()` fixo em `departamento_pessoal.py`; reescrever a query é fora do diff mínimo. Os dados estão no
  banco e no form.
- **40 ativos sem `vt_modalidade`** seguem `sem_modalidade` — cadastro, não regra; não corrigi.
- **Colunas fora do alembic** (`vt_modalidade`, `plano_odonto_*`) — intactas; as minhas também entram
  por `_ensure` (padrão da casa, zona proibida respeitada).
- **`calculo_service.py`, `alembic/`, `frontend/`, `checar_regressao.py`**: não tocados. JSON de menu:
  nada a fazer (abas de grupo existente).

## 6. Como o Jordan testa amanhã

1. DP → **Benefícios & Reembolsos** → aba **Tipos de benefício**: 8 linhas; a coluna Desconto diz
   "% sobre salário · 4% · rubrica 1010" no VT. Clique **Editar** no Vale Refeição → mude "Limite de
   faltas" para 0 → Salvar.
2. Aba **Calcular competência** → `2026-09` → na **Benefício × ponto × portal** aparecem linhas
   `cortado faltas` com R$ 0,00 (é o paralelo cego: a folha não mudou). Volte o limite para vazio e
   recalcule → tudo igual ao de antes.
3. Aba **Linhas de VT**: 2 linhas com R$ 10,00 e a origem. **Nova linha** com valor e sem origem →
   recusa; sem valor → entra e a aba avisa "1 linha sem tarifa".
4. Aba **Adicionar benefício**: escolha colaborador, "Tipo com regra" = Vale Transporte, linha
   SINETRAM, quantidade 22, unitário 10,00 → grava e aparece em **Benefícios**.
5. Terminal (staging): `python3 /app/scripts/orq/test_oraculo_beneficio_regra_e_dado.py` → `TOTAL desvios: 0`.

## 7. Decisões que só o dono pode tomar

1. **SINETRAM: 27 dias × R$ 10 ou 30 × R$ 9?** A linha SINETRAM carrega R$ 10/dia com origem "confirmar
   com a Pyetra". Confirmado → editar a linha com a origem (data, quem).
2. **Quando a tabela vira fonte da folha** (em vez de `calculo_service`): sugestão — depois de 2
   competências com oráculo verde e portal batendo.
3. **Limite de faltas para VR/VT** (o DGX permite; hoje NULL = sem corte). Se a Pyetra corta VT/VR por
   falta injustificada, é uma edição na tela — e aparece na conferência antes de qualquer folha.
4. **Cesta básica / prêmio / PLR**: existem como tipo, sem motor. Quem paga e como desconta?
5. **`nova-beneficio` passou a gravar pela ação nova** (`manual = true`). O `POST /hr/benefits` antigo
   continua vivo para quem o chama por API — manter os dois ou apontar o antigo para cá?
