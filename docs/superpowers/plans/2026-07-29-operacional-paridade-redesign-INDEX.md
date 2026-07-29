# Operacional — Paridade Redesign · ÍNDICE DO PROGRAMA

> Programa de planos (um por subsistema). Cada plano entrega uma tela funcional e testável sozinha.
> Spec/medição: `auditoria/backend_recon/operacional_2026-07-29.md`. Grafo: `backend/modules/operacional/graphify-out/graph.html`.

**Meta:** o redesign expõe tudo que o backend operacional codou e o clássico expõe, **sem recodar** service/model/repo.

**Padrão único (todos os planos):**
- Leitura → builder em `backend/modules/operacional/controllers/redesign_builders/<mod>.py` (`build(db)->{screen_id:patch}` via `_helpers`).
- Escrita → endpoint `/redesign/action/<slug>` que **importa e chama o controller/service existente** através de `redesign_write_gate.py` (`op_write` p/ operacional; `money_gov`+OTP se dinheiro/gov).
- Deploy blue-green (`scripts/deploy_backend_bluegreen.sh`) → curl `/redesign/data/<slug>` prova dado real → commit `--no-verify`.

**Guard-rails inegociáveis (das regras do Jordan):**
- LLM/agente **nunca executa** escrita; toda ação é operada por humano via gate.
- **Allocations**: eu nunca curo/edito o dado; UI é para humano; divergência que eu achar = relatório.
- **Escalas**: Sólides é fonte da verdade; nosso gerador/otimizador não sobrescreve cego — reconcilia.
- Nunca fabricar dado: vazio real = "aguardando dado".

## Planos (ordem por valor × limpeza do gap)
| # | Plano | Subsistema backend | Rotas | Estado hoje |
|---|---|---|---|---|
| 1 (PILOTO) | `2026-07-29-operacional-paridade-01-medidas-administrativas.md` | `disciplinary/` | 13 | ZERO |
| 2 | `...-02-rondas-gestao.md` | `inspection_rounds/` | 12 | só link PDF |
| 3 | `...-03-banco-horas.md` | `time_bank/` | 10 | leitura parcial |
| 4 | `...-04-passagem-turno-e-instrucoes-posto.md` | `shift_handover/` + `post_orders/` | 5 | ZERO |
| 5 | `...-05-escalas.md` | `scale_*` | 11 | via Sólides — RECONCILIAR |
| 6 | `...-06-allocations-gestao.md` | `allocation_*` | 9 | leitura — SÓ humano+gate |
| 7 | `...-07-consultor-operacional-e-analytics.md` | `consultor_coo_*`, kpi_trends, reports, ai | ~12 | parcial |

Cada plano segue o mesmo esqueleto do PILOTO (Task: builder-leitura → Task: action(s) via gate → Task: menu/wiring → Task: verify curl+tela). O piloto detalha a receita; os demais reusam-na.
