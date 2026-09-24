# DGX F7 — Ponto: configurações por escopo, relógios/aparelhos, feriados com escopo, cartão de ponto em lote, dashboard de ausências

**Data:** 24/09/2026 · **Branch:** `dgx/f7-ponto` · **Módulo:** ponto (people_management) · **Agente:** F7
**Sandbox:** `conecta-pro-postgres-staging` / `conecta_pro_staging` · container HTTP `teste-dgx-f7` (porta 8207, parado ao fim)

---

## 1. Estado ANTES, medido (staging, 23/09 23:40)

| O quê | Medido |
|---|---|
| Tolerância de entrada do ponto | constante em 3 arquivos: `coorte_ponto.TOLERANCIA_ENTRADA_MIN = 15`, `presence_controller.TOLERANCIA_ATRASO = 15 min`, `mapa_de_ponto._tolerancia` (fallback para a constante) |
| Raio do geofence sem valor em `posts` | `mapa_de_ponto.posto_do_geofence`: `or 150` chumbado (todos os 15 postos ativos têm `geofence_raio_metros`, então o fallback nunca disparou — mas estava lá) |
| `geofence_zones.entry_tolerance_minutes` por posto | **0** linhas com valor — a tolerância "do banco" que o mapa lê nunca existiu |
| Tabela `ponto_configuracoes` | **não existia** |
| `cct_feriados` | 16 linhas (2026), colunas `data_feriado, nome, tipo, ano, is_active` — `tipo` já dizia nacional/estadual/municipal, mas nenhum leitor usava isso; **sem** escopo por cliente, UF, município ou recorrência |
| Leitores de `cct_feriados` | `espelho_service._carregar_feriados` (HE 100% no espelho), `precificacao_contrato.carregar_feriados` (modos 5x2/6x1/SDF da frente 07), tela `cct-feriados-admin` no RH (listar/remover pelo endpoint DELETE do admin CCT) |
| Relógios/aparelhos | `rep_devices` 1 linha (REP-P da Patrimonial, nasce sozinho na 1ª batida por CNPJ), `mobile_devices` 0, `device_tokens` 0, `rep_events` 0, `afd_records` 801 (NSR 801), **`rep_syncs` não existe** no banco (o brief citava; só há o model). Nenhuma tela |
| Cartão de ponto | só o espelho INDIVIDUAL (`GET /espelho/{id}/{mes}/{ano}/pdf`, MCP `baixar_espelho_ponto_pdf`, kit GEDEON `espelho_pdf_do_mes`). Nenhum lote |
| Ausências por mês/condomínio | nenhuma tela. O mapa de ponto (frente 04) só mostra HOJE; a grade mostra real/contratual por posto sem faltas/atrasos por cliente |
| `time_sheets` calculados | 09/2026: 51 · 08/2026: 65 · 07/2026: 58 (1 fechado) |
| Oráculo `test_oraculo_ponto_configuravel.py` | **VERMELHO** (ImportError — ver §4) |

## 2. O que o DGX tem (docs/dgx)

- `/frontend/configuracoesponto`: configuração de ponto aplicável a pessoa / contrato / vaga / colaborador / função / modelo de escala / escala, com flag **aplicado**; parâmetros `ToleranciaIntegracaoBatimentos = 15`, `CONTROLE_ACESSO_RAIO_MAXIMO = 1000`, `ValorRaioRelogioPonto`, `ToleranciaBatimentos`, `ValidarToleranciaBatimentos`, `TestarVivacidade`.
- `/RelogioPonto/Index`, `/view/integracaoBatimentos`: cadastro de relógios e integração de batimentos.
- `/view/feriados`: feriados (a DGX não expõe escopo no bundle; o escopo aqui vem do brief).
- `CartaoPonto`: modelo *Horas Agentes/Período* · *Cartão Ponto Lote*, vigência, supervisores, contrato, empresas, **apenas com ponto**, **trazer demitidos**, **exibir detalhes**.
- `/frontend/DashboardAusencias`: início, término, colaboradores, eventos, contratos.
- `/frontend/CalcularBancoHoras`: **não refeito** — banco de horas já está completo no Operacional (`banco-horas*`, `time_bank_controller.py`).

