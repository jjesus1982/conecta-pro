# Relatório — Prontidão de Produção: Módulos de Gestão de Pessoas
**Conecta PRO · 2026-06-30 · auditoria multiagente (5 frentes paralelas)**

Módulos auditados: Saúde Ocupacional, Ponto Eletrônico, Portal do Funcionário, RH, Operações.
Método: 1 agente sênior por módulo (backend + frontend + banco + smoke test ao vivo), read-only.

---

## 1. Veredito geral

| Módulo | Prontidão | Estado |
|---|---|---|
| **Portal do Funcionário** | **82%** | Mais maduro. Esqueleto completo, auth E2E, dados REAIS do DP. 2 bugs. |
| **RH (estratégico)** | **78%** | Núcleo pronto (recrutamento/treino/desempenho/carreira/onboarding/reembolso). Clima/turnover/360 com gaps. |
| **Saúde Ocupacional (SST)** | **58%** | Funciona mas tem "split-brain" de 2 módulos, 1 tabela corrompida (2833 dups), eSocial inexistente. |
| **Ponto Eletrônico** | **58%** | Opera no dia-a-dia (sync Tangerino real), mas sem AFD legal, cálculo de horas frágil, 1 bug crítico. |
| **Operações** | **58%** | Código ~85% pronto, mas vazio de dados e com o elo posto↔cliente quebrado. |

**Resumo de uma frase:** nenhum módulo está "vazio" — todos têm código real e a maioria responde 200 sem 500. O que separa do "produção sem gaps" são **6 padrões sistêmicos** que se repetem em quase todos.

---

## 2. Os 6 padrões sistêmicos (a história real)

### Padrão A — Módulos paralelos / "split-brain" (o mais grave)
Vários domínios têm **duas implementações** convivendo, e o frontend às vezes consome a errada:
- **SST**: `health_occupational` (estrutura limpa, tabelas `health_*` quase **vazias**) **vs** `people_management/sst` (tabelas `gp_*`/`sst_*` com os **dados reais**). As telas de exames/EPI/riscos olham para o módulo vazio enquanto há 96 ASOs, 220 EPIs, 15 riscos no outro.
- **Ponto**: `people_management/ponto` (real, em produção) **vs** `hr/rep_integration` (AFD completo, mas **morto** — 404, tabelas vazias, nem montado).
- **RH**: `human_resources` (ativo) **vs** `recruitment`/`retention` (marcados DEPRECATED desde 2026-05-11, mas **ainda são a implementação real**).
- **Operações**: dois arquivos de montagem com prefixos divergentes (PT fantasma vs EN ativo).
> **Impacto:** dado inconsistente na tela, manutenção confusa, risco de "sumiço" silencioso. **Causa:** módulos nasceram em sessões diferentes sem consolidação — exatamente o que vimos no Portal do Cliente.

### Padrão B — O elo posto↔cliente quebrado (impacto transversal)
`posts.client_id` preenchido em **1 de 12**; `posts.ged_client_id` e `contract_id` **100% NULL**; `employees.cliente_id`/`posto_atual_id` **100% NULL**. Hoje o vínculo só funciona por **nome** (ILIKE), e mal.
> **Quebra:** faturamento por posto/contrato, rateio de custo por cliente, relatórios por condomínio, o Portal do Cliente vendo seus postos, escala→contrato→NF. **É o mesmo problema que me forçou a escopar o Raio-X por nome.** É a correção de maior alavancagem do ecossistema.

### Padrão C — Tabelas/recursos prontos mas vazios (feature sem operação)
Muita feature construída e **nunca usada**: substituições (0), advertências (0), ocorrências (0), checkpoints de ronda (0), respostas de clima (0), avaliação 360 (0 respostas), AFD (0), justificativas de ponto (0). O código está pronto; falta **operação/seed** e, em alguns casos, a tela fica permanentemente vazia.

### Padrão D — Bugs de ordenação de rota (500s)
Rotas estáticas declaradas **depois** de `/{id}` → o id captura a palavra. Confirmado em `/medidas-administrativas/stats` (500: "invalid UUID 'stats'"). É o mesmo padrão de bug que já corrigi em outros módulos — provavelmente há mais.

### Padrão E — Compliance legal ausente
- **SST**: eSocial **S-2220/S-2240 não existe** (só etiqueta JSON). LTCAT/PPP com dados hardcoded. Bloqueador legal.
- **Ponto**: **AFD (Portaria 671) não é gerado** em produção (existe código capaz, mas morto). Folha de ponto é HTML, não AFD. Hoje o registro legal depende do próprio Tangerino.

