# DGX W3 — Hora extra classificada: faturada ao cliente × custo nosso × cobertura (24/09/2026)

**Branch:** `dgx/w3-he-classificada` · **Módulo:** ponto (DP) · **Sandbox:** `conecta_pro_staging`,
container `teste-dgx-w3` (porta 8253, **parado e removido ao fim**)

---

## 1. Estado antes — a medição (staging, 24/09/2026 10:00 Manaus)

### Quanta HE existe, e quanto dela tem explicação

| Competência | Dias-pessoa com HE | Horas | Dos quais HE 100% | Pessoas | Com cobertura casada | **Sem explicação** |
|---|---:|---:|---:|---:|---:|---:|
| 08/2026 | 393 | **463,27 h** | 6 | 65 | **0** | **393 (100%)** |
| 09/2026 | 195 | **173,08 h** | 32 | 51 | **0** | **195 (100%)** |
| **Total** | **588** | **636,35 h** | 38 | — | **0** | **588 (100%)** |

Agregado de controle (`time_sheets.overtime_*`), que a soma dia a dia reproduz exata:
08/2026 = 26.351 min a 50% + 1.445 min a 100% = 27.796 min; 09/2026 = 7.009 + 3.376 = 10.385 min.

**Zero cobertura casada não é falha de cruzamento: é ausência de dado.** Medido:
`substitutions` (coberturas da F8) = **0 linhas** no período; `employee_alocacoes` com motivo
`cobertura_*` (movimentação da F5) = **0 linhas** — as 73 alocações existentes são todas
`alocacao_de_vaga`, e nenhuma depois de 23/07. As duas frentes que produzem a prova são de
24/09; ninguém registrou cobertura ainda. Por isso as 588 linhas nascem `falta_de_efetivo`,
**custo nosso** — que é exatamente a régua certa: repassável exige prova.

Estimativa do que isso vale (horas × fator × `time_sheets.hourly_rate`): **R$ 6.057,86** em
08/2026 e **R$ 2.498,57** em 09/2026 — hoje 100% no nosso bolso por falta de justificativa.

### De onde a HE foi lida (a pergunta do brief)

Três candidatos foram medidos:

| Fonte | Tem HE por DIA? | É a que a folha usa? | Veredito |
|---|---|---|---|
| `time_sheets.daily_summary` (espelho, `hr/services/espelho_service.py`) | **sim** — `{date, overtime (min), overtime_type 50\|100, night_real, night_ficta}` | não | **é daqui que se lê** |
| `hr_payslips.earnings` (jsonb do holerite) | não — verba do mês | é o resultado | só serve de paralelo cego |
| `folha_verba_espelho` | não — verba do mês | sim, mas só backfill Portte jan–jun | fora da janela |

**A folha NÃO lê `time_sheets` para HE.** `calculo_service.py` emite a verba **0040 — Horas
Extras 50%** a partir de `horas_reais_ponto()` (agregado do mês sobre `gp_clock_punches`:
excedente acima do divisor da escala), e de jan a jun usa o backfill `folha_verba_espelho`.
São **réguas diferentes** — e é justamente por isso que esta frente **não toca em dinheiro**:
classificar o motivo dia a dia não pode, e não vai, mudar o valor que a folha calcula.
O R$ das telas é **ESTIMATIVA** e as três telas dizem isso com essa palavra.

Achado colateral (não é desta frente, registrado): 6 postos da **Conecta Village** carregam
`posts.contract_id = 801b96b0-…`, e **não existe** linha em `contracts` com esse id — FK órfã.
O serviço só aceita `contract_id` que resolve para um contrato existente; senão cai no único
contrato ativo do cliente do posto, e senão fica sem contrato. Por isso 310 das 393 linhas de
08/2026 ficam em «— (sem contrato)»: o posto não amarra contrato nenhum.

Oráculo no nascimento: **VERMELHO** (`ImportError: cannot import name 'he_classificacao'`).

---

## 2. O que o DGX tem