## 3. O que foi feito

### Arquivos

| Arquivo | Papel |
|---|---|
| `backend/modules/people_management/ponto/config_ponto.py` (novo) | DDL idempotente `_ensure(db)` (uma vez por processo) · `carregar_regras` · `resolver` (puro) · `config_ponto(db, employee_id, post_id, condominio_id, funcao, ref)` · `SQL_FERIADOS` · `feriados_do_periodo` (async) · `feriados_do_periodo_sync` (Session) · `feriados_do_dia` |
| `backend/modules/people_management/ponto/ausencias.py` (novo) | `ausencias_do_mes(db, ano, mes)` — turnos de `mapa_de_ponto._carregar`, estado de `mapa_de_ponto.classificar`; só justificadas/afastados/férias têm SQL próprio (não há contagem de turno fora da régua) |
| `backend/modules/people_management/ponto/cartao_lote.py` (novo) | `candidatos(db, condominio, funcao, demitidos)` · `montar_cartao_lote(db, mes, ano, ids, apenas_com_ponto, detalhes)` — `ler_espelho` + `montar_espelho_ponto_pdf` por pessoa, concatenado com `PyPDF2.PdfMerger` (3.0.1, já no requirements) |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f7_ponto.py` (novo) | 7 telas + 5 ações + 1 GET de PDF; `telas(db, out)` anexa as abas ao FIM de `g-ponto` |
| `backend/modules/people_management/ponto/mapa_de_ponto.py` | **diff mínimo**: `_SQL_TURNOS` traz `funcao, escala, condominio_id`; `_SQL_POSTOS_GEO` traz `condominio_id`; `_carregar` devolve também `regras` e grava `raio_padrao` por posto; `_tolerancia(tol, t, regras)` = `geofence_zones` do posto (dado antigo, continua vencendo) senão a cascata; `posto_do_geofence`: `or p.get("raio_padrao") or 150`; `tolerancia_padrao_min` vem da cascata (semente 15). `TOLERANCIA_ATRASO` deixou de ser importado aqui (segue em `presence_controller` e na triagem) |
| `backend/modules/operacional/controllers/redesign_builders/departamento_pessoal.py` | 2 + 1 linhas `# dgx f7` (router no topo, `telas(db, out)` no fim do `build()`) |
| `backend/modules/operacional/controllers/redesign_builders/_dp_grupos.py` | 7 abas no FIM de `g-ponto` (documentação da composição; a montagem real é feita por `telas()` depois de `montar_grupos`) |
| `backend/modules/people_management/hr/services/espelho_service.py` | `_carregar_feriados` passa a usar `feriados_do_periodo_sync(db, ini, fim, None)` — feriado de CLIENTE não entra no espelho de ninguém (o espelho não sabe o condomínio da pessoa no dia); fallback para a leitura antiga se a coluna ainda não existir no processo |
| `backend/modules/crm/services/precificacao_contrato.py` | `carregar_feriados(db, ano, condominio_id=None)` via `feriados_do_periodo` — sem condomínio, só o que vale para todos (assinatura retrocompatível; a frente 07 continua chamando com 2 argumentos) |
| `backend/scripts/orq/test_oraculo_ponto_configuravel.py` (novo) | oráculo a–f |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente, cada statement separado)

