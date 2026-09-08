# Revisão operacional — diaristas / fiscal / diárias (agente só-leitura, 08/09/2026)

Conclusão: o cadastro VIVO é `diaria_*` (62 diaristas, 427 lançamentos jun–set/2026). O universo `diarist_*` + fiscal (51 rotas, 9 tabelas) tem 3 linhas de teste, 0 movimento desde 27/01/2026 e serviço quebrado em todo caminho de escrita. Recomendação: desmontar `diarist_router` e `diarist_fiscal_router`, mover `consulta-cpf` para `/diarias` (corrigindo a BrasilAPI) e revisar as 6 actions do redesign que reutilizam `DiaristService` (ativar/desativar/avaliar/fechamento/escala-criar/assignment-criar).

## Defeitos
1. `diarist_service.py:171–185` create_assignment lê `data.descricao/hora_inicio/hora_fim` inexistentes no schema → 500. Model mapeia tipo/status/recorrencia como String e dias_semana como JSONB; banco tem ENUMs `assignment_type/assignment_status/recurrence_type` e `weekday_array2[]` → `operator does not exist: assignment_status = character varying` (reproduzido em GET /assignments?status=ATIVO). Afeta POST/GET assignments, cancel, e actions redesign diarista-assignment-criar/cancelar.
2. `diarist_service.py:398–430` create_payment usa campos que não existem em DiaristPaymentCreate → 500. generate_payment_from_schedules (507–516) monta schema sem campos obrigatórios → 500.
3. `diarist_service.py:791–804` generate_payroll_payments: forma_pagamento String em ENUM payment_method; schedules_ids JSONB em varchar[] → todo INSERT falha, engolido, sessão abortada, 200 com total_gerados=0. Sem dedupe.
4. `schemas/diarist_schemas.py` 441–483, 242–290, 521–560: Response exige campos que não existem no model/banco → 500 assim que houver linha. POST /evaluations grava e depois falha na validação.
5. `diarist_service.py:387–389` register_checkout chama `calcular_horas_trabalhadas()` inexistente → 500 após commit. `valor_hora` NULL nas 3 diaristas.
6. `diarist_service.py:209–233` _generate_schedules_from_assignment: Weekday("MONDAY") inválido; kwarg `data=` inexistente (coluna data_trabalho); sem condominio_id.
7. `services/fiscal_service.py:139–152` calcular_irrf lê chaves `ate/acima_de`; tabela usa `valor_inicial/valor_final` → IRRF sempre 0 (simular/10000 → R$ 0,00).
8. `fiscal_service.py:94` + `tabela_inss.aliquota_autonomo=20.00`: retenção de contribuinte individual por tomadora PJ é 11% (Lei 10.666/03 art. 4º). diarist_service 505/734 usa 11% fixo sem teto.
9. `fiscal_service.py:190` `aliquota or ALIQUOTA_ISS_PADRAO`: aliquota 0 vira 5%.
10. `diarist_service.py:721,734` payroll-report: total_horas += 8 fixo; INSS sem teto; líquido ignora IRRF/ISS.
11. `controllers/diarist_controller.py:130–142` consulta-cpf: BrasilAPI /cpf/v1 só valida formato → found=true nome="" para qualquer CPF. Única rota diarist com chamador vivo (`diarist-form-modal.tsx:97`).
12. `diarias_service.py:442–448` criar_diarista: ON CONFLICT (lower(nome)) DO NOTHING → ok=True id=None e descarta CPF/PIX informados. Correção: 409 com id existente.
13. `diarias_service.py:212–227` lancar: não valida ativo, posto/função contra cadastro, nem duplicidade (já há 1 duplicata exata no banco).
14. `diarist_service.py:474–477` valor_total_recebido não está no model → setattr nunca persiste.
15. `diarist_service.py:366,379` utcnow em checkin_real/checkout_real (naive, +4h).
16. `diarist_controller.py:200–203` total = len(página).

## Vereditos
- VIVA: GET /diaristas/consulta-cpf/{cpf} (modal), /diarias/cadastros, POST /diarias/lancar, /diarias/lancamentos, POST/PATCH/DELETE /diarias/diaristas, POST /unificado/alocar-diarista (form redesign, mas grava em diarist_assignments — sem uso funcional).
- INTERNA: GET /diaristas (sonda do agente), /diarias/resumo-diarista (MCP).
- LIGAR: GET /diarias/resumo-gerencial (por posto/função; aba BI do operacional).
- MORTA: todas as demais 45 rotas /diaristas/* (assignments, schedules, payments, evaluations, ai/*, statistics/*, {id} CRUD, activate/deactivate, metrics), 10 rotas /diaristas/fiscal/*, DELETE /diarias/lancamentos/{id} (action usa serviço direto), /unificado/desalocar-diarista, /unificado/sugerir-diarista.
- `notificacao_router` não é montado; client gerado referencia /diaristas/notificacoes/*.
