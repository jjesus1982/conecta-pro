# FRENTE 07 — Precificação de contrato: reserva técnica, PLR sindicato %, taxa admin, modos de cálculo, calculado × faturado

**Data:** 12/09/2026 · **Branch:** `frente/07-precificacao` (criada a partir de `fase5-hermes-camada-cognitiva`
@ 30be528a3 — a worktree veio em `main` de abril, sem `auditoria/` nem `redesign_builders/`; troquei a base
e informo aqui) · **Módulo:** crm · **Sessão:** tmux-agente-07

**Commits:** `1d22edf14` (oráculos, vermelhos) · `56822cdf5` (implementação, oráculos verdes) · este relatório.

---

## 1. Estado ANTES (medido, staging `conecta_pro_staging`)

- `reserva` no repositório: **0 ocorrências**. PLR só como tipo de evento. Sem "calculado vs faturado".
- `crm_pricing_params`: 24 linhas (encargos, tributos, benefícios, adicionais, `margem` escalar), **sem vigência nem
  origem** (colunas: chave, valor, label, grupo, updated_at).
- CCT do Amazonas em `cct_convencoes` (SINDECOMPRESTS AM000613/2025, 01/01→31/12/2026), `cct_feriados` com **16
  feriados ativos em 2026**, `cct_beneficios` **sem PLR**.
- 15 contratos ativos (R$ 291.300,06/mês), 22 rascunhos. `posts.contract_id` **vazio em 100% dos 15 postos**;
  postos ligam ao cliente por `client_id`. `contract_items` só em 5 contratos.
- NFS-e no staging: competências 2026-01 e 2026-02 apenas (27 autorizadas).
- `crm_pricing_margens` (referenciada por `crm/services/margem.py`) **não existe no staging** — o código de margem
  por dimensão é mais novo que o banco de teste. Não é desta frente; registrado.

### Oráculos VERMELHOS (antes do conserto)

```
=== ORACULO 1 (antes)
arquivos crm varridos: 79 · parâmetros no armazém: 0/3 · contrato simulado: CTR-2026-00013
FALHOU: armazém sem colunas de vigência/origem: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.UndefinedColumnError'>: column "vigencia_inicio" does not exist
FALHOU: parâmetro 'reserva_tecnica_pct' não existe em crm_pricing_params
FALHOU: parâmetro 'plr_sindicato_pct' não existe em crm_pricing_params
FALHOU: parâmetro 'taxa_admin_pct' não existe em crm_pricing_params
FALHOU: serviço de simulação por contrato não existe: cannot import name 'precificacao_contrato' from 'modules.crm.services' (/app/modules/crm/services/__init__.py)
5 desvio(s): precificação não lê a fonte
exit=1
=== ORACULO 2 (antes)
contratos ativos: 15 · relatório: inexistente
FALHOU: serviço calculado×faturado não existe: cannot import name 'precificacao_contrato' from 'modules.crm.services' (/app/modules/crm/services/__init__.py)
1 desvio(s): não há calculado × faturado
exit=1
```

Na 1ª rodada após implementar, o oráculo 1 acusou **o meu próprio `demo()`** (3 literais em keyword
`reserva_tecnica_pct=0.10`…) — prova de que o detector AST não é cego. O demo passou a entregar os percentuais
por dict.

### ⚠️ Terreno: o staging NÃO aceita hot-copy — tudo aqui rodou em MODO EFÊMERO

`conecta-pro-backend-staging` monta `/opt/conecta-pro/backend → /app` **somente leitura**, e essa árvore é o
checkout principal, não esta worktree: `docker cp` responde *"mounted volume is marked read-only"*. Então nada
foi copiado para lá. Oráculos e rotas rodaram em containers efêmeros da imagem do backend com **o backend desta
worktree montado em `/app:ro`**, na rede e no banco do staging (receita do integrador, porta 8207 = frente 07):