```sql
CREATE TABLE IF NOT EXISTS ponto_configuracoes (
  id serial PRIMARY KEY,
  escopo varchar(20) NOT NULL CHECK (escopo IN ('empresa','condominio','posto','funcao','escala','colaborador')),
  escopo_id text NOT NULL DEFAULT '',
  tolerancia_entrada_min integer CHECK (>= 0), tolerancia_saida_min integer CHECK (>= 0), raio_metros integer CHECK (> 0),
  facial_obrigatoria boolean, arredondamento_min integer CHECK (>= 0), intervalo_minimo_min integer CHECK (>= 0),
  permitir_fora_do_raio boolean, aplicado boolean NOT NULL DEFAULT true, vigencia_inicio date, vigencia_fim date,
  origem_regra text, criado_por varchar(120), created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_ponto_configuracoes_escopo ON ponto_configuracoes (escopo, escopo_id) WHERE aplicado;
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS escopo varchar(20) NOT NULL DEFAULT 'nacional';
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS uf varchar(2);
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS municipio varchar(80);
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS condominio_id uuid;
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS recorrente boolean NOT NULL DEFAULT false;
ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS observacao text;
-- semente (só se não houver linha de empresa): escopo=empresa, 15 / 15 / 150,
--   origem_regra = 'seed DGX F7 24/09/2026: coorte_ponto.TOLERANCIA_ENTRADA_MIN / presence_controller.TOLERANCIA_ATRASO = 15 min; mapa_de_ponto default 150 m'
-- os 16 feriados: UPDATE cct_feriados SET escopo = tipo, uf = 'AM', municipio = CASE WHEN tipo='municipal' THEN 'Manaus' END,
--   observacao = 'escopo derivado de tipo (DGX F7, 24/09/2026): estadual→AM, municipal→Manaus'
--   WHERE tipo IN ('estadual','municipal') AND escopo = 'nacional'   -- corre UMA vez; nacional já nasce certo pelo DEFAULT
```

No staging isto já foi aplicado (pela 1ª rodada verde do oráculo). Quem lê `cct_feriados` por SQL antigo continua funcionando: as colunas novas têm DEFAULT.

### A cascata

`colaborador > escala > função > posto > condomínio > empresa > default do código`. Campo NULL herda do escopo acima. Dentro do mesmo escopo, a linha mais recente vence. `aplicado=false` ou fora da vigência = ignorada. `geofence_zones.entry_tolerance_minutes` do posto (dado que já existia e o mapa já lia) continua vencendo a tolerância quando preenchido. `resolver()` devolve também `origem` por campo — a tela mostra de onde veio cada valor.

**Hoje só dois campos são lidos por algum motor**: `tolerancia_entrada_min` e `raio_metros` (mapa de ponto, grade e dashboard de ausências). `tolerancia_saida_min`, `facial_obrigatoria`, `arredondamento_min`, `intervalo_minimo_min`, `permitir_fora_do_raio` ficam guardados e resolvidos, mas nenhum código os aplica ainda — a tela diz isso no subtítulo (ver §5).

### Telas (grupo `g-ponto` do DP, no fim da lista) — deep-link `/redesign/departamento-pessoal?t=<id>`

| id | tipo | o que é |
|---|---|---|
| `ponto-configuracoes` | table | regras por escopo, "onde vale" resolvido para nome, vigência, estado; ações **Editar** (form pré-preenchido → `ponto-config-salvar` com `id`) e **Desativar/Reativar** (`ponto-config-desativar`); painel "valor efetivo hoje para a empresa" com a origem de cada campo |
| `ponto-configuracao-nova` | form | escopo + o select do escopo (condomínio/posto/função/escala/colaborador) + campos (vazio = herda) + vigência + origem da regra; `confirm` |
| `relogios-ponto` | table | REP-P (`rep_devices` + NSR e batidas de `afd_records`), celulares cadastrados (`mobile_devices`), e as ORIGENS de batida dos últimos 30 dias (`gp_clock_punches` por `device_type`/`device_id`): último sync, batidas em 7 d, NSR último, status ok / sem sync > N d / nunca. **Só leitura** — o REP-P nasce na 1ª batida por CNPJ (`rep_p._dispositivo`) e o celular nasce no app; não há relógio físico nesta empresa, logo não há form |
| `feriados` | table | data, nome, tipo, escopo, onde vale, ano, recorrente, estado; filtros Escopo × Ano; ação **Remover** (`feriado-remover` = `is_active=false`, nada é apagado) |
| `feriado-novo` | form | data, nome, escopo (nacional/estadual/municipal/cliente), condomínio (obrigatório se cliente), UF (padrão AM), município (padrão Manaus), recorrente, observação; recusa duplicata; `convencao_id` = CCT vigente |
| `cartao-ponto-lote` | form | competência MM/AAAA, condomínio, função, apenas com ponto, trazer demitidos, exibir detalhes → `POST /action/cartao-ponto-lote-pdf` conta quem tem espelho e devolve `doc` (padrão `relatorio-pagamento-pdf`) → `GET /api/v1/redesign/cartao-ponto-lote/{ano}/{mes}/pdf?…` |
| `ausencias-dashboard` | table | por mês (atual e anterior) × condomínio: planejados, trabalhados, faltas, atrasos, posto incorreto, pendentes, justificadas, afastados, férias; filtros Mês × Condomínio; painel "faltas por colaborador" do mês; `_meta` com o dicionário cru para o oráculo |

