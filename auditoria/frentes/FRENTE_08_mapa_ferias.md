# FRENTE 08 — Mapa de férias por idade do período aquisitivo (12/09/2026)

**Branch:** `frente/08-mapa-ferias` (base `30be528a3`, a mesma das frentes 03/04)
**Módulo:** hr (serviço) + tela do redesign do DP · **Sessão:** tmux-agente-08
**Só leitura.** Nenhuma escrita em produção. Nenhum DDL.

## 1. Estado antes (medido no staging)

- Tela/rota do mapa: **não existia** (benchmark 9.5: "férias sim, faixas não").
- `hr_vacation_periods` (67 linhas, 52 pessoas): **todas semeadas por calendário** em 22–28/03/2026
  (start 2025-01-01 ou 2026-01-19, sem relação com a admissão), `days_used = 0` em 100%,
  `is_fully_used = false` em 100% — inclusive para as 5 pessoas com férias APROVADAS em
  `hr_vacation_requests` (todas com `period_id NULL`). A tabela de períodos não é alimentada pelo
  fluxo de aprovação. Exemplo: AILTON (adm. 22/10/2023) tem `limit_date = 2028-01-19` no ERP; o
  limite legal do 1º período era 21/10/2025.
- `sst_afastamentos`: 8 linhas, nenhuma com retorno > 6 meses → sem caso real para a contra-prova
  do art. 133. Montei fixture no staging (ver §2).
- Ativos com vínculo (régua abaixo): 53 no início; 55 no fim da noite (a frente 05 inseriu
  `ZZ_TESTE_F05_VALIDO/VENCIDO` sem `data_admissao` — caíram em "não calculado", como deve).

Oráculo VERMELHO (staging, antes de qualquer código):
```
$ python3 /app/scripts/orq/test_oraculo_mapa_ferias.py
FALHOU: serviço hr/services/mapa_ferias.py não importa: cannot import name 'mapa_ferias' from 'modules.people_management.hr.services'
exit=1
```

## 2. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_mapa_ferias.py` (novo) | Oráculo: (1) tela fiada no `build()` do DP; (2) soma das 7 faixas == ativos com vínculo por SQL próprio; (3) sem default — `faixa(0)` = em aquisição, `faixa(None)` = não calculado, fronteiras da DGX, e o fonte do serviço não tem `or <número>`; (4) contra-prova da âncora: pura (afastamento longo → retorno; curto → admissão; sem admissão → None) e de banco (âncora do serviço == recalculada por SQL direto em `sst_afastamentos`, pessoa a pessoa). |
| `backend/modules/people_management/hr/services/mapa_ferias.py` (novo) | `faixa(idade_meses)`, `ancora_periodo(admissao, afastamentos)` (docstring cita art. 133 IV e §2º), `situacao(...)` pura, `mapa(db)` (uma linha por pessoa: âncora, início do período aberto, idade em meses, faixa, direito/usados/restantes, limite legal, `limite_erp`, dias para o limite, risco de dobra, vencida). `demo()` com asserts. |
| `backend/modules/operacional/controllers/redesign_builders/_frente_08.py` (novo) | Tela `mapa-ferias` (type=table): lista por pessoa ordenada pelo risco + 3 painéis — legenda por faixa com contagem (formato DGX), "vence em 30/60/90 dias" nominal, "> 22 meses" nominal. |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas antes do `return out`, comentário `# frente 08`. |
| `sst_afastamentos` (STAGING, dado, não código) | Fixture: EDWARD JOSÉ ATENCIO DOMINGUEZ, doença 10/01/2025 → retorno 20/08/2025 (7 m 10 d), `encaminhado_inss = true`, `observacoes = 'FIXTURE FRENTE 08 — contra-prova art. 133 (staging)'`. Apagar com `DELETE FROM sst_afastamentos WHERE observacoes LIKE 'FIXTURE FRENTE 08%'` quando não servir mais. |