No fechamento do apontamento (`/Apontamentos` → `Lote/{id}`) existe **`JustificarHoraExtra`**:
a HE do período recebe um carimbo **FATURADA / NÃO FATURADA / COBERTURA** mais um motivo, e o
relatório «HE não acumuladas» sai por aí. É a única peça do DGX que responde *por que aquela
hora extra existiu*. No mapa de lacunas (`docs/dgx/lacunas/ponto.md`) está como **NÃO TEMOS**,
valor médio, com a nota *«HE faturada vs não faturada é dinheiro do cliente»* e a ressalva de
que precisa decisão de dono sobre onde vive.

---

## 3. O que foi feito

| Arquivo | Papel |
|---|---|
| `backend/modules/people_management/ponto/he_classificacao.py` | **novo** — vocabulário (`MOTIVOS`, `TIPOS`, `FATOR`), `_ensure` (DDL), `levantar()`, `confirmar()`, `reclassificar()`, `linhas()`, `resumo_por_contrato()`, `repassavel_por_contrato()`, `competencias()`, `demo()` com asserts |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_w3_he_classificada.py` | **novo** — 3 telas + 3 ações (`router`) |
| `.../redesign_builders/departamento_pessoal.py` | plug `# dgx w3`: import do `router` + `include_router` + `telas(db, out)` no FIM do `build()` |
| `.../redesign_builders/_dp_grupos.py` | 3 abas no **FIM** do grupo `g-ponto` |
| `.../redesign_builders/_frente_07.py` | **só a coluna**: «HE repassável não faturada» em `calculado-vs-faturado` (+1 col, +1 no grid, leitura opcional que nunca derruba a tela) |
| `backend/scripts/orq/test_oraculo_w3_he_classificada.py` | **novo** — oráculo (a)–(f) |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente, roda em `telas()` e em cada ação)

```sql
CREATE TABLE IF NOT EXISTS ponto_he_classificacao (
  id serial PRIMARY KEY,
  employee_id varchar(50) NOT NULL,
  competencia varchar(7) NOT NULL,                -- AAAA-MM
  data date NOT NULL,
  horas numeric(6,2) NOT NULL DEFAULT 0,
  tipo varchar(16) NOT NULL,                      -- he50 | he100 | noturno | intrajornada
  motivo varchar(32) NOT NULL,                    -- ver MOTIVOS abaixo
  repassavel boolean NOT NULL DEFAULT false,
  contrato_id uuid, posto_id uuid, cobertura_id uuid,   -- cobertura_id = F8 (substitutions)
  observacao text,
  classificado_por varchar(120), classificado_em timestamptz,
  origem varchar(12) NOT NULL DEFAULT 'automatica',     -- automatica | manual
  created_at timestamptz DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_he_class ON ponto_he_classificacao (employee_id, data, tipo);
CREATE INDEX IF NOT EXISTS ix_ponto_he_class_comp ON ponto_he_classificacao (competencia, motivo);
```

**Nada mais.** Nenhuma coluna nova em `time_sheets`, `hr_payslips`, `substitutions`,
`employee_alocacoes`, `posts` ou `contracts`; nenhuma semente; nenhum UPDATE/DELETE em dado
que a frente não criou.

### 3.1 A regra da sugestão (e por que ela nunca decide sozinha)

| motivo | rótulo | repassável por padrão |
|---|---|---|
| `cobertura_ferias` · `cobertura_falta` · `cobertura_afastamento` | Cobertura de férias / falta / afastamento | **sim** |
| `pedido_cliente` · `evento_extra` | Pedido do cliente · Evento extra | **sim** |
| `falta_de_efetivo` · `atraso_proprio` · `erro_de_escala` · `outro` | Falta de efetivo · Atraso do próprio · Erro de escala · Outro | **não** |

`levantar(db, "AAAA-MM")` lê a HE do espelho e, **em uma consulta só** (LATERAL joins — por
linha seriam ~1.800 idas ao banco numa competência de 600 dias-pessoa), traz a prova do dia:

1. **Cobertura da F8** (`substitutions` ativa, a pessoa como *substitute*, no dia):
   `vacation → cobertura_ferias`, `afastamento`/`sick_leave → cobertura_afastamento`,
   `no_show → cobertura_falta`. `cobertura_id` e `post_id` vêm dela.
   Os outros `reason` (volante, folga, atividade externa, treinamento…) são escala nossa:
   caem em **`outro`, não repassável**, com o rótulo na observação, para o humano decidir.