```bash
WT=/opt/conecta-pro/.claude/worktrees/agent-aebb7694081186c83
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
        | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')

# uma execução (oráculo/script):
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_precificacao_le_a_fonte.py

# servidor HTTP efêmero (só enquanto testa):
docker run -d --name teste-frente-07 --network conecta-staging-network -p 127.0.0.1:8207:8080 \
  -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  --env-file /opt/conecta-pro/.env $ENVS -e PORT=8080 -e ENVIRONMENT=staging conecta-pro-backend:latest
until curl -sf http://127.0.0.1:8207/health >/dev/null; do sleep 3; done
docker stop teste-frente-07   # ao terminar — memória é compartilhada por 9 agentes
```

🔎 **Achado para os outros agentes:** o servidor efêmero **precisa de `-e ENVIRONMENT=staging`**. Com o
`--env-file /opt/conecta-pro/.env` puro, `ENVIRONMENT=production` e o loguru abre
`/app/logs/app.log` (`core/logging/logger.py:139`) — em `/app:ro` isso é
`OSError: [Errno 30] Read-only file system: '/app/logs'` e o container morre com
`Application startup failed. Exiting.` (Exited 3), sem nunca responder ao `/health`. Um `--tmpfs /app/logs`
**não** resolve: não se cria mountpoint dentro de bind RO. A execução avulsa de oráculo não passa pelo
`lifespan`, então roda com o `.env` como está.

Nenhum container ou banco de produção foi tocado; leitura de produção não foi necessária. Ao fim, parei o
`teste-frente-07`.

---

## 2. O que foi feito (arquivo por arquivo)

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_precificacao_le_a_fonte.py` (novo) | (a) varredura AST de `modules/crm` por número literal em nome com reserva/PLR/taxa admin — atribuição, default de função, keyword, dict, `.get(chave, n)`; auto-prova com trecho ruim (5→5). (b) os 3 parâmetros existem em `crm_pricing_params` com `vigencia_inicio` e `origem`. (c) simulação de contrato real usa exatamente a linha do banco; sem confirmação → componente None; `resolver_parametro` aplica cópia confirmada em memória e recusa vigência vencida. |
| `backend/scripts/orq/test_oraculo_calculado_vs_faturado.py` (novo) | Para cada contrato ativo: `preco_calculado` (ou `motivo_sem_calculo`), `faturado` com `fonte_faturado` nfse/contrato (ou `motivo_sem_faturado`), divergência R$/% conferida; tela `calculado-vs-faturado` com 1 linha por contrato ativo e coluna de divergência; foto de `contracts` idêntica antes/depois (não é gatilho). |
| `backend/modules/crm/services/precificacao_modos.py` (novo) | 10 modos puros (`MODOS`, `ROTULO`), `dias_5x2/6x1/sdf`, `calcular_modo`, `aplicar_encargos_contrato`, `ParametroAusente`, `demo()` com asserts. |
| `backend/modules/crm/services/precificacao_contrato.py` (novo) | `resolver_parametro` (puro), `carregar_parametros_contrato`, `carregar_feriados` (cct_feriados), `custo_mao_de_obra` (posts × motor CCT), `simular_contrato`, `faturado_na_competencia` (NFS-e por CNPJ), `relatorio_calculado_vs_faturado`. |
| `backend/modules/crm/controllers/precificacao_controller.py` (novo) | Sub-router `/pricing`: `GET /modos`, `POST /simular-contrato`, `GET /contratos/calculado-vs-faturado`. Auth `get_current_active_user`. Só lê. |
| `backend/modules/crm/controllers/growth_controller.py` | Fim do arquivo: `include_router` do sub-router (# frente 07). `PUT /pricing/parametros`: para as 3 chaves novas, grava também `confirmado_por/confirmado_em` — é como o dono liga o percentual. Comportamento das outras chaves intacto. `_CHAVES_CONTRATO` tupla. |
| `backend/modules/operacional/controllers/redesign_builders/_frente_07.py` (novo) | `MENU`, `telas(db)` → `calculado-vs-faturado` (tabela) e `simular-precificacao` (FORM `showResult`); `router` com `POST /action/simular-precificacao`. Helpers do redesign importados dentro de `telas()` (ciclo de import derrubava o builder do crm). |
| `backend/modules/operacional/controllers/redesign_builders/crm.py` | 3 pontos `# frente 07`: `router.include_router(_r07)` após `router = APIRouter()`; `EXTRA_MENU.extend(_menu07)` após a lista; `out.update(await _telas_07(db))` antes do `return out`. |