### Regras aplicadas (decisões do contrato, não reabertas)
- **Âncora** = maior entre admissão e retorno de afastamento **previdenciário** (`tipo` contendo
  `doenca`/`acidente`) que durou **> 6 meses** (`data_retorno > data_inicio + 6 months`). Uma função.
- **Período aberto** = âncora + 12 meses × k, onde k = `gozados // direito` e gozados = soma de
  `days_requested` das `hr_vacation_requests` APROVADAS com `start_date <= hoje` (o mais antigo é
  consumido primeiro, como na lei). Direito = `hr_vacation_periods.days_entitled` quando a pessoa
  tem linha; senão 30 (art. 130, I). **Limite** = início + 24 meses − 1 dia (aquisitivo + concessivo).
- **Faixas** pela idade do período aberto: `< 12` = em aquisição (não é risco) · 12–16 · 17–19 ·
  20–22 · `> 22` = alarme de dobra. Mais duas faixas próprias: **"afastado > 6 meses (reinicia no
  retorno)"** (previdenciário em curso já acima de 6 meses — sem idade, o período reinicia quando
  voltar) e **"não calculado"** (sem `data_admissao`). Soma das 7 == ativos com vínculo.
- **Ativos com vínculo** = `employees.status` fora de `identidade.SEM_VINCULO` (importado, não
  copiado) **e** ≠ `demitido` (lá ele fica fora de propósito por causa da conversa; aqui é vínculo
  encerrado), sem homologação, sem PJ (`tipo_contrato ILIKE '%pj%'`). Quem está de férias ou
  afastado curto **entra** (é o mapa de quem tem direito, não a coorte do ponto).
- Zero `x or default`. `hoje` é o de Manaus.

## 3. Estado depois (medido)

Oráculo VERDE (staging, container efêmero com a worktree — ver §5 por quê):
```
$ python3 /app/scripts/orq/test_oraculo_mapa_ferias.py
ativos com vínculo: 55 · âncoras recalculadas por afastamento: 1
legenda: < 12 meses (em aquisição): 32 · 12–16: 11 · 17–19: 3 · 20–22: 2 · > 22 meses (risco de dobra): 5 · afastado > 6 meses (reinicia no retorno): 0 · não calculado: 2
OK mapa de férias: tela fiada, soma fecha, sem default, âncora respeita o art. 133
exit=0
```
(Primeira rodada verde, antes das fixtures da frente 05: `53 · ... · não calculado: 0`.)

Contra-prova do art. 133 no dado: EDWARD (adm. 06/10/2023) sem a regra estaria com **35 meses,
faixa > 22, vencida**; com o retorno de 20/08/2025 como âncora fica **12 meses, faixa 12–16,
limite 19/08/2027**. O oráculo recalcula por SQL e compara — se a âncora voltar para a admissão,
acusa `âncora do serviço 2023-10-06 ≠ recalculada 2025-08-20`.

Prova por HTTP (uvicorn efêmero em 127.0.0.1:8082 com o código da worktree, banco de staging):
```
GET /api/v1/redesign/data/departamento-pessoal  → screens["mapa-ferias"]
type: table | rows: 55 | cols: [Colaborador, Cargo, Âncora, Meses, Faixa, Gozados / direito, Restantes, Limite, Vence em]
sub: 55 ativos com vínculo · 5 na faixa > 22 meses (risco de dobra) · 5 já vencidas · hoje 12/09/2026 · âncora = admissão ou retorno de afastamento > 6 meses (art. 133 CLT)
-- Legenda: < 12: 32 · 12–16: 11 · 17–19: 3 · 20–22: 2 · > 22: 5 · afastado > 6 m: 0 · não calculado: 2
-- Vence em 30/60/90: ≤ 30 d: 0 · 31–60 d: 1 (KALEL SILVA DE JESUS — limite 24/10/2026, 42 d) · 61–90 d: 0
1ª linha: AILTON CÉSAR VASCONCELOS · AGENTE DE PORTARIA · 22/10/2023 · 34 · > 22 meses · 0 / 30 · 30 · 21/10/2025 · vencida há 326 d
```
Rota: `from main_production import app` na worktree lista `/api/v1/redesign/...` — a tela entra
pelo `build()` do DP, não precisou de rota nova (sub-router em `vacation_controller` não foi
criado: YAGNI — a tela é o entregável; JSON por API entra quando o Hermes/MCP pedir).

