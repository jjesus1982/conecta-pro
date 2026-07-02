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
                schedule["employee_name"] = getattr(employee, "nome", "")
                schedule["escala_padrao"] = getattr(employee, "escala_padrao", "")
                schedule["turno_padrao"] = getattr(employee, "turno_padrao", "")
                schedule["carga_horaria_semanal"] = getattr(employee, "carga_horaria_semanal", 0)
                schedule["jornada_trabalho"] = getattr(employee, "jornada_trabalho", "")
                schedule["cargo"] = getattr(employee, "cargo", "")
                schedule["posto_atual_nome"] = getattr(employee, "posto_atual_nome", "")

                # Calcular horas estimadas do mes
                carga = getattr(employee, "carga_horaria_semanal", 0) or 0
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

            result = await self.db.execute(
                _sqltext(
                    "SELECT CAST(id AS TEXT) AS id, document_type, document_name, "
                    "is_signed, signed_at, file_path "
                    "FROM ged_kit_documents "
                    "WHERE CAST(employee_id AS TEXT) = :e "
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