2. **Movimentação da F5** (`employee_alocacoes` com motivo `cobertura_de_*` cobrindo o dia) →
   o motivo equivalente. `a_pedido_do_cliente` **não** entra: mover alguém a pedido do cliente
   não prova que a HE daquele dia foi pedida — virar repassável por prova fraca é o erro caro.
3. **Nada** → `falta_de_efetivo`, **não repassável**, com o motivo na observação.

Posto = da cobertura → do turno (`shifts` do dia) → da movimentação. Contrato = `posts.contract_id`
que resolve para contrato existente → o **único** contrato ativo do cliente do posto (cliente com
dois contratos ativos fica sem: escolher seria chutar).

A linha nasce `origem='automatica'` com `classificado_por` **vazio**: é sugestão, não decisão.
Idempotente por `(employee_id, data, tipo)` via `ON CONFLICT DO NOTHING` — rodar de novo não
duplica **e não mexe no que um humano já reclassificou**.

### 3.2 As telas (grupo **Ponto & Jornada**, no fim)

| Tela | Deep-link | O que faz |
|---|---|---|
| `he-classificar` | `/redesign/departamento-pessoal?t=he-classificar` | Lista da competência: Colaborador · Dia · Horas · Tipo · Motivo sugerido · Repasse · R$ estimado · Posto · Contrato · Situação. Filtros **Motivo**, **Repasse**, **Situação**. Ações por linha **Confirmar** e **Reclassificar** (motivo + repassável + observação). Abrir a tela roda `levantar()` (idempotente). |
| `he-classificar-lote` | `…?t=he-classificar-lote` | Form: competência · ação (Confirmar / Reclassificar) · «só as linhas com este motivo» · novo motivo · repassável · observação. É o **em lote por motivo**. |
| `he-por-contrato` | `…?t=he-por-contrato` | Contrato × linhas × horas repassáveis × R$ repassável × horas custo nosso × R$ custo nosso × situação. O sub diz, com essa palavra, que o R$ é **ESTIMATIVA**. |

No CRM, `calculado-vs-faturado` (frente 07) ganhou **só** a coluna «**HE repassável não faturada**»
— leitura do mesmo serviço, na competência do relatório. Se a classificação não existir a coluna
fica «—» e a tela não muda em mais nada. Medido com dado: CTR-2026-00007 R$ 329,44 ·
CTR-2026-00013 R$ 266,49 · CTR-2026-00012 R$ 158,47 · CTR-2026-00011 R$ 108,35.

Ações: `POST /api/v1/redesign/action/he-confirmar?id=` · `he-reclassificar?id=` ·
`he-classificar-lote`. Todas com gate `module:dp`.

### 3.3 HTTP no container efêmero (8253, sandbox, admin `jjesus`)