### Padrão F — Bugs concretos pontuais (quick wins)
Lista no §4 — vários são correção de 1 linha que destravam uma tela inteira.

---

## 3. Módulo a módulo (o essencial)

### 🟢 Portal do Funcionário — 82%
- **Pronto:** auth E2E seguro (JWT scoped `employee_portal`, primeiro-acesso/reset self-service p/ os 53 funcionários), contracheque REAL (`hr_payslips`, PDF gerado), treinamentos/certificados/benefícios/CCT reais, dados pessoais editáveis. Todas as 10 telas wired.
- **Bugs:** (1) `my-schedules` → **500** (schema `posto_atual_nome: str` recebe `None`; fix 1 linha). (2) `my-vacations` lê tabela **errada** (`vacation_requests` legada em vez de `hr_vacation_requests`) → saldo sempre "30/0".
- **Falta operação:** só 2/53 funcionários definiram senha; DP ainda não publicou documentos/comunicados (telas prontas, vazias).

### 🟢 RH estratégico — 78%
- **Pronto (sobe em produção):** Recrutamento+Seleção (95%, com IA de matching real), Treinamento (90%, integra SST), Avaliação de Desempenho (90%), Plano de Carreira (90%), Currículos/parser (PyMuPDF+Anthropic), Reembolso (85%), Onboarding (85%). Dados reais nas tabelas.
- **Gaps:** **Clima** (45% — NPS/satisfação são `None` fixo, alerts hardcoded, sem coleta de resposta na tela RH; o fluxo real vive noutro módulo `/climate/*`). **Turnover** (60% — bug `data_demissao` vs `data_desligamento` faz `/motivos` retornar vazio; IA de predição é código morto). **Avaliação 360** (75% — completa, mas nunca rodou E2E: 1 ciclo draft, 0 respostas). **Cargos & Salários** (30% — não existe grade própria; só CCT).

### 🟡 Saúde Ocupacional — 58%
- **Pronto:** API (65+ endpoints, 0 erros 500), frontend bem feito (React Query), Celery agendado (5 verificações), dados reais (96 ASOs, 220 EPIs, afastamentos, CAT, riscos, CIPA).
- **Crítico:** **split-brain** (telas exames/EPI/riscos olham o módulo vazio); **`sst_cipa_reunioes` corrompida** (2833 linhas idênticas — seed em loop); **eSocial S-2220/S-2240 inexistente**; LTCAT/PPP hardcoded; IA preditiva de acidentes (sklearn) é código morto; registro do router SST silencioso (`except: pass` esconde falha).

### 🟡 Ponto Eletrônico — 58%
- **Pronto (operacional):** ingestão automática Tangerino (sync horária real, 4158 batidas, 55 funcionários), espelho, dashboard, justificativas (com SAVEPOINT correto), relatório de inconsistências CCT.
- **Crítico:** **BUG `registrar_ajuste`** insere `employee_id = hash()%int` numa coluna **uuid** → `/ponto/ajuste` quebrado (corrupção). **AFD/Portaria 671 não gerado** (subsistema morto). **Fechamento mensal calcula totais fictícios** (extras/faltas/noturno = 0). Banco de horas não persistido. Almoço quase não capturado (1 batida `saida_almoco` em 4158). Geofence/facial são "feature fantasma" (0% das batidas têm geo). occurrences/absences Sólides nunca importadas (relatório de assiduidade incompleto). TZ inconsistente (utcnow vs Manaus).

### 🟡 Operações — 58%
- **Pronto (código ~85%):** controllers completos (posts/allocations/scales/shifts/substitutions/disciplinar/ocorrências/rondas), gerador de escala determinístico (12x36, 6x1, 5x2…, feriados AM), services de IA (substituição/disciplinar), frontend 100% cabeado.
- **Crítico:** **vazio de dados** (escalas só `draft`, substituições/advertências/ocorrências = 0, 0 check-ins); **elo posto↔cliente quebrado** (Padrão B); **bug 500** `/medidas-administrativas/stats`; **publish de escala não opera** (não notifica funcionário — PENDENTE linha 429 — nem cria registro de ponto; passa `funcionarios=[]` ao evento); 12x36 do gerador é simplificado (carga horária pode sair errada p/ folha); over-allocation sem validação (Gelain required=1, current=3); 2 posts de teste `ZZE2E_` + arquivos `.bak/.corrupted` no front.

