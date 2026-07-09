"""
Módulo OPERAÇÕES — Agregador
Unifica: operacional (+ submodulos) + campo

Routers re-exportados dos módulos de implementação.
API URLs inalteradas.
Data migração: 2026-03-11
"""

# --- Operacional Core ---
# --- Campo (Ordens de Serviço, Visitas, Checklists) ---
from modules.campo import (
    checklist_router,
    ordem_servico_router,
    visita_router,
)

# --- Operacional AI ---
from modules.operacional.ai.controller import ai_router as operacional_ai_router

# --- Operacional Communication ---
from modules.operacional.communication import communication_router
from modules.operacional.communication.controllers.announcement_controller import (
    router as announcement_router,
)
from modules.operacional.communication.controllers.notification_controller import (
    router as notification_router,
)
from modules.operacional.controllers import (
    allocation_router,
    employee_router,
    kpi_trends_router,
    post_router,
    reports_router,
    scale_router,
    scale_template_router,
    shift_router,
    substitution_router,
    time_bank_router,
)
from modules.operacional.controllers.aliases import (
    banco_horas_alias,
    ferias_alias,
    ocorrencias_alias,
    scale_templates_alias,
)
from modules.operacional.controllers.reports_controller import (
    operacional_dashboard_router,
)

# --- Operacional Diaristas ---
from modules.operacional.diaristas.controllers import fiscal_router as diarist_fiscal_router
from modules.operacional.diaristas.controllers import router as diarist_router

# --- Operacional Disciplinary ---
from modules.operacional.disciplinary import router as disciplinary_router

# --- Operacional Inspection Rounds ---
from modules.operacional.inspection_rounds import inspection_round_router

# --- Operacional Occurrences ---
from modules.operacional.occurrences import occurrence_router

# --- Operacional Passagem de Turno ---
from modules.operacional.shift_handover import shift_handover_router

# --- Operacional Avaliação de Equipe ---
from modules.operacional.team_evaluations import team_evaluation_router

# --- Operacional Triagem (painel do gestor) ---
from modules.operacional.triage import triage_router

# --- Operacional Presença (quadro ao vivo escala × ponto) ---
from modules.operacional.presence import presence_router

# --- Operacional Instruções de Posto (gestor edita, líder lê) ---
from modules.operacional.post_orders import post_orders_router

# --- Operacional Vacations ---
from modules.operacional.vacations import vacation_router

# --- Operacional WebSocket ---
from modules.operacional.websockets import websocket_router as operacional_ws_router

__all__ = [
    "post_router",
    "scale_router",
    "scale_template_router",
    "shift_router",
    "allocation_router",
    "employee_router",
    "substitution_router",
    "time_bank_router",
    "reports_router",
    "kpi_trends_router",
    "occurrence_router",
    "shift_handover_router",
    "team_evaluation_router",
    "triage_router",
    "presence_router",
    "post_orders_router",
    "diarist_router",
    "diarist_fiscal_router",
    "disciplinary_router",
    "inspection_round_router",
    "communication_router",
    "vacation_router",
    "operacional_ai_router",
    "operacional_ws_router",
    "ordem_servico_router",
    "visita_router",
    "checklist_router",
    "announcement_router",
    "notification_router",
    "operacional_dashboard_router",
    "banco_horas_alias",
    "ocorrencias_alias",
    "ferias_alias",
    "scale_templates_alias",
]