```
GET /api/v1/redesign/data/departamento-pessoal → 200 · 130 telas · g-ponto com 25 abas
  he-classificar      "HE: classificar — 09/2026" · 195 linhas
      sub: "195 dia(s)-pessoa de hora extra (173.15h) · 195 aguardando confirmação ·
            0 repassável(is) ao cliente (0.00h ≈ R$ 0,00 ESTIMADO) · 195 sem explicação…"
      1ª linha: ADAILSON SERRA ALVES · 03/09/2026 · 0.02h · HE 50% · Falta de efetivo ·
                Custo nosso · R$ 0,28 · Residencial Laranjeiras · CTR-2026-00011 · sugestão
                ações [Ver, Confirmar, Reclassificar]
  he-classificar-lote form com 6 campos
  he-por-contrato     7 agrupamentos · repassável R$ 0,00 · custo nosso R$ 2.498,57

 1. POST he-confirmar?id=3210                          → 200 "Classificação confirmada — horas e valor não mudaram."
 2. POST he-confirmar?id=999999                        → 404 "Linha de HE não encontrada."
 3. POST he-reclassificar?id=3211 motivo=pedido_cliente→ 200 · SQL: motivo=pedido_cliente, origem=manual
 4. POST he-reclassificar?id=3211 cobertura_ferias + repassavel=0
                                                       → 200 · SQL: motivo=cobertura_ferias, repassavel=FALSE
                                                         (o humano vence a regra do motivo — de propósito)
 5. POST he-reclassificar?id=3211 motivo="faturada"     → 400 "Motivo inválido: 'faturada'. Use um de …"
 6. POST he-classificar-lote {09/2026, confirmar, falta_de_efetivo}
                                                       → 200 "193 linha(s) confirmada(s) … nenhuma hora e nenhum valor mudou."
 7. POST he-classificar-lote {09/2026, reclassificar, sem motivo novo} → 400 "Motivo inválido: ''…"
 8. POST he-classificar-lote {2026-13, confirmar}       → 400 "Competência inválida: '2026-13' (use AAAA-MM)."
 9. POST he-classificar-lote {09/2026, acao=nada}       → 400 "Escolha Confirmar ou Reclassificar."
10. lote reclassificar 194 linhas → pedido_cliente · GET /redesign/data/crm → coluna «HE repassável
    não faturada» preenchida (R$ 329,44 · 266,49 · 158,47 · 108,35 · «—» onde não há linha)
Ao fim: competências 08 e 09/2026 devolvidas ao estado natural (588 linhas `falta_de_efetivo`,
nenhuma confirmada); container `teste-dgx-w3` parado e removido.
```

---

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
        | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w3_he_classificada.py
# em produção: docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_w3_he_classificada.py
# checagem local das partes puras: python3 backend/modules/people_management/ponto/he_classificacao.py
```

**ANTES** (24/09 10:05, antes de escrever o serviço):
```
  ✗ (a–f) serviço da W3 não importa: ImportError: cannot import name 'he_classificacao' from 'modules.people_management.ponto'
TOTAL falhas W3 HE classificada: 1
```

**DEPOIS** (24/09 10:19):
```
  ✓ (a) linhas classificadas = HE do espelho: 393 == 393 · horas 463.25 == 463.25
  ✓ (a) nenhuma tripla (pessoa, dia, tipo) repetida: 0
  ✓ (b) levantar 2×: novas=0 (esperado 0) · linhas 393→393 · horas 463.25→463.25
  ✓ (e) automáticas repassáveis sem cobertura nem movimentação: 0 (esperado 0)
  ✓ (e) HE sem cobertura/movimentação nasce: falta_de_efetivo repassável=False
  ✓ (f) horas do resumo == horas das linhas: 463.25 == 463.25 (6 agrupamentos)
  ✓ (f) R$ do resumo == R$ recontado das linhas: 6057.86 == 6057.87
  ✓ (c) HE no dia de cobertura de férias → cobertura_ferias repassável=True
  ✓ (c) cobertura_id da linha == cobertura recontada por SQL (vacation): 431cac2f-… == 431cac2f-…
  ✓ (d) confirmar 393 linha(s): horas 1.00 → 1.00, motivo intacto (cobertura_ferias)
  ✓ (d) paralelo cego na folha: 65 holerite(s) em 2026-08, Σ|Δ| = R$ 0.00 (esperado 0,00)
  ✓ (d) HE do espelho intacta: 50%=26351→26351 min · 100%=1445→1445 min
  ✓ fixtures apagadas ao fim: 0 sobrando
TOTAL falhas W3 HE classificada: 0
```

**Vizinhos, no mesmo backend, depois:**
```
test_oraculo_calculado_vs_faturado.py        → "OK calculado × faturado: cada contrato ativo tem os
                                                dois números …, e nenhum contrato mudou" (exit 0)
