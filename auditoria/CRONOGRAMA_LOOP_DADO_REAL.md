# CRONOGRAMA DO LOOP — Sweep de "dado simulado/vazio vs real" (Gestão de Pessoas)
*Pedido do Jordan (2026-07-01): vários campos em vários módulos de GP mostram informação SIMULADA (hardcoded/mock) ou VAZIA lida como se fosse real. Isso vira item recorrente do loop — um oráculo de veracidade do dado.*

## A regra (o oráculo de veracidade)
**Todo campo exibido tem que ter um FATO no banco por trás.** Um campo é REPROVADO se:
- **Hardcoded/mock:** retorna um literal chumbado no código (ex: `"pesquisas_realizadas": 0` fixo; dados de exemplo/`mock`/`fake`/`exemplo`).
- **Fantasma:** lê uma tabela vazia/errada enquanto o dado real está em outra (ex: `health_epi_deliveries`=0 vs `gp_epi_deliveries`=220).
- **Placeholder:** valores `TODO`, `--`, `N/A`, `0.0` fixos, `uuid4()` falso, `random`.

Um campo é APROVADO se o valor vem de query numa tabela populada (ou é **vazio real** honesto — tabela existe, sem dado ainda, e isso é sinalizado como "aguardando dado", não mascarado).

## Como o sweep roda (por módulo)
1. **Inventário:** para cada endpoint/tela de GP, listar os campos exibidos.
2. **Cross-check:** para cada campo, comparar o valor exibido com a **verdade do banco** (a tabela/coluna que deveria alimentá-lo).
3. **Classificar:** REAL · HARDCODED · FANTASMA · VAZIO-REAL · PLACEHOLDER.
4. **Corrigir** HARDCODED/FANTASMA/PLACEHOLDER → ler o dado real (com prova valor-antes→valor-depois).
5. **VAZIO-REAL** → marcar honestamente "aguardando dado" (não mascarar com literal).

## Já pegos (amostra do que o sweep vai sistematizar)
- RH `climate/dashboard`: `pesquisas_realizadas`/`alertas_absenteismo` literais 0 → real 3/3. ✅
- SST `epi/pcmso estatisticas`: liam `health_*` vazio → `gp_*` real. ✅
- Reembolso `/categories`: fallback hardcoded pro enum mascarando `reimbursement_categories`=0.
- (padrão a caçar em TODOS: grep por retornos literais em controllers + tabelas vazias lidas)

## Módulos a varrer (cronograma)
DP/Folha · Ponto · RH · Recrutamento · Retenção · Reembolso · SST · GED · Portal Func · Operações · Área do Cliente.
Método: subagentes read-only em paralelo (como o sweep de CRUD da madrugada) → inventário classificado → correção em lote com prova.

## Gate inforjável do sweep
Nada é "REAL/verde" sem: valor exibido == valor no banco (mesmo funcionário/competência), provado com curl vs query. Onde o campo é cálculo de risco jurídico (folha/eSocial), passa pela **certificação** (item 0). Onde é vazio-real, marca "aguardando dado" — honesto, não teatro.

Ver [[loop-gates-inforjaveis]] e [[project-gp-item-menos1]].

---
## INVENTÁRIO DO 1º SWEEP (2026-07-01, 5 subagentes read-only)

### 🔴 VERMELHOS a corrigir (evidência arquivo:linha)
**Área do Cliente (pior — dado exibido ao CLIENTE):**
- `analytics/conformidade` certidão `expires_at`/`status` **PLACEHOLDER** — `analytics_controller.py:326` comenta *"Simular data de expiracao"* (created_at+30d); status vem de `is_signed`, não da validade real da CND. Fix: usar validade real (robô CND) ou remover o campo.
- `analytics/overview` janela 30d WRONG-MATH (`:73` day-subtraction) · `documentos_baixados` = contagem de ASSINADOS (mislabel `:145`).

**Operações:**
- `dashboard/` `cobertura_atual: 409.1%` WRONG-MATH — `reports_controller.py:219` divide `allocations(45)` por `required_headcount(11)` (incomensuráveis).