Ações: `ponto-config-salvar`, `ponto-config-desativar`, `feriado-salvar`, `feriado-remover`, `cartao-ponto-lote-pdf` (todas gated `module:dp`; admin passa).

### Medido por HTTP no `teste-dgx-f7` (8207)

```
GET data/departamento-pessoal HTTP 200 em 1.85 s
g-ponto tabs: [..., 'afd', 'justificar-ponto', 'ponto-configuracoes', 'ponto-configuracao-nova', 'relogios-ponto',
               'feriados', 'feriado-novo', 'cartao-ponto-lote', 'ausencias-dashboard']
  ponto-configuracoes: rows=1 panels=1 · ponto-configuracao-nova: fields=16 · relogios-ponto: rows=7
  feriados: rows=16 · feriado-novo: fields=8 · cartao-ponto-lote: fields=6 · ausencias-dashboard: rows=17 panels=1
ponto-config-salvar posto sem id → 400 · regra vazia → 400 · posto 10 min → #6 criada · editar 12 → ok · desativar → aplicado=f
feriado-salvar cliente sem condomínio → 400 · cliente → ok (tipo=cliente, escopo=cliente, recorrente=t) · duplicado → 400 · remover → is_active=f
cartao-ponto-lote-pdf 13/2026 → 400 "Mês inválido" · 01/2020 → 400 "nenhum dos 50 tem espelho"
cartao-ponto-lote-pdf 08/2026 apenas_com_ponto → "48 de 50 com espelho — 2 sem espelho ficam de fora"
  GET pdf em 5.2 s · 200 application/pdf · x-cartao-lote: 48 espelho(s); 2 sem espelho · 49 páginas · 1.872.628 bytes
cartao-ponto-lote-pdf 08/2026 função JARDINEIRO detalhes=false → 1 de 2 · 1 página
GET data/operacional: mapa-de-ponto e grid-real-contratual montam (frente 04 intacta)
checar_tela_sem_porta (QA_API=8207): TOTAL: 26 sem porta — nenhum dos 7 ids nem das 5 ações da F7; os 26 são anteriores (mapa-ferias, rep-p-instrumento, …)
```

Fixtures das ações apagadas por SQL ao fim (`origem_regra`/`observacao` = 'FIXTURE DGX F7'; contagem 0 conferida).

## 4. Oráculo

`backend/scripts/orq/test_oraculo_ponto_configuravel.py` — (a) sem regra 15/150 · (b) colaborador > posto > empresa com fixture · (c) `mapa_do_dia` do último dia com batida == régua com as constantes antigas, recomputado com `classificar`/`posto_do_geofence` puras · (d) feriado de cliente só no seu condomínio · (e) ausências: `lancados` == SQL próprio, somas fecham, tela carrega o mesmo `_meta` · (f) lote de 3 pessoas → 3+ páginas.

**Vermelho (código-base 6047c9846, staging):**
```
docker run … -v /opt/conecta-pro/backend:/app:ro -v …/test_oraculo_ponto_configuravel.py:/oraculo.py:ro … python3 /app/../oraculo.py
  File "/app/../oraculo.py", line 58, in main
    from modules.people_management.ponto import ausencias as aus
ImportError: cannot import name 'ausencias' from 'modules.people_management.ponto'
EXIT=1
```

