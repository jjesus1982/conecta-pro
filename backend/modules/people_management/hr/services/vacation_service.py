"""
Serviço de Férias — Departamento Pessoal.

Re-exporta funcionalidades do employee_portal e módulo operacional de férias,
adicionando cálculo de saldo de férias com valores CLT reais (Decimal).
"""

import contextlib
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.employee import Employee
from modules.people_management.common.utils.clt_calculator import calcular_ferias

logger = logging.getLogger(__name__)

# Re-export do serviço existente de férias
try:
    from modules.hr.employee_portal.services import VacationService as PortalVacationService
except ImportError:
    PortalVacationService = None  # type: ignore[assignment, misc]

try:
    from modules.operacional.vacations.models import VacationRequest
except ImportError:
    VacationRequest = None  # type: ignore[assignment, misc]


class VacationService:
    """Serviço de Férias — visão DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._portal_service = None
        if PortalVacationService:
            with contextlib.suppress(Exception):
                self._portal_service = PortalVacationService(db)

    async def get_by_id(self, vacation_id: str | UUID) -> "VacationRequest | None":
        """Busca uma solicitação de férias pelo ID.

        Args:
            vacation_id: ID da solicitação de férias.

        Returns:
            Instância de VacationRequest ou None se não encontrada.
        """
        if not VacationRequest:
            return None
        result = await self.db.execute(select(VacationRequest).where(VacationRequest.id == str(vacation_id)))
        return result.scalar_one_or_none()

    async def list_by_employee(self, employee_id: str | UUID, page: int = 1, page_size: int = 20) -> dict:
        """Lista solicitações de férias de um funcionário específico.

        Args:
            employee_id: ID do funcionário.
            page: Página atual.
            page_size: Itens por página.

        Returns:
            Dicionário com items, total e paginação.
        """
        if not VacationRequest:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

        from sqlalchemy import func

        emp_id = str(employee_id)
        count_q = select(func.count()).select_from(VacationRequest).where(VacationRequest.employee_id == emp_id)
        total = (await self.db.execute(count_q)).scalar() or 0

        query = (
            select(VacationRequest)
            .where(VacationRequest.employee_id == emp_id)
            .order_by(VacationRequest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def calculate_vacation_balance(self, employee_id: str | UUID) -> dict:
        """Calcula o saldo de férias do funcionário.

        Considera data de admissão, períodos aquisitivos e férias já gozadas.

        Args:
            employee_id: ID do funcionário.

        Returns:
            Dicionário com dados do saldo de férias.
        """
        result = await self.db.execute(select(Employee).where(Employee.id == str(employee_id)))
        employee = result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        data_admissao = employee.data_admissao
        if not data_admissao:
            return {
                "employee_id": str(employee_id),
                "employee_name": employee.nome,
                "dias_direito": 0,
                "dias_gozados": 0,
                "dias_saldo": 0,
                "periodos_aquisitivos": [],
                "message": "Data de admissão não informada",
            }

        today = date.today()
        delta = today - data_admissao
        meses_trabalhados = delta.days // 30

        # Dias de direito: 30 dias a cada 12 meses
        periodos_completos = meses_trabalhados // 12
        meses_periodo_atual = meses_trabalhados % 12
        dias_proporcional = int((30 / 12) * meses_periodo_atual)
        dias_direito_total = (periodos_completos * 30) + dias_proporcional

        # Buscar férias gozadas
        dias_gozados = 0
        if VacationRequest:
            try:
                # O banco grava status em português ('aprovado'/'aprovada'); manter
                # também os valores em inglês por compatibilidade histórica.
                status_aprovado = ["aprovado", "aprovada", "approved", "APPROVED"]
                vac_result = await self.db.execute(
                    select(VacationRequest).where(
                        VacationRequest.employee_id == str(employee_id),
                        VacationRequest.status.in_(status_aprovado),
                    )
                )
                vacations = vac_result.scalars().all()
                for v in vacations:
                    if hasattr(v, "days_count") and v.days_count:
                        dias_gozados += v.days_count
                    elif hasattr(v, "start_date") and hasattr(v, "end_date"):
                        if v.start_date and v.end_date:
                            # +1: intervalo inclusivo (o registro de criação grava days com +1)
                            dias_gozados += (v.end_date - v.start_date).days + 1
            except Exception as e:
                logger.warning("Erro ao buscar férias gozadas: %s", e)

        dias_saldo = max(0, dias_direito_total - dias_gozados)

        # [Achado 5] Detecção de período aquisitivo VENCIDO (art. 137 CLT — dobra).
        # Cada período aquisitivo completo (12 meses) abre um período concessivo de mais
        # 12 meses para o empregador conceder as férias. Se um período aquisitivo já venceu
        # (>= 24 meses de admissão sem que essas férias tenham sido gozadas), o pagamento é
        # em DOBRA. Aproximação: dias vencidos = saldo que corresponde a períodos aquisitivos
        # já encerrados há mais de 12 meses e ainda não gozados.
        # Períodos concessivos já vencidos = períodos aquisitivos completos com mais de
        # 12 meses de "idade" (ou seja, admissão há >= 24 meses para o 1º, >=36 p/ o 2º...).
        periodos_concessivos_vencidos = max(0, (meses_trabalhados - 12) // 12)
        dias_potencial_vencido = periodos_concessivos_vencidos * 30
        # Dos dias em saldo, quantos pertencem a período aquisitivo já vencido (não gozado).
        dias_vencidos = max(0, min(dias_saldo, dias_potencial_vencido - 0))
        # Só há dobra sobre o que efetivamente ainda está em saldo e é de período vencido.
        dias_vencidos = min(dias_vencidos, dias_saldo)
        alerta_dobra = dias_vencidos > 0

        # Cálculo de valores monetários das férias com CLT real
        salario_base = Decimal(str(employee.salario_base or 0))
        valor_ferias = 0.0
        terco_constitucional = 0.0
        abono_pecuniario = 0.0
        total_bruto_ferias = 0.0

        if dias_saldo > 0 and salario_base > 0:
            dias_gozo = min(dias_saldo, 30)
            dias_abono = max(0, dias_saldo - 30) if dias_saldo > 30 else 0
            ferias_calc = calcular_ferias(salario_base, dias_gozo=dias_gozo, dias_abono=dias_abono)
            valor_ferias = float(ferias_calc["valor_ferias"])
            terco_constitucional = float(ferias_calc["terco_constitucional"])
            abono_pecuniario = float(ferias_calc["abono_pecuniario"])
            total_bruto_ferias = float(ferias_calc["total_bruto"])

        return {
            "employee_id": str(employee_id),
            "employee_name": employee.nome,
            "data_admissao": data_admissao.isoformat(),
            "meses_trabalhados": meses_trabalhados,
            "periodos_completos": periodos_completos,
            "dias_direito": dias_direito_total,
            "dias_gozados": dias_gozados,
            "dias_saldo": dias_saldo,
            "dias_proporcional_periodo_atual": dias_proporcional,
            # [Achado 5] Alerta de período aquisitivo vencido (art. 137 CLT — férias em DOBRA)
            "dias_vencidos": dias_vencidos,
            "periodos_concessivos_vencidos": periodos_concessivos_vencidos,
            "alerta_dobra": alerta_dobra,
            "aviso_dobra": (
                f"{dias_vencidos} dia(s) de férias em período aquisitivo VENCIDO "
                "(art. 137 CLT): pagamento em DOBRA se não concedidas"
                if alerta_dobra
                else None
            ),
            "valor_ferias": valor_ferias,
            "terco_constitucional": terco_constitucional,
            "abono_pecuniario": abono_pecuniario,
            "total_bruto_ferias": total_bruto_ferias,
        }

    async def approve_vacation(
        self,
        vacation_id: str | UUID,
        approved_by_id: str | UUID | None = None,
    ) -> dict:
        """Aprova uma solicitação de férias e notifica operações.

        Args:
            vacation_id: ID da solicitação de férias.
            approved_by_id: ID do usuário que aprovou.

        Returns:
            Dicionário com resultado da aprovação.
        """
        if not VacationRequest:
            raise ValueError("Módulo de férias não disponível")

        result = await self.db.execute(select(VacationRequest).where(VacationRequest.id == str(vacation_id)))
        vacation = result.scalar_one_or_none()
        if not vacation:
            raise ValueError(f"Solicitação de férias {vacation_id} não encontrada")

        # Grava status em PT-BR ('aprovado'), consistente com o banco, com o filtro
        # ?status=aprovado e com o frontend (badge/contadores). NÃO produzir 'approved' (inglês).
        vacation.status = "aprovado"
        if hasattr(vacation, "approved_by_id"):
            vacation.approved_by_id = str(approved_by_id) if approved_by_id else None

        await self.db.flush()
        await self.db.refresh(vacation)

        # Notificar operações (async, não bloqueia)
        try:
            from modules.operacional.services import notify_vacation_approved

            await notify_vacation_approved(vacation)
        except (ImportError, Exception) as e:
            logger.info("Notificação de férias não enviada: %s", e)

        try:
            from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

            await event_bus.publish(
                ConectaEvent(
                    event_type=EventTypes.DP_FERIAS_APROVADAS,
                    payload={
                        "vacation_id": str(vacation_id),
                        "employee_id": str(getattr(vacation, "employee_id", "")),
                        "start_date": str(getattr(vacation, "start_date", "")),
                        "end_date": str(getattr(vacation, "end_date", "")),
                        "days_requested": getattr(vacation, "days_requested", None),
                    },
                    source_module="dp",
                    funcionario_id=str(getattr(vacation, "employee_id", "")),
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Falha ao publicar evento ferias: %s", exc)

        logger.info("Férias %s aprovadas", vacation_id)
        return {
            "vacation_id": str(vacation_id),
            "status": "aprovado",
            "message": "Férias aprovadas com sucesso",
        }

    async def sync_vacations_from_solides(
        self,
        employee_id: str | None = None,
        periodo_inicio: str | None = None,
        periodo_fim: str | None = None,
    ) -> dict:
        """Sincroniza férias do Sólides para o sistema de férias do DP.

        Busca absences do tipo FERIAS/VACATION e cria registros locais
        em gp_justifications, evitando duplicatas via source_id.

        Returns:
            Dict com total_importadas, total_atualizadas, erros.
        """
        import os
        from datetime import date
        from uuid import uuid4

        import httpx

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            logger.warning("sync_vacations_from_solides: SOLIDES_API_TOKEN não configurado")
            return {"success": False, "reason": "no_token", "total_importadas": 0}

        hoje = date.today()
        inicio = periodo_inicio or hoje.replace(day=1).isoformat()
        fim = periodo_fim or hoje.isoformat()

        importadas = 0
        atualizadas = 0
        erros: list[dict] = []

        try:
            base_url = os.getenv("SOLIDES_BASE_URL", "https://employer.tangerino.com.br")
            headers = {"Authorization": f"Basic {api_token}", "Accept": "application/json"}
            params: dict = {"startDate": inicio, "endDate": fim, "page": 0, "size": 200}
            if employee_id:
                params["employeeId"] = employee_id

            resp = httpx.get(f"{base_url}/absence/find-all", headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "reason": f"api_{resp.status_code}", "total_importadas": 0}

            data = resp.json()
            absences = data if isinstance(data, list) else data.get("content", data.get("data", []))

            ferias_types = {"FERIAS", "VACATION", "FÉRIAS", "ANNUAL_LEAVE", "FOLGA"}
            ferias = [
                a
                for a in absences
                if str(a.get("type", "")).upper() in ferias_types
                or "FERIA" in str(a.get("type", "")).upper()
                or "VACATION" in str(a.get("type", "")).upper()
            ]

            for absence in ferias:
                try:
                    solides_id = str(absence.get("id", ""))
                    solides_emp_id = str(absence.get("employeeId") or absence.get("employee_id", ""))
                    start_raw = absence.get("startDate") or absence.get("start_date", "")
                    end_raw = absence.get("endDate") or absence.get("end_date", start_raw)
                    if not start_raw:
                        continue

                    row = (
                        await self.db.execute(
                            text("SELECT employee_id FROM solides_employees WHERE solides_id::text = :sid LIMIT 1"),
                            {"sid": solides_emp_id},
                        )
                    ).fetchone()
                    if not row:
                        continue
                    local_emp_id = row[0]

                    source_id = f"solides_ferias_{solides_id}"
                    dup = (
                        await self.db.execute(
                            text("SELECT 1 FROM gp_justifications WHERE source_id = :sid LIMIT 1"),
                            {"sid": source_id},
                        )
                    ).fetchone()
                    if dup:
                        atualizadas += 1
                        continue

                    await self.db.execute(
                        text("""
                            INSERT INTO gp_justifications
                            (justification_id, employee_id, justification_type, reason, category,
                             status, source, source_id, created_at)
                            VALUES (:jid, :eid, 'falta',
                                    :reason, 'outro', 'aprovada', 'solides', :source_id, NOW())
                        """),
                        {
                            "jid": str(uuid4()),
                            "eid": local_emp_id,
                            "reason": f"Férias Sólides: {start_raw[:10]} a {end_raw[:10] if end_raw else start_raw[:10]}",
                            "source_id": source_id,
                        },
                    )
                    await self.db.flush()
                    importadas += 1

                except Exception as e:
                    erros.append({"absence_id": str(absence.get("id", "")), "error": str(e)[:200]})

        except Exception as e:
            logger.error("sync_vacations_from_solides erro: %s", e)
            return {"success": False, "error": str(e), "total_importadas": 0}

        logger.info(
            "sync_vacations_from_solides: %d importadas, %d atualizadas, %d erros",
            importadas,
            atualizadas,
            len(erros),
        )
        return {
            "success": True,
            "total_importadas": importadas,
            "total_atualizadas": atualizadas,
            "total_erros": len(erros),
            "erros": erros,
        }