### Decisões (não reabrir)
- **Ler a fonte, nunca chumbar.** Os 3 percentuais vivem em `crm_pricing_params` com `vigencia_inicio/fim`,
  `origem`, `confirmado_por/em`. Regra: só entram no custo se **vigentes na competência E confirmados**. Sem isso a
  resposta diz `aguardando confirmação do dono — não entra no custo`, componente `None`. Nunca 0.
- **Recalcular é simulação.** Toda resposta traz `simulacao: true, gravou: false`; o oráculo 2 prova que
  `contracts` não muda.
- **Custo por pessoa** vem do motor existente (`pricing_cct.calcular_funcao`) — funções `AGP P1 Diurno` /
  `AGP P1 Noturno` de `crm_pricing_funcoes`. Posto com `shift_start_time` ≥ 18h ou < 5h = noturno; 12x36 sem
  horário = metade/metade (**dito como hipótese na linha**). Preço = custo ÷ divisor do próprio motor
  (1 − tributos − margem).
- **Faturado**: NFS-e autorizadas do CNPJ na competência; sem NFS-e, `monthly_value` do contrato com
  `fonte_faturado='contrato'` explícito.
- **Reserva técnica** = `custo_mo × pct` (equivale a efetivo × pct × custo/pessoa). PLR sobre a mão de obra;
  taxa admin sobre o subtotal (mo + reserva + PLR + materiais).
- Os "nove modos" do benchmark são 10 rótulos (Dias Fixos + 3 variantes) — implementei os 10.

---

## 3. Estado DEPOIS (medido)

### Oráculos VERDES (modo efêmero, imagem `conecta-pro-backend:latest`, banco `conecta_pro_staging`)

```
=== ORACULO 1 (depois)
arquivos crm varridos: 82 · parâmetros no armazém: 3/3 · contrato simulado: CTR-2026-00013
OK precificação lê a fonte: nenhum percentual chumbado, os três parâmetros têm vigência e origem, e a simulação usa exatamente a linha do banco (sem confirmação = sem default)
exit=0
=== ORACULO 2 (depois)
contratos ativos: 15 · no relatório: 15 · com os dois números: 10 · maior divergência: CTR-2026-00016 R$ -41,920.73
OK calculado × faturado: cada contrato ativo tem os dois números (ou o motivo), a tela publica a divergência e nenhum contrato mudou
exit=0
```

`python3 -m modules.crm.services.precificacao_modos` → `demo precificacao_modos: OK — 10 modos`.

### Rotas em `app.routes` (ordem de boot da app, `from main_production import app`)

```
rotas frente07: ['/api/v1/crm/pricing/contratos/calculado-vs-faturado', '/api/v1/crm/pricing/modos',
                 '/api/v1/crm/pricing/simular-contrato', '/api/v1/redesign/action/simular-precificacao']
crm builder carregado: True · menu frente07: ['calculado-vs-faturado', 'simular-precificacao']
```

### curl que prova (servidor efêmero `teste-frente-07`, `http://127.0.0.1:8207`, banco staging)

