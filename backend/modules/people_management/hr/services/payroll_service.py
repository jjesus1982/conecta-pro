"""
Serviço de Folha de Pagamento — Departamento Pessoal.

Calcula folha com INSS progressivo, IRRF, adicionais legais
e integração com benefícios. Usa clt_calculator para precisão Decimal.
"""

import contextlib
import logging
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.employee import Employee
from modules.people_management.common.utils import clt_calculator as clt_calc
from modules.people_management.common.utils.clt_calculator import (
    calcular_adicional_noturno,
    calcular_dsr_sobre_extras,
    calcular_fgts_mensal,
    calcular_hora_extra_50,
    calcular_hora_extra_100,
    calcular_hora_normal,
    calcular_inss,
    calcular_irrf,
    calcular_periculosidade,
    calcular_vale_transporte_desconto,
)

logger = logging.getLogger(__name__)

# Re-export do serviço existente
try:
    from modules.hr.payroll_integration.services import PayrollService as HRPayrollService
except ImportError:
    HRPayrollService = None  # type: ignore[assignment, misc]


_TWO = Decimal("0.01")  # Precisão de 2 casas decimais


def _d(v) -> Decimal:
    """Converte para Decimal de forma segura."""
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


class PayrollService:
    """Serviço de Folha de Pagamento — visão DP com cálculos CLT reais."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._hr_service = None
        if HRPayrollService:
            with contextlib.suppress(Exception):
                self._hr_service = HRPayrollService(db)

    async def calculate_employee_payroll(
        self,
        employee_id: str | UUID,
        reference_month: int,
        reference_year: int,
    ) -> dict:
        """Calcula a folha de pagamento de um funcionário com CLT real.

        Args:
            employee_id: ID do funcionário.
            reference_month: Mês de referência (1-12).
            reference_year: Ano de referência.

        Returns:
            Dicionário com detalhamento completo da folha.
        """
        result = await self.db.execute(select(Employee).where(Employee.id == str(employee_id)))
        employee = result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        salario_base = _d(employee.salario_base)
        valor_hora = calcular_hora_normal(salario_base)

        # --- PROVENTOS ---
        proventos = []

        # 1. Salário base
        proventos.append({"codigo": "001", "descricao": "Salário Base", "ref": "30d", "valor": salario_base})

        # 2. Adicional de Periculosidade (30%)
        ad_periculosidade = Decimal("0")
        if getattr(employee, "adicional_periculosidade", None):
            ad_periculosidade = calcular_periculosidade(salario_base)
            proventos.append(
                {"codigo": "010", "descricao": "Periculosidade 30%", "ref": "30%", "valor": ad_periculosidade}
            )

        # 3. Adicional Noturno (20%) — busca horas noturnas do mês
        ad_noturno = Decimal("0")
        horas_noturnas = await self._get_horas_noturnas(employee_id, reference_month, reference_year)
        if horas_noturnas > 0:
            ad_noturno = calcular_adicional_noturno(valor_hora, horas_noturnas)
            proventos.append(
                {"codigo": "020", "descricao": "Ad. Noturno 20%", "ref": f"{horas_noturnas}h", "valor": ad_noturno}
            )

        # 4. Horas extras — busca de overtime_records
        he_50 = Decimal("0")
        he_100 = Decimal("0")
        horas_extras_50, horas_extras_100 = await self._get_horas_extras(employee_id, reference_month, reference_year)
        if horas_extras_50 > 0:
            he_50 = calcular_hora_extra_50(valor_hora, horas_extras_50)
            proventos.append(
                {"codigo": "030", "descricao": "Hora Extra 50%", "ref": f"{horas_extras_50}h", "valor": he_50}
            )
        if horas_extras_100 > 0:
            he_100 = calcular_hora_extra_100(valor_hora, horas_extras_100)
            proventos.append(
                {"codigo": "031", "descricao": "Hora Extra 100%", "ref": f"{horas_extras_100}h", "valor": he_100}
            )

        # 5. DSR sobre extras — dias úteis/domingos REAIS da competência (não 22/8 fixo,
        # que superestimava o DSR ~2,3x sobre as HE)
        total_extras = he_50 + he_100
        dsr = Decimal("0")
        if total_extras > 0:
            import calendar as _cal

            _du = _dom = 0
            _, _nd = _cal.monthrange(reference_year, reference_month)
            for _dia in range(1, _nd + 1):
                if _cal.weekday(reference_year, reference_month, _dia) == 6:
                    _dom += 1
                else:
                    _du += 1
            dsr = calcular_dsr_sobre_extras(total_extras, dias_uteis=_du, domingos_feriados=_dom)
            proventos.append({"codigo": "040", "descricao": "DSR s/ Extras", "ref": "", "valor": dsr})

        total_proventos = sum(p["valor"] for p in proventos)

        # --- DESCONTOS ---
        descontos = []

        # 1. INSS Progressivo
        inss = calcular_inss(total_proventos)
        descontos.append({"codigo": "201", "descricao": "INSS Progressivo", "ref": "", "valor": inss})

        # 2. IRRF
        base_irrf = total_proventos - inss
        # Buscar dependentes do employee (campo JSONB com lista de dependentes)
        dep_result = await self.db.execute(
            text("SELECT dependentes FROM employees WHERE id = :eid"),
            {"eid": employee_id},
        )
        dep_data = dep_result.scalar()
        dependentes = len(dep_data) if isinstance(dep_data, list) else 0
        # rendimento_bruto → aplica o redutor da reforma (Lei 15.270) + opção do desconto
        # simplificado; alinha com o motor da folha CCT (calculo_service). Motor unificado.
        irrf = calcular_irrf(base_irrf, dependentes=dependentes, rendimento_bruto=total_proventos)
        if irrf > 0:
            descontos.append({"codigo": "202", "descricao": "IRRF", "ref": "", "valor": irrf})

        # 3. Vale Transporte (4% CLT — CCT Conecta Mais)
        vt_desconto = calcular_vale_transporte_desconto(salario_base)
        if vt_desconto > 0:
            descontos.append({"codigo": "210", "descricao": "VT 4%", "ref": "4%", "valor": vt_desconto})

        # 4. Benefícios (plano saúde, odonto, seguro de vida, etc.)
        from modules.people_management.hr.models.benefits import EmployeeBenefit

        ben_result = await self.db.execute(
            select(EmployeeBenefit).where(
                EmployeeBenefit.employee_id == str(employee_id),
                EmployeeBenefit.status == "active",
            )
        )
        benefits = ben_result.scalars().all()
        for b in benefits:
            contrib = _d(b.employee_contribution)
            if contrib > 0:
                descontos.append(
                    {
                        "codigo": "220",
                        "descricao": f"Benefício: {b.type}",
                        "ref": b.plan_name or "",
                        "valor": contrib,
                    }
                )

        # 5. Faltas e atrasos — busca do ponto eletrônico
        faltas, minutos_atraso = await self._get_faltas_atrasos(employee_id, reference_month, reference_year)
        if faltas > 0:
            desconto_falta = (salario_base / Decimal("30")) * Decimal(str(faltas))
            desconto_falta = desconto_falta.quantize(_TWO, ROUND_HALF_UP)
            descontos.append({"codigo": "230", "descricao": "Faltas", "ref": f"{faltas}d", "valor": desconto_falta})
        if minutos_atraso > 0:
            horas_atraso = Decimal(str(minutos_atraso)) / Decimal("60")
            desconto_atraso = (valor_hora * horas_atraso).quantize(_TWO, ROUND_HALF_UP)
            descontos.append(
                {"codigo": "231", "descricao": "Atrasos", "ref": f"{minutos_atraso}min", "valor": desconto_atraso}
            )

        total_descontos = sum(d["valor"] for d in descontos)
        salario_liquido = total_proventos - total_descontos

        # FGTS (informativo, não desconta do funcionário)
        fgts = calcular_fgts_mensal(total_proventos)

        # Serializar Decimals para float no retorno
        def _f(v: Decimal) -> float:
            return float(v)

        return {
            "employee_id": str(employee_id),
            "employee_name": employee.nome,
            "cargo": getattr(employee, "cargo", ""),
            "matricula": getattr(employee, "matricula", ""),
            "cpf": getattr(employee, "cpf", ""),
            "data_admissao": str(getattr(employee, "data_admissao", ""))
            if getattr(employee, "data_admissao", None)
            else "",
            "reference": f"{reference_month:02d}/{reference_year}",
            "salario_base": _f(salario_base),
            "valor_hora": _f(valor_hora),
            "proventos": [{**p, "valor": _f(p["valor"])} for p in proventos],
            "descontos": [{**d, "valor": _f(d["valor"])} for d in descontos],
            "total_proventos": _f(total_proventos),
            "total_descontos": _f(total_descontos),
            "salario_liquido": _f(salario_liquido),
            "fgts_8_pct": _f(fgts),
            "base_inss": _f(total_proventos),
            "base_irrf": _f(base_irrf),
            # [Veracidade] O holerite diz a verdade sobre a base legal usada. Enquanto as
            # tabelas INSS/IRRF 2026 não forem certificadas pelo DP/Contábil, este cálculo
            # é ESTIMATIVA (tabelas 2024), não valor legal. O frontend/PDF deve exibir o aviso.
            "certificacao_tabela_legal": {
                "certificada": clt_calc.TABELAS_LEGAIS_CERTIFICADAS_2026,
                "vigencia_valores": clt_calc.VIGENCIA_TABELAS_LEGAIS,
                "status": "certificada"
                if clt_calc.TABELAS_LEGAIS_CERTIFICADAS_2026
                else "estimativa_aguardando_tabelas_2026",
                "aviso": None
                if clt_calc.TABELAS_LEGAIS_CERTIFICADAS_2026
                else (
                    f"ESTIMATIVA — cálculo usa tabelas INSS/IRRF de "
                    f"{clt_calc.VIGENCIA_TABELAS_LEGAIS}, ainda não atualizadas/certificadas para 2026. "
                    "Não usar como valor legal até certificação do DP/Contábil."
                ),
            },
        }

    async def close_payroll(
        self,
        reference_month: int,
        reference_year: int,
    ) -> dict:
        """Fecha a folha de pagamento do mês para todos os funcionários ativos.

        Args:
            reference_month: Mês de referência (1-12).
            reference_year: Ano de referência.

        Returns:
            Dicionário com resumo do fechamento.
        """
        from sqlalchemy import func

        count_result = await self.db.execute(
            select(func.count()).select_from(Employee).where(func.lower(Employee.status) == "ativo")
        )
        total_employees = count_result.scalar() or 0

        result = await self.db.execute(select(Employee).where(func.lower(Employee.status) == "ativo"))
        employees = result.scalars().all()

        total_bruto = Decimal("0")
        total_liquido = Decimal("0")
        total_fgts = Decimal("0")
        processed = 0
        errors = []

        for emp in employees:
            try:
                calc = await self.calculate_employee_payroll(str(emp.id), reference_month, reference_year)
                total_bruto += _d(calc["total_proventos"])
                total_liquido += _d(calc["salario_liquido"])
                total_fgts += _d(calc["fgts_8_pct"])
                processed += 1
            except Exception as e:
                logger.warning("Erro ao calcular folha do funcionário %s: %s", emp.id, e)
                errors.append({"employee_id": str(emp.id), "error": str(e)})

        logger.info(
            "Folha %02d/%d fechada: %d/%d funcionários processados",
            reference_month,
            reference_year,
            processed,
            total_employees,
        )

        result = {
            "reference": f"{reference_month:02d}/{reference_year}",
            "total_employees": total_employees,
            "processed": processed,
            "errors": len(errors),
            "error_details": errors[:10],
            "total_bruto": float(total_bruto),
            "total_liquido": float(total_liquido),
            "total_fgts": float(total_fgts),
            "status": "closed",
        }

        try:
            from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

            await event_bus.publish(
                ConectaEvent(
                    event_type=EventTypes.DP_FOLHA_FECHADA,
                    payload={
                        "competencia": f"{reference_year}-{reference_month:02d}",
                        "total_funcionarios": total_employees,
                        "processados": processed,
                        "total_bruto": float(total_bruto),
                        "total_liquido": float(total_liquido),
                        "total_fgts": float(total_fgts),
                    },
                    source_module="dp",
                    competencia=f"{reference_year}-{reference_month:02d}",
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Falha ao publicar evento folha fechada: %s", exc)

        return result

    async def mark_payslip_viewed(self, employee_id: str | UUID, month: int, year: int) -> dict:
        """Marca contracheque como visualizado pelo funcionário.

        Args:
            employee_id: ID do funcionário.
            month: Mês.
            year: Ano.

        Returns:
            Confirmação.
        """
        logger.info("Contracheque %02d/%d visualizado por %s", month, year, employee_id)
        return {"status": "viewed", "employee_id": str(employee_id), "reference": f"{month:02d}/{year}"}

    # =========================================================================
    # METODOS DE INTEGRACAO — busca dados reais das tabelas
    # =========================================================================

    async def _get_horas_extras(self, employee_id: str | UUID, month: int, year: int) -> tuple[Decimal, Decimal]:
        """Busca horas extras do mês em overtime_records.

        Returns:
            Tuple (horas_50, horas_100) em Decimal.
        """
        try:
            result = await self.db.execute(
                text(
                    "SELECT overtime_type, SUM(total_minutes) "
                    "FROM overtime_records "
                    "WHERE employee_id = :eid "
                    "AND EXTRACT(MONTH FROM overtime_date) = :m "
                    "AND EXTRACT(YEAR FROM overtime_date) = :y "
                    "AND status = 'approved' "
                    "GROUP BY overtime_type"
                ),
                {"eid": str(employee_id), "m": month, "y": year},
            )
            rows = result.fetchall()

            horas_50 = Decimal("0")
            horas_100 = Decimal("0")
            for row in rows:
                tipo, minutos = row[0], row[1] or 0
                horas = Decimal(str(minutos)) / Decimal("60")
                if tipo in ("50", "normal", "weekday"):
                    horas_50 += horas
                elif tipo in ("100", "sunday", "holiday"):
                    horas_100 += horas

            return horas_50.quantize(_TWO), horas_100.quantize(_TWO)
        except Exception as e:
            logger.debug("Horas extras nao encontradas para %s: %s", employee_id, e)
            return Decimal("0"), Decimal("0")

    async def _get_horas_noturnas(self, employee_id: str | UUID, month: int, year: int) -> Decimal:
        """Busca horas noturnas do mês em overtime_records ou shifts.

        Returns:
            Total de horas noturnas (22h-05h) no mês.
        """
        try:
            result = await self.db.execute(
                text(
                    "SELECT SUM(total_minutes) "
                    "FROM overtime_records "
                    "WHERE employee_id = :eid "
                    "AND EXTRACT(MONTH FROM overtime_date) = :m "
                    "AND EXTRACT(YEAR FROM overtime_date) = :y "
                    "AND overtime_type = 'night'"
                ),
                {"eid": str(employee_id), "m": month, "y": year},
            )
            minutos = result.scalar() or 0
            return (Decimal(str(minutos)) / Decimal("60")).quantize(_TWO)
        except Exception:
            return Decimal("0")

    async def _get_faltas_atrasos(self, employee_id: str | UUID, month: int, year: int) -> tuple[int, int]:
        """Busca faltas e atrasos do ponto eletrônico.

        Fonte primária: gp_justifications (local + sincronizado do Sólides).
        Fonte secundária: solides_absences (staging — pode não existir).

        Returns:
            Tuple (dias_falta, minutos_atraso).
        """
        faltas_total = 0
        atrasos_total = 0

        # Fonte 1: gp_justifications (sempre disponível, inclui dados do Sólides)
        try:
            result = await self.db.execute(
                text(
                    "SELECT "
                    "  COALESCE(SUM(CASE WHEN justification_type = 'falta' THEN 1 ELSE 0 END), 0), "
                    "  COALESCE(SUM(CASE WHEN justification_type = 'atraso' THEN 60 ELSE 0 END), 0) "
                    "FROM gp_justifications "
                    "WHERE employee_id::text = :eid "
                    "  AND status IN ('aprovada', 'pendente') "
                    "  AND EXTRACT(MONTH FROM created_at) = :m "
                    "  AND EXTRACT(YEAR FROM created_at) = :y"
                ),
                {"eid": str(employee_id), "m": month, "y": year},
            )
            row = result.fetchone()
            if row:
                faltas_total += int(row[0] or 0)
                atrasos_total += int(row[1] or 0)
        except Exception as e:
            logger.debug("gp_justifications nao acessivel para %s: %s", employee_id, e)

        # Fonte 2: solides_absences staging (pode não existir)
        try:
            result = await self.db.execute(
                text(
                    # colunas REAIS de solides_absences (staging Sólides): colaborador_id,
                    # minutos_atraso, data_inicio, justificado. A query antiga usava nomes
                    # inexistentes (employee_id/minutos/data/justificada) → erro que envenenava
                    # a transação do cálculo de folha (batch caía em cascata). Tabela vazia:
                    # segue contribuindo 0, só deixa de quebrar.
                    "SELECT "
                    "  COALESCE(SUM(CASE WHEN tipo = 'falta' THEN 1 ELSE 0 END), 0), "
                    "  COALESCE(SUM(CASE WHEN tipo = 'atraso' THEN minutos_atraso ELSE 0 END), 0) "
                    "FROM solides_absences "
                    "WHERE colaborador_id = :eid "
                    "  AND EXTRACT(MONTH FROM data_inicio) = :m "
                    "  AND EXTRACT(YEAR FROM data_inicio) = :y "
                    "  AND justificado = false"
                ),
                {"eid": str(employee_id), "m": month, "y": year},
            )
            row = result.fetchone()
            if row:
                faltas_total += int(row[0] or 0)
                atrasos_total += int(row[1] or 0)
        except Exception as e:
            logger.debug("solides_absences nao acessivel para %s: %s", employee_id, e)

        return faltas_total, atrasos_total
