# people-management — 273 rotas sem chamador (08/09/2026)

Medição: `checar_cobertura_rotas.py` T0 → bucket `nenhum` com prefixo `people-management/*` (254) + `users/*` e sobras (19).
Vereditos por agente (leitura de código + `count(*)` no banco, só SELECT).

| Veredito | Qtde | O que foi feito |
|---|---|---|
| MORTA | 184 | apagadas via `podar.py` (handler + decorator). Lista: `morta_pm_20260908.tsv` |
| LIGAR | 6 | tela/ação no redesign (lote LIGAR deste dia) |
| INTERNA / alias | restante | ficam — handler compartilhado por dupla montagem ou usado por MCP/orquestrador/oráculo |

LIGAR (6): `POST portal/self-service/solicitar-homologacao` (espelho), `pagar-via-pix` preview/status (DP payslips), `PUT admin/cct/cargos/{id}`, `DELETE admin/cct/feriados/{id}`, `ponto/onboarding/completude`.

Efeitos colaterais corrigidos no mesmo lote: `cct/schedule_controller.get_jornadas_permitidas` e `cct/compliance_controller.get_resumo_compliance` (usados pelo builder `rh` por alias `Sc.`/`Cp.`) voltaram de HEAD; `benefits_router` e `recruitment_router` voltaram aos agregadores (redesign chama `/people-management/hr/benefits` e `/human-resources/recruitment/resume/*`). `reimbursement_router` e `cct_benefits_router` saíram do agregador hr: o redesign chama `/api/v1/reimbursements/*` e `/api/v1/cct/*` direto.