```
GET /api/v1/crm/pricing/contratos/calculado-vs-faturado?competencia=2026-09
{'ok': True, 'competencia': '2026-09', 'total': 15, 'com_os_dois_numeros': 10, 'soma_faturado': 277500.06,
 'soma_preco_calculado': 432677.42, 'aviso': 'Relatório para o dono. Nenhum contrato é alterado por esta rota.'}

POST /api/v1/crm/pricing/simular-contrato {"contrato":"CTR-2026-00013","competencia":"2026-09"}
 efetivo 12 · custo_mao_de_obra 52947.90 · componentes {reserva_tecnica: null, plr_sindicato: null, taxa_admin: null}
 custo_calculado 52947.90 · preco_calculado 74838.02 · valor_contrato 65842.42 · gravou false
 avisos: "reserva_tecnica_pct: aguardando confirmação do dono (confirmado_em vazio) — não entra no custo" (×3)
 hipoteses: "postos ligados pelo CLIENTE (posts.contract_id vazio)"; "POST-0001: 12x36 sem horário — assumido 6 dia / 6 noite"
 parametros.reserva_tecnica_pct: {valor 0.0, origem 'Decisão do dono — A CONFIRMAR PELO JORDAN…', vigência 2026-01-01→2026-12-31, aplicavel false}

POST simular-contrato modo dias_fixos_5x2 (postos 2, valor_dia 350) →
 {"quantidade": 21.0, "unidade": "dia", "total": 14700.0, "memoria": "2 × 21 dia(s) × 350.00 [dias_fixos_5x2]", "feriados_no_ano": 16}
POST simular-contrato modo hora SEM valor_hora → {"detail":"parâmetro ausente: valor_hora"} http=422
POST /api/v1/redesign/action/simular-precificacao (FORM) → ok true, "Simulação de CTR-2026-00016 em 2026-09 — nada gravado."
GET /api/v1/redesign/data/crm → calculado-vs-faturado: table, 15 rows, 8 cols · simular-precificacao: form, 14 fields
                               · extraMenu: ['calculado-vs-faturado', 'simular-precificacao'] · wired: idem
```

### O caminho de LIGAR o parâmetro (testado e desfeito)

Prova de que o percentual entra pelo banco e não pelo código — feito no staging e **revertido ao estado
entregue** no mesmo script:

```
PUT /api/v1/crm/pricing/parametros {"valores":{"reserva_tecnica_pct":0.10}} → {"atualizados":1}
psql → reserva_tecnica_pct | 0.100000 | jjesus@conectamais.pro | 2026-09-13 07:40:06+00

POST /crm/pricing/simular-contrato CTR-2026-00013 2026-09 →
 componentes {reserva_tecnica: 5294.79, plr_sindicato: null, taxa_admin: null}
 custo_calculado 58242.69 (era 52947.90) · preco_calculado 82321.82 (era 74838.02)
 avisos: só PLR e taxa admin continuam "aguardando confirmação do dono"

oráculo 1 com o parâmetro CONFIRMADO (exercita o ramo "entra no custo"): exit=0

UPDATE crm_pricing_params SET valor=0, confirmado_por=NULL, confirmado_em=NULL → os 3 voltam a ausentes
```

### Contratos com maior divergência (faturado − preço calculado pelo motor CCT)

Competência **2026-09** (sem NFS-e no staging → faturado = valor do contrato):

| Contrato | Cliente | Efetivo | Custo calc. | Preço calc. | Faturado | Divergência |
|---|---|---:|---:|---:|---:|---:|
| CTR-2026-00016 | Mirante das Flores | 9 | 39.253,68 | 55.482,23 | 13.561,50 | **−41.920,73 (−75,6%)** |
| CTR-2026-00018 | Villa dos Pássaros | 6 | 26.473,95 | 37.419,01 | 3.800,00 | −33.619,01 (−89,8%) |
| CTR-2026-00010 | Mirante das Flores | 9 | 39.253,68 | 55.482,23 | 28.694,30 | −26.787,93 (−48,3%) |
| CTR-2026-00011 | Laranjeiras Village | 9 | 39.253,68 | 55.482,23 | 42.544,50 | −12.937,73 (−23,3%) |
| CTR-2026-00007 | Villa dei Fiori | 6 | 26.473,95 | 37.419,01 | 25.592,71 | −11.826,30 (−31,6%) |
| CTR-2026-00013 | Ideal Flores da Cidade | 12 | 52.947,90 | 74.838,02 | 65.842,42 | −8.995,60 (−12,0%) |
| CTR-2026-00008 | Ed. Michelangelo | 3 | 11.865,24 | 16.770,66 | 8.346,70 | −8.423,96 (−50,2%) |
| CTR-2026-00012 | Prime Arena | 6 | 26.473,95 | 37.419,01 | 33.479,60 | −3.939,41 (−10,5%) |
| CTR-2026-00009 | Villa dos Pássaros | 6 | 26.473,95 | 37.419,01 | 33.538,33 | −3.880,68 (−10,4%) |
| CTR-2026-00019 | Greenhills | 4 | 17.649,30 | 24.946,01 | 22.100,00 | −2.846,01 (−11,4%) |

