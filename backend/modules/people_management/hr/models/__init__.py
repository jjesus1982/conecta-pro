"""
Models do módulo Departamento Pessoal (DP/HR).

Re-exporta modelos existentes e define novos modelos para:
- Processos de admissão
- Processos de rescisão
- Benefícios
- Contratos de trabalho
"""

# Re-export existing models
try:
    from modules.operacional.models.employee import Employee
except ImportError:
    Employee = None  # type: ignore[assignment, misc]

try:
    from modules.operacional.models.time_bank import TimeBank, TimeBankEntryType, TimeBankStatus
except ImportError:
    TimeBank = None  # type: ignore[assignment, misc]
    TimeBankEntryType = None  # type: ignore[assignment, misc]
    TimeBankStatus = None  # type: ignore[assignment, misc]

# New DP models
from .admission import AdmissionProcess, AdmissionStatus
from .benefits import BenefitStatus, BenefitType, EmployeeBenefit
from .contract import ContractType, EmploymentContract
from .employee import Employee as EmployeeRef
from .employee_dp import EmployeeDP, GrauInsalubridade, JornadaType
from .termination import TerminationProcess, TerminationStatus, TerminationType
from .vigilante import EquipamentoControlado, EquipamentoControladoAlocacao, VigilanteCurso  # frente 05

__all__ = [
    # Re-exported
    "Employee",
    "EmployeeRef",
    "TimeBank",
    "TimeBankEntryType",
    "TimeBankStatus",
    # New models
    "AdmissionProcess",
    "AdmissionStatus",
    "TerminationProcess",
    "TerminationType",
    "VigilanteCurso",
    "EquipamentoControlado",
    "EquipamentoControladoAlocacao",
    "TerminationStatus",
    "EmployeeBenefit",
    "BenefitType",
    "BenefitStatus",
    "EmploymentContract",
    "ContractType",
    "EmployeeDP",
    "GrauInsalubridade",
    "JornadaType",
]
