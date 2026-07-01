"""
Fixtures para testes do módulo Operations.
"""

from datetime import date, time
from uuid import uuid4

import pytest

from modules.operacional.models.allocation import AllocationStatus
from modules.operacional.models.post import PostStatus, PostType, ShiftType
from modules.operacional.models.scale import ScaleStatus, ScaleType
from modules.operacional.models.shift import ShiftStatus
from modules.operacional.models.substitution import SubstitutionReason, SubstitutionStatus
from modules.operacional.models.time_bank import TimeBankEntryType, TimeBankStatus


@pytest.fixture
def sample_post_data():
    """Dados de exemplo para Post."""
    return {
        "id": str(uuid4()),
        "code": "POST-001",
        "name": "Posto Matriz",
        "description": "Posto de vigilância da matriz",
        "post_type": PostType.PORTEIRO.value,
        "status": PostStatus.ACTIVE.value,
        "shift_type": ShiftType.DIURNO.value,
        "address": "Rua das Flores, 123",
        "city": "São Paulo",
        "state": "SP",
        "zip_code": "01234-567",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "contract_id": str(uuid4()),
        "client_id": str(uuid4()),
        "required_headcount": 4,
        "current_headcount": 3,
        "requires_armed": True,
        "requires_vehicle": False,
        "requires_experience_months": 12,
        "required_certifications": ["vigilante", "cftv"],
        "shift_start_time": "07:00:00",
        "shift_end_time": "19:00:00",
        "break_duration_minutes": 60,
        "night_shift_bonus_percent": 20.0,
        "hazard_pay_percent": 30.0,
        "hourly_rate": 25.0,
        "monthly_cost": 15000.0,
        "supervisor_name": "João Silva",
        "supervisor_phone": "11999998888",
        "is_active": True,
    }


@pytest.fixture
def sample_scale_data():
    """Dados de exemplo para Scale."""
    return {
        "id": str(uuid4()),
        "post_id": str(uuid4()),
        "scale_type": ScaleType.SCALE_12X36.value,
        "status": ScaleStatus.DRAFT.value,
        "month": 1,
        "year": 2025,
        "name": "Escala Janeiro 2025",
        "description": "Escala do mês de janeiro",
        "total_shifts": 60,
        "filled_shifts": 55,
        "total_hours": 720.0,
        "overtime_hours": 24.0,
        "estimated_cost": 18000.0,
        "config": {
            "start_time": "07:00",
            "end_time": "19:00",
            "break_minutes": 60,
        },
        "is_active": True,
    }


@pytest.fixture
def sample_shift_data():
    """Dados de exemplo para Shift."""
    return {
        "id": str(uuid4()),
        "scale_id": str(uuid4()),
        "post_id": str(uuid4()),
        "employee_id": str(uuid4()),
        "status": ShiftStatus.SCHEDULED.value,
        "shift_date": date(2025, 1, 15),
        "planned_start_time": time(7, 0),
        "planned_end_time": time(19, 0),
        "planned_break_minutes": 60,
        "planned_hours": 12.0,
        "is_holiday": False,
        "is_night_shift": False,
        "is_overtime": False,
        "is_off_day": False,
        "needs_substitution": False,
        "base_pay": 300.0,
        "overtime_pay": 0.0,
        "night_bonus": 0.0,
        "holiday_bonus": 0.0,
        "total_pay": 300.0,
        "is_active": True,
    }


@pytest.fixture
def sample_allocation_data():
    """Dados de exemplo para Allocation."""
    return {
        "id": str(uuid4()),
        "post_id": str(uuid4()),
        "employee_id": str(uuid4()),
        "status": AllocationStatus.ACTIVE.value,
        "start_date": date(2024, 1, 1),
        "end_date": None,
        "is_primary": True,
        "is_temporary": False,
        "hourly_rate": 25.0,
        "monthly_salary": 4400.0,
        "additional_benefits": 600.0,
        "role": "Vigilante",
        "qualifications": {
            "certifications": ["vigilante", "armado"],
            "experience_months": 24,
        },
        "is_active": True,
    }


@pytest.fixture
def sample_substitution_data():
    """Dados de exemplo para Substitution."""
    return {
        "id": str(uuid4()),
        "shift_id": str(uuid4()),
        "post_id": str(uuid4()),
        "original_employee_id": str(uuid4()),
        "substitute_employee_id": None,
        "reason": SubstitutionReason.SICK_LEAVE.value,
        "status": SubstitutionStatus.PENDING.value,
        "substitution_date": date(2025, 1, 15),
        "reason_details": "Atestado médico",
        "additional_cost": 0.0,
        "overtime_hours": 0.0,
        "is_overtime": False,
        "notification_sent": False,
        "is_active": True,
    }


@pytest.fixture
def sample_time_bank_data():
    """Dados de exemplo para TimeBank."""
    return {
        "id": str(uuid4()),
        "employee_id": str(uuid4()),
        "entry_type": TimeBankEntryType.CREDIT.value,
        "status": TimeBankStatus.PENDING.value,
        "hours": 2.5,
        "balance_before": 10.0,
        "balance_after": 12.5,
        "reference_date": date(2025, 1, 15),
        "expiration_date": date(2025, 7, 15),
        "shift_id": str(uuid4()),
        "post_id": str(uuid4()),
        "description": "Hora extra realizada",
        "reason": "Cobertura de falta",
        "is_active": True,
    }


@pytest.fixture
def sample_employees():
    """Lista de funcionários para testes de escala."""
    return [
        {
            "id": str(uuid4()),
            "name": "Carlos Silva",
            "hourly_rate": 25.0,
            "is_available": True,
        },
        {
            "id": str(uuid4()),
            "name": "Maria Santos",
            "hourly_rate": 25.0,
            "is_available": True,
        },
        {
            "id": str(uuid4()),
            "name": "José Oliveira",
            "hourly_rate": 25.0,
            "is_available": True,
        },
        {
            "id": str(uuid4()),
            "name": "Ana Costa",
            "hourly_rate": 25.0,
            "is_available": True,
        },
    ]