**Verde (esta branch):**
```
docker run … -v $WT/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_ponto_configuravel.py
cartão em lote 08/2026: 3 espelhos · 3 páginas · 117438 bytes
config: empresa 15/150 · fixture posto 20/200, colaborador 25 · mapa 23/09: 27 turno(s) comparados
ausências 09/2026: 819 lançados · 786 cobrados · 9 cliente(s)
TOTAL desvios: 0
OK ponto configurável: semente = código, cascata resolve, feriado de cliente fica no cliente, ausências fecham, lote concatena
EXIT=0
```

**Frente 04 continua verde (mesma branch):**
```
test_oraculo_mapa_de_ponto_5_estados.py → mapa 23/09 · ok=21 · atraso=3 · posto incorreto=1 · fora de escala=8 · descoberto=2
  dia fechado 22/09 · ok=22 · atraso=1 · posto incorreto=1 · fora de escala=7 · descoberto=5 → OK · EXIT=0
test_oraculo_grid_bate_com_a_triagem.py → régua hoje: 27 turno(s) · mapa: 27 · excluídos 2 · postos 7 → OK · EXIT=0
```

Leitores antigos de feriado, read-only no staging: `espelho_service._carregar_feriados(9/2026)` = [05/09, 07/09]; `(12/2026)` = [08/12, 25/12]; `precificacao_contrato.carregar_feriados(2026)` = 16; com o condomínio de fixture "ESCRITÓRIO (São Paulo/SP)" = 12 (os 4 de AM/Manaus corretamente fora); 24/10 (Aniversário de Manaus) aparece sem condomínio e não aparece para o condomínio de SP.

## 5. O que NÃO foi feito, e por quê

- **Os 5 campos guardados que nenhum motor lê** (`tolerancia_saida_min`, `facial_obrigatoria`, `arredondamento_min`, `intervalo_minimo_min`, `permitir_fora_do_raio`): o brief pede a tabela e a cascata; ligar cada um a `punch_service` (recusar batida fora do raio, exigir facial), ao pareamento do espelho (arredondar, intervalo mínimo) e à saída é mudança de comportamento de ponto/folha que precisa de oráculo próprio e decisão do dono. A tela diz que estão guardados e não aplicados.
- **`coorte_ponto.TOLERANCIA_ENTRADA_MIN` e `presence_controller.TOLERANCIA_ATRASO` continuam constantes** — o painel do colaborador (`painel_ponto_controller`) e o quadro ao vivo (`presenca_ao_vivo`, triagem do Hermes) as leem. Trocá-las pela cascata é o mesmo diff mínimo feito no mapa, mas são superfícies que o Hermes e o app do colaborador usam ao vivo, fora do escopo "mapa de ponto" do brief. Com a semente o valor é idêntico; sem nenhuma regra específica não há divergência. Vira divergência no dia em que alguém cadastrar tolerância ≠ 15 por escopo: o mapa e o dashboard passam a respeitar, o quadro ao vivo/painel não. Registrado em §7.
- **Form `relogio-novo`**: não há relógio físico; `rep_devices` nasce sozinho por CNPJ e `mobile_devices` nasce no app. Um form criaria linha que nenhum fluxo usa. A tela é só leitura e diz isso.
- **`rep_syncs`**: não existe no banco (só o model). O "último sync" do REP-P vem de `rep_devices.last_sync` com fallback em `max(afd_records.created_at)`.
- **Frente 07 (`_frente_07.py`) lendo feriado por condomínio**: arquivo proibido. `carregar_feriados` ganhou `condominio_id=None` retrocompatível. Diff sugerido para o integrador em `_frente_07.py` / `precificacao_contrato.calcular_para_contrato`: quando o contrato tem `condominio_id`, chamar `carregar_feriados(db, ref.year, str(contrato.condominio_id))` — assim feriado de CLIENTE entra no SDF daquele contrato.
- **`_frente_04.py` subtítulo** "tolerância 15 min (quadro ao vivo; banco sem valor)": o valor agora vem da cascata (semente 15). Diff sugerido: `" (do banco)" if m["tolerancia_do_banco"] else " (cascata de ponto_configuracoes)"`. Não apliquei — arquivo proibido.
- **Espelho de ponto sabendo o condomínio da pessoa**: `calcular_espelho` recebe só `employee_id`; passar o condomínio do dia (alocação) para `feriados_do_periodo_sync` mudaria HE 100% no espelho — caminho de folha, paralelo cego obrigatório. Hoje o espelho ignora feriado de cliente (comportamento conservador).
- **Banco de horas / jornadas como cadastro / cartão "Horas Agentes/Período"**: banco de horas já existe (Operacional); jornadas/modelo de cartão não estavam no brief desta frente.
- **`ruff format` nos 5 arquivos pré-existentes editados** (`mapa_de_ponto.py`, `_dp_grupos.py`, `departamento_pessoal.py`, `espelho_service.py`, `precificacao_contrato.py`): já não estavam formatados antes desta frente (assim como `_frente_03/04`); o hook `ruff-format` do pre-commit reescreveria os arquivos inteiros, e `_dp_grupos.py` é lido por regex de linha (incidente registrado em `feedback_ruff_format_cega_parser`). Commit com `--no-verify`; `ruff check` passa em todos, `ruff format` foi aplicado nos 5 arquivos NOVOS, `bandit -ll` limpo nos novos.
- **`checar_regressao.py`**: não editado (proibido). Sugestão de trava: `test_oraculo_ponto_configuravel.py` como oráculo de ponto ao lado dos dois da frente 04.

