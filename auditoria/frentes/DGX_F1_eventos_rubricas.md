# DGX F1 — Eventos/rubricas como dado (24/09/2026)

**Branch:** `dgx/f1-eventos-rubricas` (base `c7077dbb6`, fase5-hermes-camada-cognitiva)
**Módulo:** folha (cadastro `rubricas_folha`) + telas do redesign do DP · **Sessão:** agent-f1
**Paralelo cego.** O motor `calculo_service.py` NÃO foi tocado. Nenhuma escrita em produção.
DDL idempotente aplicada só no sandbox (`_ensure`); em produção acontece no 1º acesso à aba.

## 1. Estado antes (medido no sandbox = cópia de produção de 23/09)

- `rubricas_folha`: 24 linhas, 21 colunas (codigo, descricao, tipo, natureza, base_calculo, percentual,
  valor_fixo, incide_inss/irrf/fgts, ativo, esocial_*). Produção: os mesmos 24 códigos.
- A aba **Rubricas** (`folha-rubricas`, g-folha) **não lia esta tabela**: era um `unnest` do JSON dos
  holerites lendo as chaves `description`/`value` (formato Portte) — para holerite `conecta` (chaves
  `descricao`/`valor`) mostrava "—" e R$ 0. Não havia editar/inativar/incluir.
- Holerites de 09/2026 (`source_system='conecta'`, 51 pessoas, status `draft` — não há `published`
  em 09; o último publicado do motor próprio é 07/2026): 20 rubricas distintas. **8 sem linha no
  cadastro** (0016, 0018, 0031, 0095, 0937, 1045, 1051, 1053 — R$ 48.429 em linhas) e **4 com
  outro significado** no cadastro (0060 "Vale Refeicao" × holerite "Ferias"; 0061 "Vale Transporte"
  × "1/3 Ferias"; 1002 "IRRF" × "INSS Ferias"; 0030 "Intrajornada Nao Concedida" ≈ "Intrajornada
  Diurno"). No caminho do espelho (jan–jul) mais 3: 0040 ronda × HE 50%; 0050/0051 insalubridade/
  periculosidade × afastamento; 0070 13º × Horas Extras.
- Base INSS/FGTS/IRRF recomposta pelas flags do cadastro ≠ gravada em **31 de 51** holerites,
  **Σ|Δ| = R$ 7.897,21** (as três verbas sem linha que o motor soma na base: 0016/0018/0031).

Oráculo VERMELHO (sandbox, antes de qualquer código):
```
$ python3 /app/scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py
competência 09/2026 · 51 holerites · 20 rubricas usadas · cadastro 24 linhas · divergência de base: INSS 31 (Σ|Δ| R$ 7.897,21), FGTS 31 (Σ|Δ| R$ 7.897,21), IRRF 31 (Σ|Δ| R$ 7.897,21)
FALHOU: builder _dgx_f1_rubricas não importa: cannot import name '_dgx_f1_rubricas' ...
FALHOU: (a) 0016/provento aparece em 11 holerite(s) (R$ 1.851,50) e não existe em rubricas_folha
FALHOU: (a) 0018/provento aparece em 15 holerite(s) (R$ 3.792,76) e não existe em rubricas_folha
FALHOU: (a) 0031/provento aparece em 9 holerite(s) (R$ 2.252,95) e não existe em rubricas_folha
FALHOU: (a) 0095/provento aparece em 11 holerite(s) (R$ 1.121,16) e não existe em rubricas_folha
FALHOU: (a) 0937/desconto aparece em 1 holerite(s) (R$ 343,30) e não existe em rubricas_folha
FALHOU: (a) 1045/desconto aparece em 51 holerite(s) (R$ 34.473,71) e não existe em rubricas_folha
FALHOU: (a) 1051/desconto aparece em 19 holerite(s) (R$ 2.575,28) e não existe em rubricas_folha
FALHOU: (a) 1053/desconto aparece em 12 holerite(s) (R$ 2.018,58) e não existe em rubricas_folha
FALHOU: (b) ADAILSON SERRA ALVES: base INSS gravada R$ 2.425,10 ≠ recomposta R$ 2.174,60
FALHOU: (b) ADAILSON SERRA ALVES: base FGTS gravada R$ 2.425,10 ≠ recomposta R$ 2.174,60
FALHOU: (b) ADAILSON SERRA ALVES: base IRRF gravada R$ 2.231,16 ≠ recomposta R$ 1.980,66
... (AILTON, ADEMIR) ...
FALHOU: (b) … e mais 28 holerite(s) com base INSS divergente
FALHOU: (b) … e mais 28 holerite(s) com base FGTS divergente
FALHOU: (b) … e mais 28 holerite(s) com base IRRF divergente
FALHOU: (c) rubricas_folha sem as colunas do DGX: periodo, tipo_dia, credito, soma_ao_evento, ... origem_regra
TOTAL rubricas dizem a verdade: 22 falha(s)
exit=1
```

## 2. O que o DGX tem

Evento com 40 atributos (`docs/dgx/01` §Eventos, `docs/dgx/09`): código, descrição, período
(dias/horas/mês), tipo de dia (normal, falta justificada/não, folga, crédito, atividade externa),
crédito (soma/subtrai), soma ao evento (hora trabalhada/extra/extra 100/noturna/noturna reduzida/
atraso/adicional feriado/intrajornada), soma ao ponto, banco de horas (não/soma/subtrai), desconta
benefício + qual, exporta evento + código auxiliar, incidências (fgts/inss/irrf/dsr/13º/média 13º/
periculosidade), base (salário base/mínimo), razão, razão noturna, vale, ausência, hora extra,
considerar descanso, remover ponto calculado, remover diária, comercial, porcentagem/valor.
Ponto, folha e benefício conversam por ele. Aqui isso é código em `calculo_service.py`.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f1_rubricas.py` (novo) | `_ensure(db)`: 25 × `ALTER TABLE rubricas_folha ADD COLUMN IF NOT EXISTS` + 11 `INSERT … ON CONFLICT (codigo) DO NOTHING` (códigos que o motor emite sem linha) + semente dos atributos DGX nas 35 rubricas **só onde `origem_regra IS NULL`** (o que o dono editar nunca é sobrescrito). `telas(db, out)`: sobrescreve `folha-rubricas` e cria `folha-rubrica-nova`. `router`: `POST /api/v1/redesign/action/rubrica-salvar` e `rubrica-inativar`. |
| `backend/scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py` (novo) | Oráculo (§4). |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`), 2 linhas antes de `montar_grupos(out)` (`telas`), comentário `# dgx f1`. |
| `.../redesign_builders/_dp_grupos.py` | 1 tupla no g-folha: `("folha-rubrica-nova", "Nova rubrica")`. |