---

## 4. Bugs concretos / quick wins (correções pequenas, alto impacto)

| # | Onde | Bug | Fix |
|---|---|---|---|
| 1 | `employee_portal/schemas/schedule.py:51` | `my-schedules` 500 p/ quem não tem posto | `posto_atual_nome: str \| None = None` |
| 2 | `employee_portal/.../my_vacations_controller.py:96` | Férias lê tabela legada errada | apontar p/ `hr_vacation_requests` + status maiúsculo |
| 3 | `ponto/.../dashboard_service.py:768` | `registrar_ajuste` grava int em coluna uuid | `CAST(:eid AS uuid)`, remover `hash()` |
| 4 | operacional disciplinar router | `/medidas-administrativas/stats` 500 | declarar `/stats` antes de `/{id}` |
| 5 | `human_resources/.../turnover_controller.py:92` | `/motivos` vazio (coluna divergente) | COALESCE `data_demissao`/`data_desligamento` |
| 6 | `sst_cipa_reunioes` (dado) | 2833 duplicatas idênticas | dedup + UNIQUE constraint |
| 7 | `people_management/__init__.py:83` | router SST `except: pass` esconde erro | logar a exceção |
| 8 | `time_record_service.py:787` | fonte Tangerino detectada como "portal" | corrigir prefixo `tang-` |

---

## 5. Bloqueadores estruturais (o trabalho de verdade)

1. **Reconciliação posto↔condomínio↔cliente↔contrato** (Padrão B) — script de backfill (`posts.name ↔ condominios.nome`, não `clients`), popular `client_id`/`ged_client_id`/`contract_id` + `employees.cliente_id`/`posto_atual_id` via alocações ativas. **Destrava faturamento, portal, relatórios e operações de uma vez.**
2. **Consolidar os módulos paralelos** (Padrão A) — decidir a fonte única em SST/Ponto/RH, repontar o frontend e descontinuar/limpar o lado morto.
3. **Compliance**: AFD (Ponto) e eSocial S-2220/S-2240 (SST) — reaproveitar a infra de `government_integrations` + certificado A1. É esforço grande, mas é bloqueador legal real.
4. **Fechar o ciclo de escala** (Operações): publish → notifica funcionário → cria registro de ponto → fechamento mensal com cálculo CCT real (extras/noturno/faltas) — hoje os totais são fictícios tanto no ponto quanto na escala.

---

## 6. Roadmap sugerido (ordem de execução)

**Fase 1 — Quick wins (1 frente, ~1 dia):** os 8 bugs do §4. Destrava telas inteiras com correções pequenas e elimina os 500.

**Fase 2 — O elo posto↔cliente (1 frente, ~1-2 dias):** o script de reconciliação. Maior alavancagem do ecossistema inteiro.

**Fase 3 — Consolidação dos split-brains (1 frente por módulo, paralelizável):** SST (unificar fonte + limpar CIPA), Ponto (decidir AFD próprio vs Tangerino, montar ou remover o módulo morto), RH (clima + turnover + validar 360).

**Fase 4 — Cálculo & operação:** motor de apuração de horas CCT (ponto + escala), banco de horas persistido, importar intrajornada/ausências do Tangerino.

**Fase 5 — Compliance:** AFD (Portaria 671) e eSocial SST (S-2220/S-2240).

**Fase 6 — Operação/seed & UX:** popular as features vazias (substituições, advertências, ocorrências, clima, 360), onboarding dos 53 funcionários no portal, DP publicar documentos, limpar dados/arquivos de teste.

---

## 7. Recomendação

As **Fases 1 e 2 são as de maior retorno** e podem começar já — quick wins + o elo posto↔cliente resolvem a maior parte da sensação de "gap/bug" e destravam vários módulos de uma vez. As Fases 3-5 são paralelizáveis por módulo (ótimo caso pra multiagentes ou terminais paralelos). A Fase 5 (compliance) é a de maior esforço e a que eu recomendaria planejar com calma.

**Posso atacar de forma autônoma e paralela** (como fiz aqui na auditoria e no Portal do Cliente). Se você abrir 1-2 terminais extras, dá pra rodar consolidações de módulos diferentes em paralelo sem conflito (cada um mexe em arquivos distintos). Quando você decidir o escopo/ordem, eu executo — com o mesmo padrão de E2E real no frontend que você exigiu.
</content>
