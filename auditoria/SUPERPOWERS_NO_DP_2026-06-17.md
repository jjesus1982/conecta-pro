# O que as skills Superpowers podem fazer no módulo de Departamento Pessoal (DP) — Conecta PRO

**Data:** 2026-06-17 · **Escopo:** módulo `hr` (DP-folha) + sub-módulo DP de `people_management`.
**Natureza:** as skills do Superpowers são **processo** (COMO eu trabalho), não features prontas. Este relatório traduz cada uma em **uso concreto no DP**, onde o risco é **dado trabalhista real** (folha, férias, ponto, ASO, EPI) — errar aqui = erro trabalhista. Por isso o DP é, de todos os módulos, o que mais se beneficia de disciplina de processo.

## Contexto real do DP hoje (base do mapeamento)
- Dado real sensível: ~58 employees, **67 períodos de férias** (`hr_vacation_periods`), folha, ponto eletrônico, SST (ASO/EPI/PCMSO).
- Pendências já mapeadas (da rodada de migrations):
  - **5 models suspeitos** com FK→`funcionarios` (tabela inexistente; real é `employees`): `employee_documents`, `employee_notifications`, `employee_payroll_configs`, `employee_preferences`, `payroll_events`.
  - **2 tabelas rename-com-dado**: `employee_vacation_periods`↔`hr_vacation_periods` (67 reais), `employee_vacation_requests`↔`hr_vacation_requests` (15).
- hr saiu de **10 FAIL → 7** na rodada anterior; o que resta é decisão + código.

---

## Mapa: skill → uso concreto no DP

### 🧭 Antes de codar (entender e desenhar)
| Skill | O que faz no DP |
|---|---|
| **brainstorming** | Antes de mexer em férias/folha, explora intenção e regras (CLT, CCT SINDECOMPRESTS, proporcionalidade, abono pecuniário) **antes** de implementar — evita assumir semântica trabalhista errada. Ex.: decidir se `employee_vacation_periods` (portal) é rename de `hr_vacation_periods` ou tabela separada. |
| **writing-plans** | Transforma "migrar férias" num plano escrito, revisável, passo a passo, com checkpoints — essencial quando há 67 registros reais em jogo. |
| **finding-schema-drift** (nossa) | Detecta drift model↔banco do DP read-only e classifica nos 3 baldes. Já roda: aponta os 5 suspeitos `funcionarios` e as 2 tabelas de férias como balde 3 (parar). |

### 🏗️ Executando com segurança
| Skill | O que faz no DP |
|---|---|
| **executing-plans** | Executa o plano de férias/folha com checkpoints de revisão entre passos — não despeja tudo de uma vez sobre dado real. |
| **test-driven-development** | Escreve o teste **antes** do código de cálculo (férias, 13º, rescisão, horas extras, DSR). No DP, cálculo errado é passivo trabalhista — TDD garante que a fórmula foi vista falhar e depois passar. |
| **subagent-driven-development** / **dispatching-parallel-agents** | Quebra trabalho independente do DP em agentes paralelos: ex. um cuida de `employee_documents`, outro de `employee_notifications`, outro de `payroll_*` — sem estado compartilhado. |
| **using-git-worktrees** | Isola a refatoração do DP (ex.: corrigir FK→`employees` nos 5 models) num worktree, sem sujar o workspace atual nem arriscar produção. |

### 🔍 Depurando e verificando (onde o DP mais ganha)
| Skill | O que faz no DP |
|---|---|
| **systematic-debugging** | Quando um endpoint de DP dá 500 (ex.: ponto, ASO, contracheque), exige **achar a causa raiz antes de remendar**. Já provou valor: foi o método que pegou o `periodstatus` mal classificado (enum do banco ≠ enum do código). |
| **verification-before-completion** | Proíbe dizer "folha corrigida/ponto OK" sem rodar a verificação e mostrar o output. No DP isso é regra de ouro: evidência antes de afirmar que o cálculo trabalhista está certo. |
| **superpowers:code-reviewer** (agente) | Revisa a implementação do DP contra o plano + padrões, após cada etapa grande (ex.: novo cálculo de rescisão). |
| **requesting-code-review** / **receiving-code-review** | Pede revisão ao concluir features de DP (folha, férias) e aplica o feedback com rigor técnico, não concordância performática. |

### 🚢 Fechando
| Skill | O que faz no DP |
|---|---|
| **finishing-a-development-branch** | Ao terminar uma feature de DP, conduz a decisão de merge/PR/cleanup de forma estruturada. |
| **writing-skills** | Vira padrão recorrente do DP em skill própria (ex.: "validador de cálculo de folha CCT 2026"). |
| **using-superpowers** / **writing-skills** | Descobrir/usar/criar skills do projeto. |

### 🧠 Memória (instalado nesta sessão)
| Plugin | O que faz no DP |
|---|---|
| **episodic-memory** | Lembra entre sessões as decisões de DP já tomadas (DP 25/25, SST 100%, correções RH) — evita eu re-descobrir o que já foi auditado/decidido. Os relatórios `project_dp_25_25_aprovado`, `project_sst_sessao26`, `project_rh_sessao27` viram contexto recuperável. |

---

## Exemplo concreto — como as skills encadeiam num pendente real do DP

**Objetivo:** resolver os 5 models suspeitos do DP (FK→`funcionarios` inexistente) + decidir as férias.

1. **finding-schema-drift** (read-only) → confirma os 5 suspeitos + 2 tabelas de férias (já feito).
2. **brainstorming** → `funcionarios` deveria ser `employees`? as férias do portal são rename de `hr_vacation_periods` (67) ou tabela nova? (decisão de negócio, não adivinhar).
3. **writing-plans** → plano: corrigir FK no model `employees`, migrar/parear férias, com backup→staging→prod e checkpoints.
4. **using-git-worktrees** → isola a mudança de código dos models.
5. **test-driven-development** → teste que prova que o portal lê os 67 períodos corretos antes de mexer.
6. **executing-plans** + **systematic-debugging** → executa; se 500, causa raiz primeiro.
7. **verification-before-completion** → roda o `drift_finder` de novo: hr FAIL deve cair; mostra dado intacto (67 férias preservadas).
8. **superpowers:code-reviewer** + **requesting-code-review** → revisão antes do merge.
9. **finishing-a-development-branch** → merge/PR estruturado.

---

## O que as skills NÃO fazem (honestidade)
- **Não são features de DP.** Não calculam folha, não geram eSocial, não emitem ASO. Elas garantem que, quando EU implementar isso, seja feito com causa-raiz, teste-primeiro, verificação e revisão.
- **Não substituem decisão trabalhista/jurídica.** Regras de CLT/CCT, proporcionalidade de férias, semântica de rescisão = decisão sua/contábil; as skills só impedem que eu adivinhe.
- **Não tocam produção sozinhas.** O princípio "dado real → parar e trazer evidência" continua valendo.

## Recomendação de uso no DP (prioridade)
1. 🥇 **verification-before-completion + systematic-debugging + TDD** — o tripé que protege dado trabalhista. Use em todo cálculo/endpoint de DP.
2. 🥈 **finding-schema-drift + brainstorming + writing-plans** — para encarar os pendentes (funcionarios FK, férias) sem mina.
3. 🥉 **using-git-worktrees + code-reviewer + finishing-a-development-branch** — para entregar com segurança e revisão.
