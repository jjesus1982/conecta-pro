# Revisão operacional — rondas, ocorrências, comunicação, escalas, alocações, presença, triagem (agente só-leitura, 08/09/2026 ~05h)

210 rotas revisadas — VIVA 178 (29 também INTERNA via MCP/agentes/tasks) · LIGAR 6 · MORTA 26.

## Defeitos (mais grave primeiro)
1. `communication/repositories/communication_repository.py:324-333` + `communication/models/announcement.py:163-186` — classe 2 — POST /comunicados/{id}/publicar sempre 500: chama `announcement.can_be_published()` (não existe) e atribui `publish_at/published_at/published_by` que são @property sem setter. Front chama (`useAnnouncements.ts:70`). Correção: escrever em status/data_publicacao/created_by e definir can_be_published.
2. `services/scale_generator.py:172-174, 202-203, 226-227` — classe 5 — 12x36 gerado errado: `if day % 2 == 0: idx += 1` deixa o mesmo funcionário em D1 e D2; com 1 funcionário ele recebe diurno E noturno todo dia. Correção: `idx = day % len(...)` e exigir ≥2 pessoas por turno.
3. `controllers/falta_substituto_controller.py:298-301, 394-398` — classe 5 — substituto exclui só turno no mesmo dia: noturno D-1 (19h–07h) é sugerido para o diurno D às 07h → 0h de interjornada (CLT art. 66, 11h). Correção: excluir noturno D-1 e diurno D+1.
4. `models/shift.py:189-194` + `repositories/shift_repository.py:370` — classe 5 — check-out calcula HE com regular_hours=8.0; turno 12x36 fecha com 4h extras em todo check-out; /reports/hours soma isso. Correção: regular = planned_hours.
5. `repositories/allocation_repository.py:471-478` — classe 5 — encerrar alocação/demissão não cancela turnos futuros: KEYSON (demitido 14/08) segue com allocation active no Prime Arena e 12 shifts scheduled de 08/09 a 30/09. Correção: terminate cancela shifts ≥ end_date (como grade_controller.py:616 faz) e o desligamento no DP encerra a allocation.
6. `communication_repository.py:527` — classe 2/3 — GET /comunicados/{id}/leituras 500: `_get_total_targets()` não existe. Correção: coluna total_destinatarios.
7. `controllers/allocation_controller.py:53` + `allocation_repository.py:125-134` — classe 3 — POST /allocations/ duplicada: ValueError não tratado → 500. Correção: 409.
8. `frontend/src/services/allocations.ts:23`, `posts.ts:23`, `occurrences.ts:20,60` — classe 6/3 — clássico usa PUT; backend só PATCH → 405 (clássico, fora do escopo).
9. `triage/controllers/triage_controller.py:111, 170, 204-205, 221-222, 246` — classe 4 — CURRENT_DATE (UTC) para "passagens de hoje" e vencimentos; data_turno é gravado com date.today() Manaus. Correção: Manaus.
10. `repositories/scale_template_repository.py:80, 104, 280, 289` + banco — classe 5/6 — os 4 scale_templates têm tenant_id=0000…; get_tenant_id resolve ad9abb59… → GET /scales/templates/ devolve 0, /{id} 404. Correção: migrar tenant_id das linhas ou não filtrar (single-tenant).
11. `controllers/substitution_controller.py:167-171` — classe 3 — POST /substitutions/suggest sempre [] (implementação comentada). Correção: delegar ao SQL do falta_substituto ou remover.
12. `inspection_rounds/controllers/inspection_round_controller.py:613, 652` — classe 2 — `service.register_occurrence` / `apply_disciplinary_action` não existem → 500. Sem chamador. Remover.
13. `inspection_rounds/repositories/inspection_round_repository.py:162-163` — classe 4 — get_rounds_scheduled_today usa utcnow(). Correção: Manaus.
14. `controllers/aliases.py:80-84, 113-114, 130` — classe 5/6 — /ocorrencias/ sem is_active, /ocorrencias/stats conta canceladas como resolvidas, /ferias/ lê vacation_requests órfã. Sem chamador. Apagar os 5 aliases.
15. `controllers/reports_controller.py:130-146`, `dashboard_controller.py:459` — classe 6 — /reports/overtime duplica /reports/hours; /unificado/kpi-trends duplica /kpi-trends. Remover.
16. `occurrences/models/occurrence_comment.py:105-107`, `occurrence_attachment.py:142-144` — classe 2 — back_populates sem relationship em Occurrence: importar derruba todos os mappers. Hoje ninguém importa. Corrigir.
17. `controllers/scale_controller.py:443-450` — classe 6 — publish com notify_employees só loga.
18. `vacations/controller.py:148-209` — classe 6 — 5 rotas de escrita 501 por design.

## MORTA (26)
PATCH /shifts/bulk · DELETE /allocations/bulk · PATCH /allocations/bulk · GET /comunicacao/ws/status · GET /ws/status · aliases /ocorrencias/, /ocorrencias/stats, /ferias/, /scale-templates/, /banco-horas/ · /unificado/dashboard, /metricas, /ocupacao, /resumo-dia, /kpis, /kpi-trends · GET /reports/overtime · POST /rondas/{id}/registrar-ocorrencia · POST /rondas/{id}/aplicar-medida-disciplinar · POST /vacations · GET/PATCH /vacations/{id} · POST /vacations/{id}/approve|reject · DELETE /vacations/{id} · GET /scale-optimizer/status.

## LIGAR (6)
PUT /grade/{post_id}/colaborador (redesenhar) · PATCH /scales/{id} · POST /scales/{id}/reject · DELETE /substitutions/{id} · DELETE /time-bank/{id} · GET /rondas/gestao/resumo-inspetores.

## Notas
Classe 1 limpa (17 models × banco). Classe 7 limpa (session comita no fim da request). Classe 8: nenhum WhatsApp; Telegram é no-op. Varredura GET com token: 93 chamadas, único 500 foi /leituras.