Sem cálculo (motivo publicado): 00004 (postos com `required_headcount = 0`), 00017/00005/00015/00022 (nenhum
posto ligado ao contrato nem ao cliente); 00022 também sem faturado (valor mensal vazio).

Competência **2026-02** (12 com NFS-e): 00019 −24.446,01 (NFS-e de R$ 500 contra 4 postos); 00010/00016
−13.226,43 cada; 00011 −12.937,73; 00007 −11.826,30; 00013 −8.995,60; 00008 −8.423,96; 00009/00018 −80,68;
**00012 +3.047,49 (+8,1%)** — o único acima do preço do motor.

**Leitura honesta:** "preço calculado" é o do motor CCT com margem-alvo 15% + tributos; **todos os 10 contratos
faturam ACIMA do custo calculado** (ex.: 00013 custo 52.947 × faturado 65.842) e abaixo do preço-alvo. A tela
mostra os dois números para o dono decidir. E **Mirante das Flores (00010+00016) e Villa dos Pássaros
(00009+00018) são dois contratos do mesmo cliente**: efetivo e NFS-e são do cliente e se repetem nas duas
linhas (hipótese publicada na linha) — separar exige preencher `posts.contract_id`.

---

## 4. Fiação pendente para o integrador

- **`checar_regressao.py`**: nada. A varredura da meia-noite globa `scripts/orq/test_*.py` sozinha.
- **`celery_app.py`**: nada (sem tasks).
- **`main_production.py`**: nada (sub-router do growth_controller já montado em `/crm`; ação do redesign entra
  pelo registry `_discover_module_builders` via `router` do `crm.py`).
- **`frontend/src/app/redesign/_modules/crm.json`**: nada (menu via `extraMenu` do builder; `tbl`/`FORM`
  renderizam genericamente). Nenhum `.tsx` editado.
- **DDL de produção — rodar ANTES do bake** (o `PUT /pricing/parametros` só toca `confirmado_*` nas 3 chaves
  novas, que só existem depois do INSERT; mas o serviço de simulação lê as colunas de vigência e falharia sem
  elas — a tela e a rota devolvem "Sem dado: …" em vez de derrubar o módulo, mesmo assim: DDL primeiro):

```sql
ALTER TABLE crm_pricing_params
  ADD COLUMN IF NOT EXISTS vigencia_inicio date,
  ADD COLUMN IF NOT EXISTS vigencia_fim date,
  ADD COLUMN IF NOT EXISTS origem varchar(200),
  ADD COLUMN IF NOT EXISTS confirmado_por varchar(120),
  ADD COLUMN IF NOT EXISTS confirmado_em timestamptz;

-- valor 0 + confirmado_em NULL = "parâmetro ausente": NÃO entra no custo até o Jordan confirmar.
INSERT INTO crm_pricing_params (chave, valor, label, grupo, vigencia_inicio, vigencia_fim, origem) VALUES
 ('reserva_tecnica_pct', 0, 'Reserva técnica — % sobre o efetivo do posto (cobertura de faltas/férias)', 'contrato',
  '2026-01-01', '2026-12-31', 'Decisão do dono — A CONFIRMAR PELO JORDAN (sem confirmação NÃO entra no custo)'),
 ('plr_sindicato_pct', 0, 'PLR sindicato — % sobre a mão de obra', 'contrato',
  '2026-01-01', '2026-12-31', 'CCT SINDECOMPRESTS AM000613/2025 não traz PLR em % (cct_beneficios sem PLR) — A CONFIRMAR PELO JORDAN'),
 ('taxa_admin_pct', 0, 'Taxa administrativa — % sobre o subtotal do contrato', 'contrato',
  '2026-01-01', '2026-12-31', 'Decisão do dono — A CONFIRMAR PELO JORDAN (sem confirmação NÃO entra no custo)')
ON CONFLICT (chave) DO NOTHING;
```

  Aplicado no staging em 12/09 (idêntico). Vigência copiada da CCT vigente (01/01→31/12/2026).