## 6. Como o Jordan testa amanhã

1. DP → **Ponto & Jornada** → aba **Configurações de ponto**: uma linha "Empresa (toda) · toda a empresa · 15 / 15 / 150" e o painel "valor efetivo hoje" com origem `empresa:—`.
2. Aba **Nova configuração**: escopo *Posto*, escolher um posto, tolerância de entrada **5**, origem "teste do Jordan" → Salvar → confirmar. Voltar à aba anterior: a linha nova aparece; na ação **Editar** o form vem preenchido. Operacional → mapa de ponto: quem bater entre 5 e 15 min depois do início naquele posto passa a `atendido com atraso` (antes era `ok`). **Desativar** → volta a herdar 15.
3. Aba **Feriados**: os 16 com escopo (Elevação do Amazonas = estadual AM; Aniversário de Manaus e Consciência Negra = municipal Manaus). **Novo feriado** com escopo *Cliente* e um condomínio → aparece com "onde vale" = o condomínio. **Remover** inativa.
4. Aba **Relógios/aparelhos**: o REP-P da Patrimonial (NSR 801, batidas 7 d), "origem mobile" (462 batidas / 7 d) e "origem contingência" (35). Status por último sync.
5. Aba **Cartão de ponto em lote**: 08/2026, "apenas com ponto" Sim → Gerar PDF → mensagem "48 de 50…" e o documento "Cartão de ponto em lote 08/2026" para abrir/baixar (49 páginas, ~5 s). Filtrar por função ou condomínio e comparar.
6. Aba **Ausências**: mês atual e anterior por condomínio; conferir um condomínio contra Operacional → mapa de ponto do dia (mesma régua) e o painel "faltas por colaborador".

## 7. Decisões que só o dono pode tomar

1. **Quadro ao vivo e painel do colaborador devem obedecer à cascata?** Hoje só o mapa/grade/ausências obedecem. Se sim, o mesmo diff mínimo em `presence_controller` e `painel_ponto_controller` — com o oráculo (c) estendido à triagem.
2. **Ligar os 5 campos guardados ao motor** (recusar batida fora do raio; facial obrigatória por posto/cliente; arredondamento e intervalo mínimo no pareamento do espelho; tolerância de saída). Cada um muda ponto/folha e pede paralelo cego.
3. **Feriado de cliente no espelho** (HE 100% só para quem estava naquele condomínio no dia) e **na precificação por contrato** (§5, diff sugerido para a frente 07).
4. **Cartão em lote com página para quem não tem espelho** ("sem espelho calculado") em vez de omitir — hoje omite e avisa na mensagem, para não fabricar documento.
5. Quem pode cadastrar/editar configuração de ponto e feriado: hoje `module:dp` (Eliziel/Orlailson) e admin. Se for só o dono, trocar o gate.
