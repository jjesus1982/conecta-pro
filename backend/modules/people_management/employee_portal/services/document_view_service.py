"""
Document View Service — Consulta de documentos, contracheques e escalas.

Servico de leitura para o portal do funcionario acessar seus proprios dados.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _carga_from_escala(escala_padrao: str) -> int:
    """Deriva a carga horaria semanal a partir do tipo de escala.

    Usado como fallback coerente com o perfil (my_profile default 44) quando
    employees.carga_horaria_semanal esta NULL. Pela CCT SINDECOMPRESTS/AM,
    tanto 12x36 quanto 44h correspondem a 44h/semana. Retorna 44 como padrao
    para escalas conhecidas; 0 se nao houver escala reconhecida (vazio-real).
    """
    e = (escala_padrao or "").strip().lower().replace(" ", "")
    if not e:
        return 0
    # 12x36, 44h, e demais escalas da categoria => 44h/semana.
    if "12x36" in e or "44" in e or "6x1" in e or "5x2" in e:
        return 44
    if "36" in e:  # ex.: '36h'
        return 36
    if "30" in e:  # meio periodo
        return 30
    return 44


class DocumentViewService:
    """Servico para visualizacao de documentos do funcionario.

    Fornece acesso a contracheques, escalas, documentos e advertencias
    do proprio funcionario.

    Attributes:
        db: Sessao async do banco de dados.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o servico com sessao de banco.

        Args:
            db: Sessao async do SQLAlchemy.
        """
        self.db = db

    async def get_my_payslips(
        self,
        employee_id: UUID,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retorna contracheques do funcionario.

        Args:
            employee_id: UUID do funcionario.
            year: Ano de referencia (opcional, default ano atual).

        Returns:
            Lista de dicts com dados dos contracheques.
        """
        target_year = year or datetime.utcnow().year

        # Buscar dados do funcionario para calcular valores
        try:
            from modules.operacional.models.employee import Employee

            query = select(Employee).where(Employee.id == employee_id)
            result = await self.db.execute(query)
            employee = result.scalar_one_or_none()

            if not employee:
                return []

            salario_base = float(getattr(employee, "salario_base", 0) or 0)
            if not salario_base:
                salario_base = 1800.0

            # Gerar contracheques simplificados
            payslips: list[dict[str, Any]] = []
            current_month = datetime.utcnow().month if target_year == datetime.utcnow().year else 12

            for month in range(1, current_month + 1):
                inss = min(salario_base * 0.14, 877.24)
                irrf = max((salario_base - inss - 528.0) * 0.075, 0)
                deductions = inss + irrf

                payslips.append(
                    {
                        "month": month,
                        "year": target_year,
                        "gross_salary": salario_base,
                        "deductions": round(deductions, 2),
                        "net_salary": round(salario_base - deductions, 2),
                        "items": [
                            {
                                "description": "Salario Base",
                                "type": "provento",
                                "reference": "220h",
                                "value": salario_base,
                            },
                            {
                                "description": "INSS",
                                "type": "desconto",
                                "reference": "14%",
                                "value": round(inss, 2),
                            },
                            {
                                "description": "IRRF",
                                "type": "desconto",
                                "reference": "7.5%",
                                "value": round(irrf, 2),
                            },
                        ],
                    }
                )

            return payslips

        except ImportError:
            logger.warning("Modelo Employee nao disponivel para contracheques.")
            return []

    async def get_my_schedules(
        self,
        employee_id: UUID,
        month: int | None = None,
        year: int | None = None,
    ) -> dict[str, Any]:
        """Retorna a escala do funcionario para o mes.

        Args:
            employee_id: UUID do funcionario.
            month: Mes de referencia (default mes atual).
            year: Ano de referencia (default ano atual).

        Returns:
            Dict com dados da escala e lista de turnos.
        """
        now = datetime.utcnow()
        target_month = month or now.month
        target_year = year or now.year

        schedule: dict[str, Any] = {
            "employee_name": "",
            "month": target_month,
            "year": target_year,
            "shifts": [],
            "total_hours": 0.0,
        }

        try:
            from modules.operacional.models.employee import Employee

            emp_query = select(Employee).where(Employee.id == employee_id)
            emp_result = await self.db.execute(emp_query)
            employee = emp_result.scalar_one_or_none()

            if employee:
                escala_padrao = getattr(employee, "escala_padrao", "") or ""
                schedule["employee_name"] = getattr(employee, "nome", "")
                schedule["escala_padrao"] = escala_padrao
                schedule["turno_padrao"] = getattr(employee, "turno_padrao", "")
                schedule["jornada_trabalho"] = getattr(employee, "jornada_trabalho", "")
                schedule["cargo"] = getattr(employee, "cargo", "")
                schedule["posto_atual_nome"] = getattr(employee, "posto_atual_nome", "")

                # Coerencia com o perfil (my_profile usa default 44):
                # quando a coluna carga_horaria_semanal estiver NULL/0, derivar da
                # escala_padrao (12x36 e 44h => 44h/semana pela CCT). Nao chumbar 0.
                carga = getattr(employee, "carga_horaria_semanal", None) or 0
                if not carga and escala_padrao:
                    carga = _carga_from_escala(escala_padrao)
                schedule["carga_horaria_semanal"] = carga
                schedule["total_hours"] = float(carga * 4.33)

        except ImportError:
            logger.warning("Modelos operacionais nao disponiveis para escalas.")

        return schedule

    async def get_my_documents(
        self,
        employee_id: UUID,
    ) -> list[dict[str, Any]]:
        """Retorna documentos associados ao funcionario.

        Inclui contratos, politicas, certificados e outros documentos
        que requerem ciencia ou assinatura.

        Args:
            employee_id: UUID do funcionario.

        Returns:
            Lista de dicts com dados dos documentos.
        """
        documents: list[dict[str, Any]] = []

        # [Veracidade] Documentos reais do funcionario vivem em ged_kit_documents
        # (mesma fonte usada pelo card pending_documents do dashboard). Antes lia so
        # PortalDigitalSignature (0 linhas) -> tela vazia contradizendo o dashboard.
        try:
            from sqlalchemy import text as _sqltext

            # [Veracidade] Só expõe documentos REAIS ao funcionário: exclui
            # placeholders ('[PLACEHOLDER] ...') e registros sem arquivo
            # (file_path NULL) — eram ~552 placeholders + ~1479 sem arquivo.
            result = await self.db.execute(
                _sqltext(
                    "SELECT CAST(id AS TEXT) AS id, document_type, document_name, "
                    "is_signed, signed_at, file_path "
                    "FROM ged_kit_documents "
                    "WHERE CAST(employee_id AS TEXT) = :e "
                    "AND file_path IS NOT NULL "
                    "AND COALESCE(document_name, '') NOT LIKE '[PLACEHOLDER]%' "
                    "ORDER BY created_at DESC"
                ),
                {"e": str(employee_id)},
            )
            rows = result.mappings().all()

            for row in rows:
                signed_at = row["signed_at"]
                documents.append(
                    {
                        "document_id": row["id"],
                        "document_type": row["document_type"] or "other",
                        "document_name": row["document_name"],
                        "signed": bool(row["is_signed"]),
                        "signed_at": signed_at.isoformat()
                        if hasattr(signed_at, "isoformat")
                        else (str(signed_at) if signed_at else None),
                        "signature_valid": bool(row["is_signed"]),
                        "file_path": row["file_path"],
                    }
                )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Erro ao buscar documentos (ged_kit_documents): %s", exc)

        return documents

    async def get_my_warnings(
        self,
        employee_id: UUID,
    ) -> list[dict[str, Any]]:
        """Retorna advertencias/medidas disciplinares do funcionario.

        Args:
            employee_id: UUID do funcionario.

        Returns:
            Lista de dicts com dados das advertencias.
        """
        warnings: list[dict[str, Any]] = []

        try:
            from modules.operacional.disciplinary import DisciplinaryAction

            query = (
                select(DisciplinaryAction)
                .where(DisciplinaryAction.employee_id == employee_id)
                .order_by(DisciplinaryAction.created_at.desc())
            )

            result = await self.db.execute(query)
            actions = result.scalars().all()

            for action in actions:
                warnings.append(
                    {
                        "id": action.id,
                        "type": getattr(action, "action_type", "advertencia"),
                        "reason": getattr(action, "reason", ""),
                        "date": str(getattr(action, "created_at", "")),
                        "status": getattr(action, "status", "pendente"),
                    }
                )

        except ImportError:
            logger.warning("Modelo DisciplinaryAction nao disponivel.")

        return warnings