**SST (health_occupational fantasma — continuação do B'):**
- `ppra/estatisticas` + `ppra/mapeamentos` lêem `health_risk_mappings` (filtro status='ativo'; real é 'identificado') → 0; real `gp_risks`=15.
- `pcmso/vencimentos` JOIN quebrado (`health_asos→health_medical_exams` vazio); real `gp_asos.data_validade`.
- `epi/ficha/{id}` + listas de entrega → `EPIDelivery`→`health_epi_deliveries`=0 → **500**; real `gp_epi_deliveries`=220.

**GED (fantasma ged_documents=0 vs ged_kit_documents=2046):**
- `/ged/dashboard` + `/people-management/ged/kits/dashboard` (2 controllers byte-idênticos) bloco `documentos` = 0.
- `/ged/stats` + `/documents/stats/summary` = 0.
- `/documents/ai/dashboard` health=100/"excellent" sobre 0 docs (enganoso).
- kit `total_documents` coluna stored-stale (31/38 divergem; ex 3 vs 18).

**Ponto:**
- `dashboard` `banco_horas` = 0.0 HARDCODED (`dashboard_service.py:115` dict literal).
- `relatorio/inconsistencias` `employee_nome: "Emp#<uuid>"` PLACEHOLDER em 277 linhas (`:171,200,227` sem JOIN employees.nome).

**Portal do Funcionário:**
- `dashboard` `workplace`/`next_shift` = null HARDCODED (`portal_service.py:170-228` nunca atribui; dado em `allocations`=58).
- `dashboard` `pending_documents` = `max(0, 0-signed)` fórmula quebrada (`:223`).

**DP/Folha:**
- `hr/payroll/summary` PHANTOM — query usa colunas inexistentes (`total_proventos` vs `total_earnings`...) → except → fallback com `0` hardcoded; real em `hr_payslips` (51). Fix: nomes de coluna certos (`calculo_service` já usa).
- (folha `/calcular`,`/holerite` = simulador CCT hardcoded vs holerite real → risco jurídico, priorizar Domínio; NÃO recalcular)

### 🟡 VAZIO-REAL (honesto — "aguardando dado", NÃO mexer)
RH inteiro limpo. Retention turnover/climate/profile (tabelas novas vazias). portal_notifications=0, ged_document_signatures=0, climate_responses=0, reimbursement_categories=0 (fallback enum), rh_onboarding_checklist=102 (real).

---
## ✅ CORRIGIDOS no 1º ciclo do sweep (2026-07-01, provados + duráveis)
- **Área Cliente** certidão: validade SIMULADA → real (ged_certidoes.expiry_date; CRF FGTS vence 2026-07-06). commit 55f6119c
- **DP** payroll/summary: colunas erradas/fallback 0s → hr_payslips real (R$97.504). 46bb35b9
- **Ponto** inconsistências Emp#→nome real · banco_horas 0.0→nao_calculado honesto. bf5ed695
- **Operações** cobertura 409%→100%. bf5ed695
- **SST** ppra(15/2)/pcmso(200)/epi-ficha(200,5) — health_*→gp_* real. (SST batch)
- **GED** dashboard documentos 0→2046 real (ged_kit_documents; 2 controllers). (GED batch)
- **Portal Func** workplace/next_shift/pending null→real (CONDOMINIO IDEAL FLORES/12x36/34). (Portal batch)

## 🟡 RESTANTE (mais fino, prioridade menor / precisa cuidado ou dado)
- **GED** /ged/stats, /documents/stats/summary, /documents/ai/dashboard → ORM Document→ged_documents (repoint do MODEL, maior, afeta todas as queries Document — fazer com cuidado). Kit total_documents stored-stale (31/38) → COUNT ou trigger.
- **Reembolso** /categories fallback enum mascarando tabela vazia (by-design; seed ou label).
- **Folha** /calcular,/holerite simulador CCT vs holerite real → RISCO JURÍDICO, priorizar Domínio (NÃO recalcular). Ponto banco de horas / extras/noturno idem.

---
## ✅ 2º CICLO — 8 MÓDULOS DE GP (2026-07-02) — pedido do Jordan "todos os 8 alimentados com dado verdadeiro, loop infinito"
Método: 8 auditores read-only (1 por módulo) → inventário → 6 fixers paralelos (papéis separados: finder≠fixer≠verificador=eu) → deploy+verificação por curl vs banco → bake.

### Corrigidos + PROVADOS (curl vs query):
- **DP (6)**: employees/stats ativos 60→50 (removido `or is_active` sujo; inativos=21); employee_name real via JOIN em Rescisão/Contratos/Benefícios (schema+join)/Licenças (COALESCE nome). Prova: terminations→"ANTONIO DINIZ...", contracts→"MALAQUIAS...".
- **SST (1 back)**: ppra/mapeamentos lia health_risk_mappings (status='ativo'→0); repontado p/ gp_risks + schema RiskMappingResponse relaxado (id str, campos opcionais). Prova: 0→15 mapeamentos reais.
- **SST (2 front)**: exames/riscos page.tsx liam chaves inexistentes (total_exames→total_exames_ano etc.; total_riscos→total_riscos_identificados; rótulos "Setores Mapeados"→"Mapeamentos Ativos", "Medidas Implementadas"→"Riscos Alto Nível"). Cards 0→real.
- **Portal (4)**: dashboard caía em fallback (schema next_shift datetime→str; escala "44h" real); my-schedules 500 (posto_atual_nome str→str|None); my-documents fantasma (só assinaturas→ged_kit_documents real); férias balance hardcoded 30→employee_vacation_periods. Prova: get_dashboard→"PAULO DA SILVA LAMEGO"/next_shift "44h".
- **GED (5)**: total_documents/documents_signed/completion_percentage STORED-STALE (31/38 divergem) → COUNT ao vivo em ged_kit_documents (kit_service._to_response, auto_assemble detail/summary/list). Prova: average_completion 19.9→26.1; kit stored=0 vs real=138.
- **Operações (4)**: kpi-trends cobertura 409%→≤100% (métrica por posto+cap); série plana→snapshot vigência-aware; trend "estavel" hardcoded→removido; predicoes []→removido.
- **Ponto (2)**: /ajuste 500 (hash int→uuid) → UUID direto (500→422 valida); /fechamento horas 8h/dia fabricadas + noturnas 0.0 → horas reais das batidas (pareamento entrada→saída, janela 22-05h).
- **RH (2)**: turnover recalcular/recalcular-todos injetavam features de demonstração (faltas=1/dist=15/dias_sem_aumento=180) → tempo_empresa real (data_admissao) + resto 0/neutro honesto; batch itera funcionários reais.
- **Reembolso: 0 reds** (categories = fallback enum documentado, não mock).

### Deploy: docker cp + restart (provado) → bake backend + build frontend (durável).
### RESTA (fila): DRE/BI financeiro fabricado, dashboard executivo R$2,85M fake, NFC-e/eSocial gov fabricados — ver SWEEP_ERP_MOCK_2026-07-02.md (fora de GP; tratar quando Jordan pedir).