**DDL que `_ensure` aplica em produção no 1º acesso** (idempotente; sem DEFAULT — NULL = "ninguém
disse", o oráculo (c) acusa):
```
ALTER TABLE rubricas_folha ADD COLUMN IF NOT EXISTS periodo text, tipo_dia text, credito text, soma_ao_evento text,
  soma_ao_ponto boolean, banco_horas text, desconta_beneficio boolean, tipo_beneficio_descontado text,
  exporta_evento boolean, codigo_exportacao text, incide_dsr boolean, incide_13 boolean, media_13 boolean,
  base text, razao numeric(12,4), razao_noturna numeric(12,4), vale boolean, ausencia boolean, hora_extra boolean,
  considerar_descanso boolean, remove_ponto_calculado boolean, remove_diaria boolean, comercial boolean,
  porcentagem_ou_valor text, origem_regra text          -- (um ALTER por coluna)
INSERT ... ON CONFLICT DO NOTHING: 0015 Periculosidade, 0016 Insalubridade, 0018 Ronda, 0031 Intrajornada Noturna,
  0062 Vantagens Ferias, 0095 Salario Familia, 0937 Adiantamento de Ferias (desconto), 1040 Consignado/Pensão,
  1045 Desc. Adiantamento Salarial, 1051 Faltas, 1053 DSR sobre Faltas
UPDATE rubricas_folha SET <25 atributos> WHERE codigo = :cod AND origem_regra IS NULL   -- 35 códigos
```
Nada de DROP/DELETE/UPDATE nas colunas que já existiam (codigo, descricao, tipo, incide_*): as
colisões de código ficam registradas em `origem_regra` e visíveis na tela (coluna "Descrição no
holerite"), não corrigidas — §7.

**Telas** (deep-links `/redesign/departamento-pessoal?t=folha-rubricas` e `?t=folha-rubrica-nova`;
abas "Rubricas" e "Nova rubrica" em Folha de pagamento):
- `folha-rubricas` (table, 35 linhas): Código · Descrição · Tipo · Período·base · Razão · Incide
  (INSS·IRRF·FGTS) · Reflexos (DSR·13º·média) · Cód. contador (Portte) · **Uso na competência**
  (n × R$, medido nos holerites) · **Descrição no holerite** ("bate" / "no holerite: Ferias" /
  "não emitida") · Status. Por linha: **Editar** (modal com os 32 campos, POST rubrica-salvar com
  `id`) e **Inativar/Reativar** (POST rubrica-inativar). Filtro ativas/inativas.
- `folha-rubrica-nova` (form, 32 campos): código, descrição, tipo, natureza, período, tipo do dia,
  base, %/valor, razão, razão noturna, fórmula, incide INSS/IRRF/FGTS/DSR/13º/média, soma ao
  evento/ponto, banco de horas, hora extra, ausência, vale, considerar descanso, remove ponto/diária,
  desconta benefício + qual, comercial, exporta + código no contador, **origem da regra (obrigatória)**.

**Validações da ação `rubrica-salvar`**: código `[A-Z0-9]{1,10}` único (409 se existir em outro
id), descrição ≥ 3, tipo ∈ {provento, desconto}, natureza ∈ check da tabela, todos os enums do DGX
fechados (400 com a lista), razão numérica (aceita vírgula), `desconta_beneficio=sim` exige `qual`,
`origem_regra` obrigatória (≥ 5). `credito` derivado do tipo. `percentual`/`valor_fixo` (colunas
antigas) derivados de razão + %/valor para o `get_rubricas` legado continuar coerente.
**`rubrica-inativar`**: alterna `ativo`; **nunca apaga**; recusa (409) inativar rubrica presente nos
holerites da competência corrente ("0001 está em 51 holerite(s) de 09/2026").

**Semente — de onde veio cada valor** (`origem_regra`, resumo; o texto completo está na tabela):
| Código | Atributos semeados | Origem |
|---|---|---|
| 0001 | dias, soma, 13º, razão 1, Portte 1 | `calculo_service` L428; proporcional L340-360; piso L296-310 |
| 0020 | horas, soma ao evento hora_noturna, 13º+média, razão 0,20, Portte 246 | L672-700 (escala 7h/plantão L149; DSR não reflete L757) |
| 0021 | horas, hora_noturna_reduzida, hora extra, razão 1,8 / 2,025 c/ ronda, Portte 247 | L702-722 |
| 0030 / 0031 | horas, intrajornada, hora extra, razão 1,5 / 1,8, Portte 244/245 | L727-750; `employees.recebe_intrajornada` |
| 0016 / 0018 / 0015 | mês, 13º, razão 0,10 / 0,15 / 0,30, Portte 223/224 | L636-649 / L652-665 / L622-635; CCT Cl. 23ª |
| 0090 | dias, 13º+média, razão 1/6, Portte 250 | L751-770; `fator_dsr` L189-215 |
| 0095 | valor 67,54, sem incidência, Portte 995 | L777-800; Lei 8.213 art. 66 |
| 0060/0061/0062/0937 (férias) | dias; 0937 = vale | L448-496; art. 129/142/145 CLT |
| 1001 / 1002 | %, Portte 998 / — | L806-826 / L828-850; Portaria MPS/MF 13/2026; Lei 15.270/2025 |
| 1010 / 1011 | desconta benefício VT / VR, razão 0,04 / 0,01, Portte 48 / 9383 | L852-874; CCT 2026 |
| 1020 | desconta benefício odonto, razão 8,50, Portte 202 | L876-904; Pyetra 09/09/2026 |
| 1030 | valor 22, Portte 264 | L908-918; meses ímpares |
| 1045 | vale, razão 0,40, Portte 981 | L952-1000; regra do Jordan 22/09/2026 |
| 1051 / 1053 | dias, falta não justificada, ausência, remove ponto/diária, desconta VT, DSR, Portte 8792/8794 | L531-602; Lei 605/49 art. 6º |
| 0010/0011/0041/0070/0071/0080/0100/1021/0040/0050/0051 | do próprio `base_calculo` do cadastro 03/2026 | "cadastro 03/2026" + a colisão/ausência no motor, quando há |

## 4. Oráculo — `backend/scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py`

Afirma, na ÚLTIMA competência `conecta` até o mês corrente (nasceu em 09/2026): (a) toda (código,
tipo) do holerite existe em `rubricas_folha`, ativa, mesmo tipo; (b) por holerite, base INSS =
Σ proventos `incide_inss` − Σ descontos `incide_inss`, FGTS idem, IRRF = Σ proventos `incide_irrf`
− INSS retido (linha 1001, dedução legal — art. 4º Lei 9.250/95, não é flag), tolerância R$ 0,01,
recontado por SQL próprio; (c) nenhum atributo DGX NULL em rubrica ativa; (d) `origem_regra`
preenchida; (e) fiação (build do DP chama a frente; abas em `_dp_grupos`).

Comando (container efêmero, worktree RO, banco do sandbox):
```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py
```
VERDE (depois do 1º GET da tela ter rodado `_ensure` no sandbox):
```
competência 09/2026 · 51 holerites · 20 rubricas usadas · cadastro 35 linhas · divergência de base: INSS 0 (Σ|Δ| R$ 0,00), FGTS 0 (Σ|Δ| R$ 0,00), IRRF 0 (Σ|Δ| R$ 0,00)
OK rubricas dizem a verdade: toda rubrica do holerite existe e ativa, bases INSS/FGTS/IRRF recompostas pelas flags, atributos DGX preenchidos com origem
TOTAL rubricas dizem a verdade: 0
exit=0
```

Prova por HTTP (container `teste-dgx-f1`, porta 8201, parado ao fim):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-folha tabs: [... ('folha-rubricas', 'Rubricas'), ('folha-rubrica-nova', 'Nova rubrica'), ...]
folha-rubricas: table · 35 rows · cols [Código, Descrição, Tipo, Período · base, Razão, Incide, Reflexos, Cód. contador, Uso 09/2026, Descrição no holerite, Status]
  ['0001','Salario Base','provento','dias · salario base','1','INSS·IRRF·FGTS','13º','1','51 × R$ 85.237,95','bate','ativa'] edit=True actions=['Inativar']
  divergem do holerite: 0030 (Intrajornada Diurno), 0060 (Ferias), 0061 (1/3 Ferias), 1002 (INSS Ferias)
folha-rubrica-nova: form · 32 fields · submit rubrica-salvar
POST rubrica-salvar (ZZ99, origem 'FIXTURE DGX F1') → 200 id 47 · repetir → 409 · tipo 'x' → 400 · sem origem → 400
POST rubrica-salvar (id 47, editar) → 200 · rubrica-inativar 47 → 200 inativada · de novo → 200 reativada
POST rubrica-inativar (0001) → 409 "0001 está em 51 holerite(s) de 09/2026 — inative depois de fechar a competência."
```
A fixture ZZ99 foi apagada do sandbox ao fim (`DELETE … WHERE origem_regra LIKE 'FIXTURE DGX F1%'`).

## 5. O que NÃO foi feito e por quê

- **O motor não lê o cadastro.** `calculo_service.py` segue com as regras em código (caminho de
  dinheiro; Σ|Δ| = 0 garantido por não tocar). O cadastro é a *descrição fiel* do motor, provada
  pelo oráculo. Ligar o motor às flags (INSS/FGTS/IRRF/DSR pela tabela) é a F1-b, com o mesmo oráculo
  como trava.
- **Não renomeei/corrigi os 24 registros antigos** (descrição, tipo, incidências): dado que não
  criei. As 4 colisões visíveis (0060, 0061, 1002, 0030) e as 4 do espelho (0040, 0050, 0051, 0070)
  estão em `origem_regra` e na coluna "Descrição no holerite". §7.
- **Verbas do caminho do espelho** (0052, 1050, 1052, 1054, 1060, 1061, 1062 — jan–jul/2026, fonte
  `folha_verba_espelho`) não foram inseridas: o cadastro delas é a própria tabela do espelho, com
  `incide_inss` por linha; e o motor deixa de emiti-las quando `USAR_ESPELHO_PORTTE` virar `False`.
- **`incide_inss` de 1051/1053 (faltas) = false**, porque é o que o motor faz hoje going-forward
  (§7.1) — a lei diz o contrário. Preferi o cadastro dizer a verdade do motor e o relatório dizer a
  verdade da lei, a fazer o oráculo ficar verde com uma flag que o motor ignora.
- **`codigo_exportacao`** = código da Portte observado nos holerites importados de 2026 (998, 246,
  247, 244/245, 223, 224, 995, 981, 8792/8794, 48, 9383, 202, 264, 937, 250). IRRF, periculosidade
  e HE 100% ficaram '' (não observados). O exportador Domínio (`payroll_export_service`) usa os
  NOSSOS códigos — não foi alterado.
- **DGX `periculosidade`, `holerith`, `rendimentoBruto`, `digiexpress`, `suspensao`, `finalidade`,
  `naoVizualizarPonto`, `exportarEmFolga`**: sem equivalente aqui (ou redundante com `incide_*`);
  não criei coluna para atributo que ninguém lê.
- **13 rubricas ativas que o motor nunca emite** (0010, 0011, 0040, 0041, 0050, 0051, 0060, 0061,
  0070, 0071, 0080, 0100, 1021): não inativei (é UPDATE em dado que não criei). Aparecem como "não
  emitida" na tela; o botão Inativar está a um clique.
- **Frontend**: nada. `table` + `edit`/`actions` + `form` renderizam genericamente; abas vêm do
  `_dp_grupos` (o front lê o grupo do backend).
- **`checar_regressao.py`**: nada — `scripts/orq/test_*.py` é globado pela meia-noite.
- Teste HTTP precisou de `--tmpfs /app/logs:mode=1777 --tmpfs /app/uploads:mode=1777` (a worktree
  RO em `/app` não deixa o loguru criar `/app/logs`; o contrato não menciona). `backend/logs` é
  ignorado pelo git; `backend/uploads` foi removido ao fim.

## 6. Como o Jordan testa amanhã

1. Depois do bake: Departamento Pessoal → **Folha de pagamento** → aba **Rubricas**
   (`/redesign/departamento-pessoal?t=folha-rubricas`). Subtítulo: "35 rubricas (35 ativas) · uso
   medido nos holerites de 09/2026". A coluna "Uso 09/2026" mostra 51 × R$ 85.237,95 no 0001.
2. Coluna "Descrição no holerite": 4 linhas em amarelo (0030, 0060, 0061, 1002) — é a colisão de
   código do §7.2, não defeito da tela.
3. Clicar **Editar** no 1010 (Desconto VT): modal com 32 campos, "Desconta benefício = sim / Qual =
   vale transporte / Razão 0,04 / Origem: calculo_service L852-862". Mudar só "Origem" e salvar →
   "Rubrica 1010 atualizada". A semente não sobrescreve o que você editou (só preenche NULL).
4. Clicar **Inativar** no 0001 → recusa: "0001 está em 51 holerite(s) de 09/2026". Inativar o
   0011 (HE 100%, nunca emitida) → "inativada"; ela desce para o filtro "inativas"; clicar de novo
   reativa.
5. Aba **Nova rubrica**: preencher código `0017`, descrição, tipo, origem → "cadastrada". Repetir
   com o mesmo código → "já existe". (Cadastrar não faz o motor calculá-la — está escrito no
   subtítulo.)
6. Oráculo no container de produção: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3
   /app/scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py` → `TOTAL ...: 0`. Se sair vermelho em
   (a), alguém inativou/apagou rubrica em uso; em (b), o motor passou a somar/tirar algo da base que
   o cadastro não sabe — e é ISSO que a tela existe para não deixar acontecer em silêncio.

## 7. Decisões que só o dono pode tomar (com os números)

1. **Faltas não reduzem a base do INSS no motor going-forward.** Em 09/2026, 19 pessoas tiveram
   1051 Faltas (R$ 2.575,28) e 12 tiveram 1053 DSR s/ faltas (R$ 2.018,58) — R$ 4.593,86 que a lei
   (salário-de-contribuição = remuneração efetivamente devida) tira da base, e `base_inss` (L806-817)
   não tira. No caminho do espelho (jan–jul) o mesmo motor tira (L524-525). Consequência: INSS do
   empregado e FGTS (8% de R$ 4.593,86 = R$ 367,51) calculados a maior em setembro. Corrigir é
   mudar o motor (não fiz). O cadastro hoje diz `incide_inss=false` para 1051/1053 (verdade do
   motor); ao corrigir o motor, virar as duas flags e o oráculo continua verde.
2. **Colisões de código — `codRubr` é chave no eSocial (S-1010/S-1200).** O motor e a tabela usam
   o mesmo código para coisas diferentes: 0040 (tabela ronda / motor HE 50%), 0050 e 0051 (tabela
   insalubridade e periculosidade / espelho afastamento ≤15d e afastamento INSS — 6 e 1 holerites em
   07/2026), 0060 e 0061 (tabela VR e VT / motor Férias e 1/3 Férias), 0070 (tabela 13º 1ª parcela /
   espelho Horas Extras — 20 holerites em 07/2026), e **1002 usado pelo próprio motor para IRRF
   (L843) e INSS Férias (L481)**. Decisão: renumerar no motor (0040→0010, 0015/0016→0051/0050 ou
   vice-versa, INSS Férias→1060 como a Portte) ou renomear as linhas da tabela. Qualquer um dos dois
   é uma mudança no caminho do dinheiro/eSocial; o oráculo acusa se ficar pela metade.
3. **07/2026 (publicado) não fecha com o cadastro: 37 de 51 holerites, Σ|Δ| = R$ 2.690,32.** É o
   caminho do espelho: `folha_verba_espelho.incide_inss` manda (faltas subtraem, 0070 HE incide,
   0050 afastamento incide) e 7 códigos (0052, 1050, 1052, 1060, 1061 + 1054/1062 em outros meses)
   não têm linha. Enquanto `USAR_ESPELHO_PORTTE = True`, o cadastro descreve só o going-forward.
   O oráculo mede a competência corrente de propósito.
4. **Insalubridade sobre salário base, não sobre o mínimo** (NR-15 / Súmula Vinculante 4 — base
   salário mínimo salvo negociação). O motor (L636-649) e a folha da Portte (223 = 10% do salário
   base) usam a base; o cadastro antigo dizia `salario_minimo`. Semeei `base = salario_base`
   (verdade do motor). Se a CCT não fixar a base, é passivo para o lado que se paga a MAIS (R$ 1.851
   em 09/2026 sobre 11 pessoas; sobre o mínimo seriam R$ 1.783 — diferença R$ 68/mês).
5. **13 rubricas ativas que o motor nunca emitiu** (lista no §5): inativar pela tela ou manter como
   "reserva". Enquanto ativas, o `GET /hr/payroll/rubricas` e a tool `listar_rubricas_folha` do
   Hermes as listam como se existissem.
6. **Ligar o motor ao cadastro (F1-b)**: só depois de 1 e 2. Ordem: motor lê `incide_inss/irrf/fgts`
   da tabela → oráculo verde contra 09/2026 com Σ|Δ| = 0 → então `incide_dsr`, `soma_ao_evento` e
   `desconta_beneficio` passam a alimentar ponto (F7) e benefício (F3).