- **Como o Jordan liga cada percentual** (depois do DDL), pelo caminho que já existe e é "propose" no MCP:
  `definir_parametros_precificacao({"reserva_tecnica_pct": 0.10})` → `PUT /crm/pricing/parametros` grava o valor
  **e** `confirmado_por/confirmado_em`. Ou direto no banco:
  `UPDATE crm_pricing_params SET valor=0.10, confirmado_por='jjesus@conectamais.pro', confirmado_em=now() WHERE chave='reserva_tecnica_pct';`
  Os valores **0.10 / PLR / taxa admin são A CONFIRMAR PELO JORDAN** — a CCT não dá o número.

- **Bake**: módulos `crm` e `operacional` (builders) na imagem do backend; sem workers Celery envolvidos.
  Depois do bake: `checar_bake_pendente = 0`, `checar_drift_workers` limpo (Parte 0 do pré-mortem).

---

## 5. O que NÃO foi feito e por quê

- **Valores dos 3 percentuais.** A CCT do Amazonas não tem PLR em %; reserva técnica e taxa admin são decisão do
  dono. Ficaram com valor 0 e `confirmado_em` NULL = ausentes. Não inventei número.
- **"Ignorar alerta de posto descoberto" por contrato.** `contracts` não tem coluna/JSON natural (só `sla_config`
  e `clauses`, com outro propósito) e a tabela é compartilhada por várias frentes. Se o Jordan quiser: `ALTER TABLE
  contracts ADD COLUMN IF NOT EXISTS ignorar_alerta_posto_descoberto boolean NOT NULL DEFAULT false` — e o
  consumidor (alerta de cobertura, frente 4) precisa ler.
- **"Reserva técnica" como flag por contrato** (☑ na ficha deles): implementei como percentual global com
  vigência; ligar/desligar por contrato exige coluna em `contracts` (mesma razão acima). Registrado.
- **`posts.contract_id`** está vazio em todos os postos; o efetivo cai para `client_id` (hipótese na linha).
  Preencher é dado operacional do Jordan/Gonzaga, não desta frente.
- **`_DEFAULTS` em `pricing_cct.py`** (encargos, adicionais, `repasse=0.075`, `margem=0.15` chumbados como
  fallback "se faltar no banco") — viola a regra "ler a fonte", mas é o motor de todas as propostas e não é desta
  frente. O oráculo 1 só vigia reserva/PLR/taxa admin; ampliar o regex para `repasse|margem|iss|inss…` acusaria
  hoje 24 literais. Dono: quem cuidar do motor.
- **Modo de cálculo gravado no contrato** (a ficha deles tem `Cálculo: POR HORA/POR MONTANTE`). Não criei coluna
  em `contracts`; o modo é entrada da simulação. Se virar cadastro: `ALTER TABLE contracts ADD COLUMN IF NOT
  EXISTS modo_calculo varchar(20)` com CHECK nos 10 nomes de `MODOS`.
- **Hot-copy no `conecta-pro-backend-staging`**: impossível (bind RO). Testado em instância efêmera da mesma
  imagem — ver §1.
- `crm_pricing_margens` ausente no staging (drift do banco de teste) — fora da frente, registrado.

---

## 6. Como o Jordan testa amanhã

Suba o servidor efêmero da §1 (`http://127.0.0.1:8207`, banco de staging, mesmo login) — ele não fica de pé
sozinho, e pare com `docker stop teste-frente-07` ao terminar. Depois do merge no checkout que o staging serve +
restart, os mesmos passos valem em `:8081`; depois do bake, em produção.

