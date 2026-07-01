# QUARENTENA Item −1 (2026-07-01)
Código órfão movido aqui (0 importador vivo, orchestrator não sobe no boot — DIAG §5.2, re-provado no cut-time).
NÃO deletado (§13.6, reversível). Para restaurar: git mv de volta + reverter core/events/__init__.py.
- agents/ : framework de agents de people_management (dp/ops/rh/sst/portal/base + orchestrator)
- event_types.py : registro gp.* EventTypes (usado só pelos agents; dp.* de infra/event_bus é o eleito)
MessageBus NÃO foi quarentenado: tem 5 publishers vivos (health_occupational + employee_service).

## Testes movidos junto (testam código quarentenado, não código vivo):
- tests_agents/test_e2e_integration.py : importava modules.people_management.agents
- tests_agents/test_event_bus.py : 44 usos de GPEventTypes (gp.* deprecado)
Cobertura do bus VIVO (ConectaEventBus/alias GPEventBus) fica nos testes de infrastructure/event_bus.
