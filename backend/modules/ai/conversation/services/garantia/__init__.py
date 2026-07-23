"""Fase 5.2a.3 — Camada de Garantia do Conecta PRO.

O que separa "brinquedo" de "grande player": 4 módulos standalone, todos
testáveis sem o Hermes no ar.

- `groundedness`  — âncora anti-alucinação: número afirmado precisa ter lastro
  numa fonte (panorama/tool-result), senão é suspeito.
- `agent_audit`   — auditoria append-only de ações de agente, reusando a tabela
  `audit_logs` (Sprint 33) — nenhuma tabela nova.
- `observability` — spans Sentry (`gen_ai.*`) das chamadas de LLM, no-op seguro
  se o Sentry não estiver inicializado.
- `routing`       — roteamento de custo: tier por tamanho (herda de
  `core.llm_cascade`) + regra de domínio (dinheiro/legal/C-level força a pesada).

A auditoria + groundedness são PLUGADOS nos endpoints executivos na Fase 5.2a.4;
aqui os módulos ficam prontos e só o roteamento+span já estão ligados na ponte
Hermes (`consultor_hub.gerar`).
"""
from __future__ import annotations

from . import agent_audit, groundedness, observability, routing

__all__ = ["agent_audit", "groundedness", "observability", "routing"]