### A lista que o Jordan precisa ver — faixa > 22 meses (staging, 12/09/2026)

| Colaborador | Admissão | Período aberto desde | Limite legal | Situação | Gozadas no ERP |
|---|---|---|---|---|---|
| AILTON CÉSAR VASCONCELOS | 22/10/2023 | 22/10/2023 | 21/10/2025 | **vencida há 326 d** | 0 |
| ANTONIO CARLOS CASTRO GAMA | 24/03/2024 | 24/03/2024 | 23/03/2026 | **vencida há 173 d** | 0 |
| ELEN XAVIER NUNES | 14/04/2024 | 14/04/2024 | 13/04/2026 | **vencida há 152 d** | 0 |
| ANTONIO DINIZ ASSIS DOS SANTOS | 14/07/2024 | 14/07/2024 | 13/07/2026 | **vencida há 61 d** | 0 |
| ARYELTON BRAGA FIGUEIRA (suspenso) | 22/07/2024 | 22/07/2024 | 21/07/2026 | **vencida há 53 d** | 0 |

Na faixa 20–22 (próximos): KALEL SILVA DE JESUS (22 m, limite 24/10/2026, **42 dias**) e OSCAR
SOARES DA COSTA FILHO (20 m, limite 04/01/2027).

⚠️ "Gozadas no ERP = 0" significa que **o ERP não tem férias aprovadas** para essas pessoas. Se
elas tiraram férias pelo Sólides antes do ERP registrar, o mapa está certo sobre o que o ERP sabe
e errado sobre a vida — a correção é registrar a férias gozada (ou `sync-ferias-solides`), não
mexer no cálculo. É exatamente o alarme que a tela existe para dar.

## 4. Fiação pendente para o integrador

1. **Aba no grupo Férias** (arquivo compartilhado do DP, não tocado por mim):
   `backend/modules/operacional/controllers/redesign_builders/_dp_grupos.py`, em `GRUPOS`,
   grupo `g-ferias`, acrescentar a tupla `("mapa-ferias", "Mapa de férias")` — e, para a aba
   receber a tela, **mover as 2 linhas `# frente 08` de `departamento_pessoal.build()` para
   ANTES de `montar_grupos(out)`** (hoje estão antes do `return out`, como o contrato pediu;
   `montar_grupos` só monta abas com telas já em `out`). Sem isso a tela continua alcançável só
   pelo deep-link `?t=mapa-ferias`.
2. `checar_regressao.py`: **nada** — oráculo em `scripts/orq/test_*.py` é globado pela varredura da
   meia-noite. Não criei caçador.
3. `celery_app.py`, `main_production.py`, `_modules/*.json`: **nada**.
4. DDL de produção: **nenhum**. A fixture de afastamento é dado de staging, não vai para produção.
5. Bake: a tela só serve depois do bake do backend (docker cp não publica — §0.3 do pré-mortem).

## 5. O que NÃO foi feito e por quê

- **Não hot-copiei para `conecta-pro-backend-staging`**: o container monta
  `/opt/conecta-pro/backend` (checkout principal) como **read-only** em `/app` — `docker cp`
  falha com "mounted volume is marked read-only" e o checkout principal não é a minha worktree.
  Testei num **container efêmero** (`docker run --rm`, imagem `conecta-pro-backend-staging`,
  mesmo env e rede do staging, worktree montada RO em `/app`) — banco de staging, código da
  branch. Script em `scratchpad/stg.sh` desta sessão; o integrador reproduz com
  `docker run --rm --network conecta-staging-network --env-file <env do staging> -v <worktree>/backend:/app:ro -e PYTHONPATH=/app --user erp conecta-pro-backend-staging python3 /app/scripts/orq/test_oraculo_mapa_ferias.py`.
