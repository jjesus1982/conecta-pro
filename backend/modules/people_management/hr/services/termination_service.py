"""
Serviço de Rescisão — Departamento Pessoal.

Gerencia o workflow de desligamento: criação do processo,
cálculos rescisórios com CLT real (Decimal) e conclusão.
"""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.employee import Employee
from modules.people_management.common.utils.clt_calculator import (
    calcular_rescisao,
)
from modules.people_management.hr.models.termination import (
    TerminationProcess,
    TerminationStatus,
    TerminationType,
)

logger = logging.getLogger(__name__)


class TerminationService:
    """Serviço para processos de rescisão."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_termination(
        self,
        data: dict,
        created_by_id: str | UUID | None = None,
    ) -> TerminationProcess:
        """Cria um novo processo de rescisão.

        Args:
            data: Dados do processo (schema TerminationCreate).
            created_by_id: ID do usuário que criou.

        Returns:
            Instância de TerminationProcess criada.
        """
        # notice_type (trabalhado/indenizado) é armazenado em reason quando reason não fornecido
        notice_type = data.get("notice_type")
        reason = data.get("reason") or (f"notice_type:{notice_type}" if notice_type else None)
        # Respeitar status fornecido (ex.: notice_period para aviso prévio)
        status_value = data.get("status") or TerminationStatus.INITIATED
        termination = TerminationProcess(
            id=uuid4(),
            employee_id=data["employee_id"],
            type=data["type"],
            reason=reason,
            notice_period_days=data.get("notice_period_days"),
            notice_start_date=data.get("notice_start_date"),
            last_working_day=data.get("last_working_day"),
            status=status_value,
            created_by_id=str(created_by_id) if created_by_id else None,
        )
        self.db.add(termination)
        await self.db.flush()
        await self.db.refresh(termination)
        logger.info("Processo de rescisão criado: %s", termination.id)
        return termination

    async def get_by_id(self, termination_id: str | UUID) -> TerminationProcess | None:
        """Busca processo de rescisão por ID."""
        result = await self.db.execute(select(TerminationProcess).where(TerminationProcess.id == str(termination_id)))
        return result.scalar_one_or_none()

    async def list_terminations(
        self,
        status: TerminationStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Lista processos de rescisão com filtro e paginação."""
        from sqlalchemy import func

        query = select(TerminationProcess)
        count_query = select(func.count()).select_from(TerminationProcess)

        if status:
            query = query.where(TerminationProcess.status == status)
            count_query = count_query.where(TerminationProcess.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        query = query.order_by(TerminationProcess.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": list(items),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def calculate_severance(
        self,
        employee_id: str | UUID,
        termination_type: TerminationType,
        last_working_day: date,
    ) -> dict:
        """Calcula verbas rescisórias conforme CLT com Decimal preciso.

        Args:
            employee_id: ID do funcionário.
            termination_type: Tipo de rescisão.
            last_working_day: Último dia de trabalho.

        Returns:
            Dicionário com breakdown dos cálculos rescisórios.
        """
        result = await self.db.execute(select(Employee).where(Employee.id == str(employee_id)))
        employee = result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        salario_base = Decimal(str(employee.salario_base or 0))

        # Base das verbas rescisórias = salário-base + adicionais que integram a
        # remuneração (CLT art. 457/459 e Súmulas TST): insalubridade,
        # periculosidade e adicional de ronda. Mesma convenção do motor de folha
        # (calculo_service): percentual aplicado sobre o salário-base/piso.
        insal_pct = Decimal(str(getattr(employee, "insalubridade_percentual", 0) or 0)) / Decimal("100")
        peric_pct = Decimal(str(getattr(employee, "periculosidade_percentual", 0) or 0)) / Decimal("100")
        ronda_pct = Decimal(str(getattr(employee, "adicional_ronda_percentual", 0) or 0)) / Decimal("100")
        adic_insalubridade = (salario_base * insal_pct).quantize(Decimal("0.01"))
        adic_periculosidade = (salario_base * peric_pct).quantize(Decimal("0.01"))
        adic_ronda = (salario_base * ronda_pct).quantize(Decimal("0.01"))
        remuneracao_base = salario_base + adic_insalubridade + adic_periculosidade + adic_ronda

        data_admissao = employee.data_admissao

        if not data_admissao:
            data_admissao = last_working_day  # fallback

        # Meses trabalhados (meses de calendário com regra dos 15 dias, tanto no
        # mês de admissão quanto no de demissão — não usar delta.days//30, que
        # usa mês fictício de 30 dias e infla os avos).
        meses_calendario = (last_working_day.year - data_admissao.year) * 12 + (
            last_working_day.month - data_admissao.month
        )
        # Mês de admissão só conta se admitido até o dia 15.
        if data_admissao.day > 15:
            meses_calendario -= 1
        # Mês de demissão conta se trabalhou >= 15 dias nele.
        if last_working_day.day >= 15:
            meses_calendario += 1
        months_worked = max(1, min(meses_calendario, 12))
        # tempo TOTAL de casa (SEM teto de 12): FGTS é depositado todo mês e as férias
        # vencidas dependem do tempo real — usar o valor capado aqui zerava a multa 40%
        # e as férias vencidas de quem tem mais de 1 ano.
        meses_totais_casa = max(1, meses_calendario)

        # Mapear tipo de rescisão para clt_calculator
        type_map = {
            TerminationType.INVOLUNTARY: "involuntary",
            TerminationType.VOLUNTARY: "voluntary",
            TerminationType.JUST_CAUSE: "just_cause",
            TerminationType.MUTUAL_AGREEMENT: "mutual_agreement",
        }
        tipo_str = type_map.get(termination_type, str(termination_type.value))

        # Estimar saldo FGTS acumulado (8% sobre a remuneração, base que inclui adicionais)
        # sobre o tempo REAL de casa (estimativa de referência; o saldo oficial vem do
        # extrato FGTS/Caixa antes de fechar o TRCT).
        saldo_fgts = remuneracao_base * Decimal("0.08") * meses_totais_casa

        # Férias vencidas: >12 meses de casa => há período aquisitivo vencido (estimativa;
        # o TRCT oficial confirma contra o histórico de férias gozadas). Nunca zerar por
        # causa do teto de avos.
        ferias_vencidas_dias = 30 if meses_totais_casa > 12 else 0

        # Dias trabalhados no mês da rescisão — teto de 30 para não exceder 100%
        # do salário do mês (a base do saldo é salário/30; dia 31 daria 103%).
        dias_trabalhados_mes = min(last_working_day.day, 30)

        # Usar clt_calculator para cálculo completo. A base das verbas é a
        # remuneração (salário + adicionais integrativos), não só o salário-base.
        calc = calcular_rescisao(
            salario_base=remuneracao_base,
            tipo_rescisao=tipo_str,
            data_admissao=data_admissao,
            data_demissao=last_working_day,
            saldo_fgts=saldo_fgts,
            ferias_vencidas_dias=ferias_vencidas_dias,
            dias_trabalhados_mes=dias_trabalhados_mes,
        )

        # months_worked exibido = maior avo entre 13º e férias (evita mostrar um
        # número que contradiz as verbas pagas). A contagem própria acima
        # (regra dos 15 dias no mês de admissão/demissão) fica como referência
        # de tempo total de casa em months_worked_calendario.
        avos_13 = int(calc["avos_13"])
        avos_ferias = int(calc["avos_ferias"])

        # Reconciliação: total_proventos DEVE bater com a soma das linhas.
        terco_total = calc["terco_ferias_vencidas"] + calc["terco_ferias_proporcionais"]
        soma_verbas = (
            calc["saldo_salario"]
            + calc["aviso_previo_indenizado"]
            + calc["ferias_vencidas"]
            + calc["ferias_proporcionais"]
            + terco_total
            + calc["decimo_terceiro_proporcional"]
        )

        return {
            "employee_id": str(employee_id),
            "employee_name": employee.nome,
            "termination_type": termination_type,
            "last_working_day": last_working_day,
            # Avos exibido: usa o maior entre 13º e férias como "meses trabalhados"
            # de referência; os avos exatos por verba vão em campos próprios.
            "months_worked": max(avos_13, avos_ferias, months_worked),
            "months_worked_calendario": months_worked,
            "avos_decimo_terceiro": avos_13,
            "avos_ferias_proporcionais": avos_ferias,
            "salario_base": float(salario_base),
            "adicional_insalubridade": float(adic_insalubridade),
            "adicional_periculosidade": float(adic_periculosidade),
            "adicional_ronda": float(adic_ronda),
            "remuneracao_base": float(remuneracao_base),
            "saldo_salario": float(calc["saldo_salario"]),
            "aviso_previo_indenizado": float(calc["aviso_previo_indenizado"]),
            "aviso_previo_dias": calc["aviso_previo_dias"],
            "ferias_vencidas": float(calc["ferias_vencidas"]),
            "terco_ferias_vencidas": float(calc["terco_ferias_vencidas"]),
            "ferias_proporcionais": float(calc["ferias_proporcionais"]),
            "terco_ferias_proporcionais": float(calc["terco_ferias_proporcionais"]),
            "terco_constitucional": float(terco_total),
            "decimo_terceiro_proporcional": float(calc["decimo_terceiro_proporcional"]),
            # Multa FGTS é INDENIZATÓRIA — fora do total de proventos, sem INSS/IRRF.
            "multa_fgts_40": float(calc["multa_fgts"]),
            "saldo_fgts_estimado": float(saldo_fgts),
            "fgts_estimado": True,
            # total_proventos = soma EXATA das verbas de provento (sem multa FGTS).
            "total_proventos": float(calc["total_proventos"]),
            "soma_verbas_proventos": float(soma_verbas),
            "total_indenizatorio_fgts": float(calc["multa_fgts"]),
            "total_bruto": float(calc["total_bruto"]),
            "inss": float(calc["inss"]),
            "irrf": float(calc["irrf"]),
            "total_descontos": float(calc["total_descontos"]),
            "total_liquido": float(calc["total_liquido"]),
        }

    async def complete_termination(
        self,
        termination_id: str | UUID,
    ) -> TerminationProcess | None:
        """Conclui o processo de rescisão.

        Atualiza o status do funcionário para 'Desligado' e marca
        o processo como concluído.

        Args:
            termination_id: ID do processo de rescisão.

        Returns:
            Processo atualizado ou None se não encontrado.
        """
        termination = await self.get_by_id(termination_id)
        if not termination:
            return None

        # Calcular verbas se ainda não calculadas
        if not termination.total_amount and termination.last_working_day:
            calc = await self.calculate_severance(
                termination.employee_id,
                TerminationType(termination.type),
                termination.last_working_day,
            )
            termination.severance_amount = calc.get("aviso_previo_indenizado", 0)
            termination.vacation_balance_amount = calc.get("ferias_vencidas", 0) + calc.get("ferias_proporcionais", 0)
            termination.thirteenth_salary_amount = calc.get("decimo_terceiro_proporcional", 0)
            termination.fgts_amount = calc.get("multa_fgts_40", 0)
            termination.total_amount = calc.get("total_liquido", 0)

        termination.status = TerminationStatus.COMPLETED

        # Atualizar status do funcionário
        emp_result = await self.db.execute(select(Employee).where(Employee.id == str(termination.employee_id)))
        employee = emp_result.scalar_one_or_none()
        if employee:
            # canônico: 'demitido' (não "Desligado" — que o trigger de is_active trata como
            # ATIVO e as queries de demitido não pegam)
            employee.status = "demitido"
            if termination.last_working_day:
                employee.data_demissao = termination.last_working_day

            # encerrar benefícios ATIVOS do demitido — senão seguem 'active' e continuam
            # sendo somados/descontados na folha do mês seguinte
            from sqlalchemy import text as _sqltext

            await self.db.execute(
                _sqltext(
                    "UPDATE employee_benefits SET status='cancelled', "
                    "end_date=:d, updated_at=NOW() "
                    "WHERE CAST(employee_id AS TEXT)=:e AND status='active'"
                ),
                {"d": termination.last_working_day, "e": str(termination.employee_id)},
            )

            # encerrar o CONTRATO vigente — end_date E is_current=false. O badge "Vigente" lê
            # is_current (não deriva de end_date), então setar só a data deixava o demitido
            # como "Vigente". Encerra os contratos abertos (end_date NULL) e também qualquer
            # contrato ainda marcado is_current do demitido.
            await self.db.execute(
                _sqltext(
                    "UPDATE employment_contracts SET "
                    "end_date=COALESCE(end_date, :d), is_current=false, updated_at=NOW() "
                    "WHERE CAST(employee_id AS TEXT)=:e AND (end_date IS NULL OR is_current=true)"
                ),
                {"d": termination.last_working_day, "e": str(termination.employee_id)},
            )

        await self.db.flush()
        await self.db.refresh(termination)
        logger.info("Rescisão %s concluída", termination_id)

        # Publicar evento de funcionário demitido no ConectaEventBus
        try:
            import asyncio

            from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

            asyncio.create_task(
                event_bus.publish(
                    ConectaEvent(
                        event_type=EventTypes.DP_FUNCIONARIO_DEMITIDO,
                        payload={
                            "employee_id": str(termination.employee_id),
                            "termination_id": str(termination_id),
                            "tipo_rescisao": termination.type,
                            "ultimo_dia": str(termination.last_working_day) if termination.last_working_day else None,
                            "cargo": employee.cargo if employee else None,
                            "departamento": employee.departamento if employee else None,
                        },
                        source_module="dp",
                        funcionario_id=str(termination.employee_id),
                    )
                )
            )
        except Exception as _pub_err:
            logger.warning("Falha ao publicar DP_FUNCIONARIO_DEMITIDO: %s", _pub_err)

        return termination