1. **Tela — Redesign › CRM › "Calculado × Faturado"**: 15 linhas; olhar a coluna *Divergência* (verde ≥ 0,
   amarelo até −10%, vermelho abaixo) e a última coluna (*Parâmetros ausentes · hipóteses*). Conferir que
   nada mudou em Contratos depois de abrir.
2. **Tela — Redesign › CRM › "Simular precificação"**: escolher `CTR-2026-00013`, competência `2026-09`, modo
   vazio → *Simular* → painel *Resultado* com custo 52.947,90, preço 74.838,02, componentes "ausente". Depois
   modo `Dias fixos 5x2`, postos 2, valor/dia 350 → total 14.700,00 (21 dias: setembro tem o 7/9 na segunda).
3. **Ligar a reserva técnica** (é o teste do "lê a fonte"): no Cowork, `definir_parametros_precificacao`
   com `{"reserva_tecnica_pct": 0.10}` → aprovar o pedido → repetir o passo 2: `reserva_tecnica` passa a
   5.294,79 e o custo a 58.242,69. Ou por curl:
   ```bash
   TOKEN=$(curl -sf -X POST http://127.0.0.1:8207/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=jjesus@conectamais.pro&password=JsJ618908@#%" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
   curl -s -X PUT http://127.0.0.1:8207/api/v1/crm/pricing/parametros -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"valores":{"reserva_tecnica_pct":0.10}}'
   curl -s -X POST http://127.0.0.1:8207/api/v1/crm/pricing/simular-contrato -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" -d '{"contrato":"CTR-2026-00013","competencia":"2026-09"}' | python3 -m json.tool
   ```
4. **API**: `GET /api/v1/crm/pricing/contratos/calculado-vs-faturado?competencia=2026-02` — 12 linhas com
   `fonte_faturado: nfse`.
5. **Oráculos**: `docker exec teste-frente-07 python3 /app/scripts/orq/test_oraculo_precificacao_le_a_fonte.py`
   e `…/test_oraculo_calculado_vs_faturado.py` → ambos `exit 0`.

---

## 7. Riscos residuais (pré-mortem, frente 7)

1. **Percentual chumbado** — vigiado pelo oráculo 1 só para reserva/PLR/taxa admin em `modules/crm`. O motor
   (`pricing_cct._DEFAULTS`) continua com 24 literais de fallback. Se alguém "ajustar" o percentual no código em
   vez do banco, o oráculo acusa à meia-noite; se ajustar no `_DEFAULTS`, não.
2. **CCT errada** — o PLR ficou explicitamente "A CONFIRMAR": a régua SP do DigiExpress não foi copiada. Risco
   permanece se alguém confirmar um % sem ler a convenção do AM.
3. **"Ajustar o cálculo para a divergência sumir"** — a divergência é publicada com a fonte de cada número
   (motor CCT, posts, NFS-e/contrato) e hipóteses; o oráculo 2 afirma a presença dos dois números, não o valor.
   Quem quiser esconder ainda pode mexer no motor — a proteção é a memória de cálculo visível, não uma trava.
4. **Virar preço** — nenhuma rota escreve em `contracts`; o oráculo 2 fotografa antes/depois. A trava cobre o
   relatório e a tela; um agente novo que use `simular_contrato` para depois chamar `atualizar_contrato` não é
   impedido por código — é impedido pela regra (aditivo).
5. **Efetivo pelo cliente, não pelo contrato** — enquanto `posts.contract_id` estiver vazio, clientes com 2+
   contratos têm efetivo e NFS-e repetidos nas duas linhas (hipótese publicada). É dado, não código.
6. **Parte 0** — `docker cp` não publica e o staging é RO: esta frente só existe em produção depois do bake com
   `checar_bake_pendente = 0`. Sem Sentry (0.1), uma exceção nova na tela cai no `except` do builder e aparece
   como "Sem dado: …" — visível, mas ninguém é avisado.