- **Sub-router em `vacation_controller.py`**: não criado (YAGNI; a tela do redesign é genérica).
- **Afastamentos descontínuos** não são somados (art. 133 IV fala em total no período): o
  `ancora_periodo` olha cada afastamento isolado. Registrado na docstring. Sobe quando houver caso.
- **`suspensao_contratual`** (Aryelton, em curso desde 02/02/2026) **não** move a âncora nem cai em
  "afastado > 6 meses": só `doenca`/`acidente` são tratados como previdenciários. Se a suspensão
  dele for auxílio-doença registrado com o tipo errado, é decisão do dono corrigir o tipo.
- **`hr_vacation_periods` semeada por calendário**: não corrigi (é dado, e é de outro fluxo). O mapa
  usa dela só `days_entitled`; `limit_date` sai como `limite_erp` no serviço mas **não** vai para a
  tela, porque está errado em todos os casos conferidos. Decisão do dono: apagar/ressemear a
  partir da admissão, ou fazer o fluxo de aprovação atualizar `days_used`/`period_id`.
- **Redução por faltas (art. 130)** só entra se `days_entitled` do ERP disser — não recalculo por
  `absences_count`.
- Não editei frontend: `table` + `panels` renderizam genericamente.

## 6. Como o Jordan testa amanhã

1. Depois do bake do backend: abrir
   `https://<host>/redesign/departamento-pessoal?t=mapa-ferias`
   (ou, se o integrador fez a fiação do §4.1, Departamento Pessoal → Férias & Afastamentos → aba
   "Mapa de férias").
2. Conferir o subtítulo: N ativos com vínculo, quantos em `> 22`, quantos vencidos, a data de hoje.
3. Painel "Legenda": as 7 contagens somam N. Painel "> 22 meses": a lista nominal acima (em
   produção os nomes/datas podem diferir do staging). Painel "Vence em 30/60/90".
4. Buscar "EDWARD" no campo de busca do staging: âncora 20/08/2025 (não 06/10/2023) — é a fixture
   do art. 133. Em produção ele aparece com a admissão, porque lá não há afastamento longo.
5. Oráculo (container de produção, depois do bake):
   `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_mapa_ferias.py`
   — esperado: `OK mapa de férias ...`, exit 0. Se sair `FALHOU: ... âncora do serviço ... ≠
   recalculada ...`, alguém quebrou a regra do art. 133.
6. Para cada nome na faixa `> 22`: confirmar no Sólides/na pasta se a pessoa tirou férias. Se
   tirou, registrar a férias no ERP (Férias → Solicitar → aprovar com a data real) e a pessoa
   desce de faixa sozinha.

## 7. Riscos residuais (do pré-mortem)

- **0.3 / 0.4** — só existe depois do bake; `docker cp` não publica e o staging monta RO. O oráculo
  verde desta noite foi contra a worktree, não contra o container `conecta-pro-backend-staging`.
- **"Gozadas = 0" pode ser falta de registro**, não falta de férias (§3). O mapa é tão bom quanto
  `hr_vacation_requests`. `sync-ferias-solides` existe e está na aba Férias.
- **Afastamento com `tipo` fora de doença/acidente** (ex. `suspensao_contratual` que na verdade é
  INSS) não reinicia o período — fica visível como risco, nunca escondido (erro para o lado seguro).
- **Duas verdades sobre o limite**: `hr_vacation_periods.limit_date` (semeado) × limite legal
  calculado. A tela mostra o legal; a tela antiga "Saldo de férias" pode mostrar o do ERP. Até o
  dono decidir o §5, os dois números vão divergir.
- **Sem Sentry** (0.1): exceção no `build()` do DP cai no `safe()`? Não — as 2 linhas da frente
  08 estão fora do `safe()`; se `mapa()` estourar, o DP inteiro falha. Preferi assim de propósito:
  tela de risco de dinheiro que falha em silêncio vira "verde cego". Se o integrador preferir
  degradar, envolva em `try/except` e registre a falha em `out["mapa-ferias"]` como "sem dado".