test_oraculo_operacional_dgx.py (F8)         → TOTAL falhas operacional DGX F8: 0
test_oraculo_u1_movimentacao_supervisao.py   → TOTAL falhas U1 movimentação/supervisão: 0
```
`ruff check` limpo nos 6 arquivos tocados. Fixtures `'FIXTURE DGX W3'` (em `substitutions.notes`)
apagadas no `finally`; o oráculo também desfaz a própria assinatura (`classificado_por = 'oráculo W3'`).

---

## 5. O que NÃO foi feito e por quê

- **`tipo = noturno` e `tipo = intrajornada` existem na tabela, mas `levantar()` não os cria.**
  O espelho tem hora noturna por dia (`night_real`/`night_ficta`), mas noturno e intrajornada
  são adicionais **habituais da escala** (a folha os paga por plantão agendado, decisão do
  Jordan de 04/08), não hora extra que alguém pediu. Classificá-los automaticamente encheria a
  tela de 588 → ~4.000 linhas sem nenhuma decisão de repasse por trás. Os dois valores ficam no
  vocabulário para reclassificação manual quando o dono quiser tratá-los.
- **Nenhum abatimento do que já foi faturado.** A coluna do CRM chama-se «HE repassável **não
  faturada**», mas nenhuma NFS-e discrimina HE (medido: itens de serviço só com o código 11.02
  do contrato). Então não há o que abater e a coluna mostra a estimativa cheia — e diz isso.
- **A folha não foi tocada.** `calculo_service.py`, `horas_service.py` e `espelho_service.py`
  estão byte a byte como estavam. Classificar não muda um centavo — é o (d) do oráculo.
- **Nenhum gatilho automático.** `levantar()` roda quando a tela abre; não entrou no beat.
  Se o volume crescer, uma task diária é uma linha — mas hoje seria infraestrutura para um caso.
- **`a_pedido_do_cliente` (F5) não vira sugestão** (§3.1, item 2).
- **Nada no frontend.** As três telas são `table`/`form` genéricos e o CRM só ganhou coluna.
- **A FK órfã da Conecta Village** (`posts.contract_id` sem linha em `contracts`) foi **contornada,
  não corrigida** — não é dado desta frente e consertar exigiria decidir qual contrato é.

---

## 6. Como o Jordan testa amanhã

1. `/redesign/departamento-pessoal` → grupo **Ponto & Jornada** → aba **HE: classificar**.
   Abre já na competência mais recente com HE. Confere no subtítulo: quantos dias-pessoa,
   quantas horas, quantos repassáveis e quantos «sem explicação».
2. Filtre por **Repasse = custo nosso** e olhe uma linha: **Reclassificar** → escolha
   *Pedido do cliente*, escreva o que o síndico pediu, grave. A linha vira repassável.
3. Aba **HE: confirmar/reclassificar em lote**: competência, ação *Confirmar*, motivo
   *Falta de efetivo* → assina todas de uma vez. Nenhuma hora e nenhum valor mudam (a mensagem
   diz isso e o oráculo prova contra os holerites).
4. Aba **HE por contrato**: quanto de HE cada contrato carrega, repassável × custo nosso.
   O R$ é estimativa — está escrito na tela.
5. `/redesign/crm` → **Calculado × Faturado**: a coluna «HE repassável não faturada» mostra,
   por contrato, o que o DP marcou como do cliente e ninguém cobrou.
6. Confira o holerite de qualquer pessoa em `/redesign/departamento-pessoal?t=folha` antes e
   depois: o valor é o mesmo.

---

## 7. Decisões que só o dono pode tomar

1. **Cobertura de FALTA é repassável?** Hoje a sugestão diz que sim (o brief manda), mas manter
   o posto coberto quando um agente falta pode ser obrigação contratual nossa — nesse caso
   `cobertura_falta` deveria nascer **custo nosso**. É um `MOTIVOS["cobertura_falta"] = (…, False)`.
   As outras oito classificações não mudam.
2. **A HE repassável vira cobrança?** Esta frente só mostra o número. Transformá-lo em item de
   NFS-e ou aditivo é decisão comercial — e é o que fecharia o laço com a frente 07 (10 de 15
   contratos faturados abaixo do custo calculado).
3. **Quem confirma?** Hoje qualquer usuário com `module:dp`. Se a classificação vai virar
   argumento de cobrança, talvez deva exigir o gerente operacional ou o próprio dono.
4. **Noturno e intrajornada entram na classificação?** (§5). Hoje não.
5. **Os postos da Conecta Village** apontam para um contrato que não existe — 310 das 393 linhas
   de 08/2026 ficam sem contrato por causa disso. Qual contrato é o certo?
