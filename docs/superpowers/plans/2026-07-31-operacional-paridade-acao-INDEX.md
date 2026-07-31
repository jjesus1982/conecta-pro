# Operacional — Paridade de AÇÃO (desligar o clássico) · ÍNDICE DO PROGRAMA

> Programa de planos (um por subsistema). Meta: ligar no redesign as ~147 escritas do backend
> operacional que ainda só existem no clássico, para poder **desligar o clássico**.
> Reuso confirmado (recon + grafo): cada ação tem controller/service PRONTO — **nada a recriar**.

**Spec/medição:** `auditoria/backend_recon/operacional_2026-07-29.md`, lista de escritas em
`/tmp/.../scratchpad/op_writes.txt` (147 rotas POST/PUT/PATCH/DELETE), grafo `backend/modules/operacional/graphify-out/`.

## Molde único (todos os planos) — já provado 6× nesta sessão
Em `backend/modules/operacional/controllers/redesign_builders/operacional.py`:
1. **Ação** = `@router.post("/action/<slug>")` com `CurrentActiveUser` que **importa a função do controller/service existente** e a chama através de `redesign_write_gate.op_write` (operacional) ou `money_gov`+OTP (dinheiro/gov). Valida ANTES do gate (evita poison-marker).
2. **Form** = screen `{type:"form", submit:{endpoint:"/api/v1/redesign/action/<slug>", okMsg}, fields:[...]}` em `EXTRA_MENU` (id novo) ou reusando id de menu existente. Selects preenchidos por SQL do banco (nunca digitação livre de id).
3. **Teste-oráculo** em `backend/scripts/orq/test_acao_*_redesign.py`: chama a função do endpoint direto com user fake → confere efeito no banco → **limpa** (net-new).
4. Deploy: source commitado (sessões paralelas bakeiam do source); commits `git add <arqs> && git commit -- <arqs>` (índice compartilhado).

## Guard-rails inegociáveis
- **allocations (6 escritas): NÃO wire** — curado à mão pelo Jordan, read-only p/ agentes.
- **vacations (5): NÃO wire** — backend marca "escrita é responsabilidade do módulo DP".
- **dinheiro/gov** (pagar-diaristas, fiscal/rpa, gerar-guia): `money_gov`+OTP humano; nunca happy-path.
- **LLM/agente nunca dispara**; humano opera via `CurrentActiveUser`. Nunca fabricar dado.

## Planos por subsistema (ordem por valor gerencial)
| # | Plano | Subsistema | Escritas a ligar | Reuso |
|---|---|---|---|---|
| 1 (PILOTO) | `...-acao-01-medidas-fluxo-aprovacao.md` | disciplinary | submeter/aprovar/rejeitar/gerar-documento (+assinar/recusar) | `DisciplinaryService.submit_for_approval/approve/reject/generate_document/sign_document` |
| 2 | `...-acao-02-scales-ciclo.md` | scales | criar/gerar/otimizar/submeter/aprovar/publicar/rejeitar/editar/excluir/templates | `ScaleService`/`scale_generator.generate`/`ScaleRepository`; Sólides=fonte-verdade, reconciliar |
| 3 | `...-acao-03-rondas-ciclo-campo.md` | inspection_rounds | iniciar/pausar/retomar/concluir/cancelar/checkpoints(CRUD+fotos)/registrar-ocorrência/aplicar-medida | `inspection_round_controller` (start/pause/resume/complete/cancel/create_checkpoint/register_occurrence) |
| 4 | `...-acao-04-time-bank.md` | time_bank | aprovar/compensar/rejeitar/editar/excluir | `TimeBankRepository.approve`/`time_bank_controller.compensate_hours` |
| 5 | `...-acao-05-substitutions-shifts.md` | substitutions+shifts | criar/confirmar/completar/rejeitar; shifts bulk/mark-missed | `substitution_service`, `shift_controller` |
| 6 | `...-acao-06-diaristas-gestao.md` | diaristas | ativar/desativar/avaliar/assignments; (pagamentos/fiscal=money_gov OTP) | `DiaristService` (activate/deactivate/evaluations) |
| 7 | `...-acao-07-comunicacao.md` | communication | publicar comunicado/marcar-lido/acknowledge alerta/marcar-todas | `announcement_service.publish`, alert ack |

FORA do programa (guard-rail): allocations, vacations. Money/gov (pagar-diaristas, fiscal/rpa) entram só com OTP.

Cada plano segue o esqueleto do PILOTO. Concluído todos → o clássico do operacional pode ser desligado
(exceto o que é intencionalmente de outro módulo: allocations-curadoria, férias-DP).
